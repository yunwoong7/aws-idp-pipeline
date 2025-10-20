"""
Analysis Agent API router
"""
import json
import logging
import os
import yaml
from typing import Dict, Any, Optional, List, Union
from fastapi import APIRouter, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
from src.agent.analysis_agent import AnalysisAgent
from langchain_core.messages import HumanMessage
from src.dependencies.permissions import get_current_user_from_request

# Logging configuration
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/analysis", tags=["analysis-agent"])

# Configuration paths
try:
    from ..utils.path_resolver import path_resolver
    MODELS_CONFIG_PATH = str(path_resolver.get_config_path("models.yaml"))
    MCP_CONFIG_PATH = str(path_resolver.get_mcp_config_path())
    logger.info(f"Using path resolver - models: {MODELS_CONFIG_PATH}, mcp: {MCP_CONFIG_PATH}")
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    MODELS_CONFIG_PATH = os.path.join(BASE_DIR, "config/models.yaml")
    MCP_CONFIG_PATH = os.path.join(BASE_DIR, "config/mcp_config.json")
    logger.warning("Path resolver not available, using fallback path logic")

# Initialize global agent variable
agent = None

# Startup event to initialize agent
async def initialize_agent_on_startup():
    """Initialize agent on server startup to avoid first request delay"""
    global agent
    try:
        if not agent:
            model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
            logger.info(f"Pre-initializing Analysis agent on startup: model={model_id}")
            agent = AnalysisAgent(model_id=model_id, mcp_json_path=MCP_CONFIG_PATH)
            await agent.startup()
            logger.info("Analysis agent pre-initialization completed successfully")
    except Exception as e:
        logger.error(f"Failed to pre-initialize agent on startup: {e}")
        # Don't fail the server startup if agent initialization fails
        agent = None

# Request and response models (same as analysis_agent.py for compatibility)
class ChatRequest(BaseModel):
    """Chat request model"""
    message: str
    stream: bool = True
    model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    index_id: Optional[str] = None
    thread_id: Optional[str] = None

class ReinitRequest(BaseModel):
    """Agent reinitialization request model"""
    model_id: Optional[str] = None
    reload_prompt: Optional[bool] = False
    thread_id: Optional[str] = None
    index_id: Optional[str] = None

class ReinitResponse(BaseModel):
    """Agent reinitialization response model"""
    success: bool
    model_id: str
    max_tokens: int
    message: str

class ChatResponse(BaseModel):
    """Chat response model"""
    response: str
    tool_calls: Optional[List[Dict[str, Any]]] = None

# Input state model for compatibility
from types import SimpleNamespace

def create_input_state(messages: List[Any], index_id: Optional[str] = None):
    """Create input state object"""
    return SimpleNamespace(messages=messages, index_id=index_id)

@router.post("/chat")
async def chat(
    request: Request,
    message: str = Form(None),
    stream: bool = Form(True),
    model_id: str = Form("us.anthropic.claude-3-7-sonnet-20250219-v1:0"),
    index_id: Optional[str] = Form(None),
    document_id: Optional[str] = Form(None),
    segment_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None)
):
    """
    Chat API endpoint (Strands implementation)
    
    Args:
        request: HTTP request
        message: User message text
        stream: Streaming response flag
        model_id: Model ID to use
        index_id: Index ID for context
        document_id: Document ID for context
        segment_id: Segment ID for context
        thread_id: Thread ID for conversation
        files: List of attachment files
        
    Returns:
        Chat response or streaming response
    """
    try:
        # Check if request is JSON or FormData
        content_type = request.headers.get("content-type", "")
        logger.info(f"Request Content-Type: {content_type}")
        
        # Handle JSON request
        if "application/json" in content_type:
            request_data = await request.json()
            message = request_data.get("message", "")
            stream = request_data.get("stream", True)
            model_id = request_data.get("model_id", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
            index_id = request_data.get("index_id")
            document_id = request_data.get("document_id")
            segment_id = request_data.get("segment_id")
            thread_id = request_data.get("thread_id")
            files_data = None
            logger.info(f"JSON request: message_len={len(message)}, stream={stream}, model={model_id}")
        
        # Handle file uploads if present
        processed_files = []
        if files and len(files) > 0:
            logger.info(f"File upload detected: {len(files)} files")
            for file in files:
                if file and file.filename:
                    try:
                        file_data = await file.read()
                        file_size = len(file_data)
                        file_info = {
                            "name": file.filename,
                            "type": file.content_type or "",
                            "data": file_data,
                            "size": file_size
                        }
                        processed_files.append(file_info)
                        logger.info(f"File added: {file.filename} ({file_size / 1024:.2f} KB)")
                    except Exception as e:
                        logger.error(f"File processing error: {e}")
                        raise HTTPException(status_code=400, detail=f"File upload error: {str(e)}")
        
        # Validate message
        if not message and not processed_files:
            raise HTTPException(status_code=400, detail="Message or files are required")
        
        # Initialize agent if needed
        global agent
        if not agent:
            logger.info(f"Initializing Analysis agent: model={model_id}")
            agent = AnalysisAgent(model_id=model_id, mcp_json_path=MCP_CONFIG_PATH)
            await agent.startup()
            logger.info("Analysis agent startup completed")
        
        # Get user information for thread isolation
        try:
            user_info = get_current_user_from_request(request)
            user_id = user_info.get("sub", user_info.get("email", "anonymous"))
            logger.info(f"User authenticated: {user_id}")
        except Exception as e:
            logger.warning(f"Failed to get user info, using anonymous: {e}")
            user_id = "anonymous"

        # Create messages
        messages = [HumanMessage(content=message)]

        # Handle thread ID with user isolation
        if not thread_id:
            if index_id:
                thread_id = f"thread_{user_id}_{index_id}"
                logger.info(f"Using user+index thread: {thread_id}")
            else:
                thread_id = f"thread_{user_id}_default"
                logger.info(f"Using user default thread: {thread_id}")
        else:
            logger.info(f"Using provided thread_id: {thread_id}")
        
        # Create config
        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }
        
        # Create input state
        input_state = create_input_state(messages, index_id)
        
        # Handle streaming response
        if stream:
            logger.info("Streaming response processing")
            
            async def stream_response():
                """Streaming response generator"""
                try:
                    # Stream from agent
                    async for chunk, metadata in agent.astream(
                        input_state,
                        config,
                        stream_mode="messages",
                        files=processed_files,
                        index_id=index_id,
                        document_id=document_id,
                        segment_id=segment_id
                    ):
                        # Format chunk for frontend compatibility
                        if hasattr(chunk, "content") and chunk.content:
                            response_content = chunk.content
                            
                            # Handle different content types
                            if isinstance(response_content, str):
                                # Determine chunk type based on metadata
                                chunk_type = "text"
                                if metadata.get("type") == "tool_result":
                                    chunk_type = "tool_result"
                                elif metadata.get("type") == "step_separator":
                                    # Step 구분자는 건너뛰기
                                    continue
                                
                                response_data = {
                                    "chunk": [{
                                        "type": chunk_type,
                                        "text": response_content,
                                        "index": 0
                                    }],
                                    "toolCalls": None,
                                    "metadata": metadata
                                }
                                yield f"data: {json.dumps(response_data)}\n\n"
                            
                        # Handle tool calls
                        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                            tool_use_items = []
                            for i, tool_call in enumerate(chunk.tool_calls):
                                tool_use_items.append({
                                    "type": "tool_use",
                                    "name": tool_call.get("name", ""),
                                    "input": json.dumps(tool_call.get("args", {})),
                                    "id": f"tooluse_{i}",
                                    "index": i
                                })
                            
                            response_data = {
                                "chunk": tool_use_items,
                                "toolCalls": None,
                                "metadata": metadata
                            }
                            yield f"data: {json.dumps(response_data)}\n\n"
                    
                except Exception as e:
                    logger.error(f"Streaming error: {e}")
                    error_data = {
                        "error": str(e),
                        "metadata": {
                            "langgraph_node": "error",
                            "langgraph_step": 0,
                            "type": "error"
                        }
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                
                # Send completion signal
                yield "data: [DONE]\n\n"
                logger.info("Streaming completed")
            
            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream"
            )
        
        # Handle non-streaming response
        else:
            logger.info("Non-streaming response processing")
            response = await agent.ainvoke(
                input_state, 
                config, 
                files=processed_files,
                index_id=index_id,
                document_id=document_id,
                segment_id=segment_id
            )
            
            # Extract response
            if "messages" in response and response["messages"]:
                last_message = response["messages"][0]
                response_content = last_message.content if hasattr(last_message, "content") else ""
                
                # Extract tool calls
                tool_calls = []
                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    for tool_call in last_message.tool_calls:
                        tool_calls.append({
                            "name": tool_call.get("name", ""),
                            "input": tool_call.get("args", {})
                        })
                
                return ChatResponse(
                    response=response_content,
                    tool_calls=tool_calls if tool_calls else None
                )
            else:
                return ChatResponse(response="Unable to generate response")
    
    except Exception as e:
        logger.error(f"Chat processing error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    message: str = Form(None),
    model_id: str = Form("us.anthropic.claude-3-7-sonnet-20250219-v1:0"),
    index_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None)
):
    """Chat streaming endpoint"""
    return await chat(request, message, True, model_id, index_id, None, None, thread_id, files)

@router.post("/reinit")
async def reinit_agent(request: ReinitRequest = None):
    """
    Agent reinitialization endpoint
    
    Args:
        request: Reinitialization request
        
    Returns:
        Reinitialization response
    """
    global agent
    
    try:
        # Get model ID
        model_id = request.model_id if request else None
        
        logger.info(f"Reinitializing agent: model_id={model_id}")
        
        # Shutdown existing agent
        if agent:
            try:
                await agent.shutdown()
            except Exception as e:
                logger.warning(f"Failed to shutdown agent: {e}")
        
        # Create new agent
        agent = AnalysisAgent(
            model_id=model_id or "",
            reload_prompt=True if request and request.reload_prompt else False
        )
        await agent.startup()
        
        # Clear conversation histories - critical for memory cleanup
        if request and request.thread_id:
            # Clear specific thread
            agent.clear_conversation_history(request.thread_id)
            logger.info(f"Cleared conversation history for thread: {request.thread_id}")
        else:
            # Clear all conversation histories
            agent.clear_conversation_history()
            logger.info("All conversation histories cleared")
        
        return ReinitResponse(
            success=True,
            model_id=agent.model_id,
            max_tokens=agent.max_tokens,
            message="Agent reinitialized successfully"
        )
    
    except Exception as e:
        logger.error(f"Reinitialization error: {e}")
        return ReinitResponse(
            success=False,
            model_id="",
            max_tokens=4096,
            message=f"Reinitialization failed: {str(e)}"
        )
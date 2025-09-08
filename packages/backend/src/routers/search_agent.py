"""
Search API router with Plan-Execute-Respond pattern
"""
import json
import logging
import os
import yaml
from typing import Dict, Any, Optional, List, Union, Annotated

from fastapi import APIRouter, HTTPException, Request, Form, File, UploadFile, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pathlib import Path

from src.agent.search_agent import SearchAgent

# logging configuration
logger = logging.getLogger(__name__)

# create router
router = APIRouter(prefix="/api", tags=["search"])

# Configuration paths using path resolver
try:
    from ..utils.path_resolver import path_resolver
    MODELS_CONFIG_PATH = str(path_resolver.get_config_path("models.yaml"))
    MCP_CONFIG_PATH = str(path_resolver.get_mcp_config_path())
    logger.info(f"Using path resolver - models: {MODELS_CONFIG_PATH}, mcp: {MCP_CONFIG_PATH}")
except ImportError:
    # Fallback to original logic
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    MODELS_CONFIG_PATH = os.path.join(BASE_DIR, "config/models.yaml")
    MCP_CONFIG_PATH = os.path.join(BASE_DIR, "config/mcp_config.json")
    logger.warning("Path resolver not available, using fallback path logic")

# User settings
USER_SETTINGS_DIR = os.path.expanduser("~/.mcp-client")
USER_MODEL_FILE = os.path.join(USER_SETTINGS_DIR, "aws_idp_mcp_client.json")

# Global agent
search_agent = None

# Conversation histories (in production, use Redis or database)
conversation_histories = {}

class SearchRequest(BaseModel):
    """search request model"""
    message: str
    stream: bool = True
    model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    index_id: Optional[str] = None
    document_id: Optional[str] = None
    segment_id: Optional[str] = None
    thread_id: Optional[str] = None

class SearchResponse(BaseModel):
    """search response model"""
    response: str
    references: List[Dict[str, Any]] = []
    plan: Optional[Dict[str, Any]] = None

def get_user_model() -> str:
    """Load user model settings"""
    try:
        if not os.path.exists(USER_MODEL_FILE):
            logger.debug("User model setting not found, return default value")
            return "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        
        with open(USER_MODEL_FILE, "r") as f:
            data = json.load(f)
            model_id = data.get("model_id", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
            logger.debug(f"User model load success: {model_id}")
            return model_id
    except Exception as e:
        logger.error(f"User model load failed: {e}")
        return "us.anthropic.claude-3-7-sonnet-20250219-v1:0"

def load_model_config(model_id: str) -> Dict[str, Any]:
    """Load model configuration"""
    try:
        if not os.path.exists(MODELS_CONFIG_PATH):
            logger.error(f"Model configuration file not found: {MODELS_CONFIG_PATH}")
            return {"max_output_tokens": 4096}
        
        with open(MODELS_CONFIG_PATH, "r") as f:
            models_config = yaml.safe_load(f)
        
        # Search model configuration
        for provider_id, provider_data in models_config.get("providers", {}).items():
            for model_config_id, model_data in provider_data.get("models", {}).items():
                if model_data.get("id") == model_id:
                    logger.debug(f"Model configuration load success: {model_id}")
                    return model_data
        
        logger.warning(f"No configuration found for specified model ID: {model_id}")
        return {"max_output_tokens": 4096}
    except Exception as e:
        logger.error(f"Model configuration load failed: {e}")
        return {"max_output_tokens": 4096}

async def initialize_search_agent(model_id: str, max_tokens: int) -> SearchAgent:
    """Initialize SearchAgent"""
    global search_agent
    
    if not search_agent or search_agent.model_id != model_id:
        logger.info(f"Initializing SearchAgent: model={model_id}, max_tokens={max_tokens}")
        
        if search_agent:
            await search_agent.shutdown()
        
        search_agent = SearchAgent(
            model_id=model_id,
            max_tokens=max_tokens,
            mcp_config_path=MCP_CONFIG_PATH,
            verbose=True
        )
        
        await search_agent.startup()
        logger.info("SearchAgent initialization completed")
    
    return search_agent

def get_conversation_history(thread_id: str) -> List[Dict[str, str]]:
    """Get conversation history for thread"""
    return conversation_histories.get(thread_id, [])

def update_conversation_history(thread_id: str, history: List[Dict[str, str]]):
    """Update conversation history for thread"""
    conversation_histories[thread_id] = history[-20:]  # Keep last 20 messages

@router.post("/search")
async def search(
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
    Search API endpoint with Plan-Execute-Respond pattern
    """
    try:
        # Handle request parsing
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
            files = []
            logger.info(f"JSON request: message_len={len(message)}, model={model_id}")
        
        # Validate message
        if not message or not message.strip():
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Handle model configuration
        if not model_id:
            model_id = get_user_model()
            logger.info(f"Using default model: {model_id}")
        
        model_config = load_model_config(model_id)
        max_tokens = model_config.get("max_output_tokens", 4096)
        logger.info(f"Model config: {model_id}, max_tokens={max_tokens}")
        
        # Initialize SearchAgent
        agent = await initialize_search_agent(model_id, max_tokens)
        
        # Handle thread ID
        if not thread_id:
            if index_id:
                thread_id = f"thread_{index_id}"
                logger.info(f"Using index-based thread: {thread_id}")
            else:
                thread_id = f"thread_default_{id(request)}"
                logger.info(f"Using default thread: {thread_id}")
        
        # Get conversation history
        message_history = get_conversation_history(thread_id)
        logger.info(f"Loaded {len(message_history)} previous messages")
        
        # Handle streaming response
        if stream:
            logger.info("Starting streaming response")
            
            async def stream_search_response():
                """Stream search response with plan visualization"""
                try:
                    updated_history = None
                    final_references = []
                    final_plan = None
                    
                    async for event in agent.astream(
                        message=message,
                        message_history=message_history,
                        index_id=index_id,
                        document_id=document_id,
                        segment_id=segment_id
                    ):
                        event_type = event.get("type", "unknown")
                        
                        # Planning events
                        if event_type == "planning_start":
                            yield f"data: {json.dumps({'type': 'planning_start', 'message': event['message']})}\n\n"
                            
                        elif event_type == "planning_token":
                            yield f"data: {json.dumps({'type': 'planning_token', 'token': event['token']})}\n\n"
                            
                        elif event_type == "plan_complete":
                            plan = event["plan"]
                            final_plan = plan.model_dump() if hasattr(plan, 'model_dump') else plan
                            
                            # Send plan to frontend
                            yield f"data: {json.dumps({'type': 'plan', 'plan': final_plan})}\n\n"
                        
                        # Phase transitions
                        elif event_type == "phase_start":
                            phase = event["phase"]
                            yield f"data: {json.dumps({'type': 'phase_start', 'phase': phase, 'message': event['message']})}\n\n"
                            
                        elif event_type == "phase_skip":
                            yield f"data: {json.dumps({'type': 'phase_skip', 'phase': event['phase'], 'message': event['message']})}\n\n"
                        
                        # Execution events
                        elif event_type == "task_start":
                            yield f"data: {json.dumps({'type': 'task_start', 'task': event['task'], 'message': event['message']})}\n\n"
                            
                        elif event_type == "task_complete":
                            # Include references from task result if available
                            task_data = {
                                'type': 'task_complete',
                                'task': event['task'],
                                'message': event['message']
                            }
                            if 'references' in event:
                                task_data['references'] = event['references']
                            if 'result' in event:
                                task_data['result'] = event['result']
                            yield f"data: {json.dumps(task_data)}\n\n"
                            
                        elif event_type == "task_failed":
                            yield f"data: {json.dumps({'type': 'task_failed', 'task': event['task'], 'error': event['error']})}\n\n"
                        
                        elif event_type == "execution_complete":
                            # Send execution complete event with all references
                            yield f"data: {json.dumps({'type': 'execution_complete', 'all_references': event.get('all_references', []), 'message': event.get('message', 'Execution completed')})}\n\n"
                        
                        # Response events
                        elif event_type == "response_start":
                            yield f"data: {json.dumps({'type': 'response_start', 'message': event['message']})}\n\n"
                            
                        elif event_type == "response_token":
                            yield f"data: {json.dumps({'type': 'token', 'token': event['token']})}\n\n"
                        
                        # Final events
                        elif event_type == "workflow_complete":
                            updated_history = event["message_history"]
                            final_references = event["references"]
                            
                            # Send references
                            if final_references:
                                yield f"data: {json.dumps({'type': 'references', 'references': final_references})}\n\n"
                            
                            # Send completion
                            yield f"data: {json.dumps({'type': 'complete', 'message': 'Response completed successfully'})}\n\n"
                            
                        elif event_type == "workflow_error":
                            error_msg = event.get("error", "Unknown error")
                            yield f"data: {json.dumps({'type': 'error', 'error': error_msg})}\n\n"
                            return
                    
                    # Update conversation history
                    if updated_history:
                        update_conversation_history(thread_id, updated_history)
                        logger.info(f"Updated conversation history for thread: {thread_id}")
                    
                    # Send final done signal
                    yield f"data: [DONE]\n\n"
                    
                except Exception as e:
                    logger.error(f"Streaming error: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            
            return StreamingResponse(
                stream_search_response(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                }
            )
        
        else:
            # Handle non-streaming response
            logger.info("Processing non-streaming request")
            
            result = await agent.ainvoke(
                message=message,
                message_history=message_history,
                index_id=index_id,
                document_id=document_id,
                segment_id=segment_id
            )
            
            # Update conversation history
            update_conversation_history(thread_id, result["message_history"])
            
            return SearchResponse(
                response=result["response"],
                references=result["references"],
                plan=result.get("plan")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search processing error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Search processing failed: {str(e)}")

@router.post("/search/stream")
async def search_stream(
    request: Request,
    message: str = Form(None),
    model_id: str = Form("us.anthropic.claude-3-7-sonnet-20250219-v1:0"),
    index_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None)
):
    """Dedicated streaming search endpoint"""
    return await search(
        request=request,
        message=message,
        stream=True,
        model_id=model_id,
        index_id=index_id,
        thread_id=thread_id,
        files=files
    )

@router.post("/search/reinit")
async def reinit_agent(
    model_id: Annotated[Optional[str], Form()] = None,
    reload_prompt: Annotated[Optional[bool], Form()] = False,
    thread_id: Annotated[Optional[str], Form()] = None,
    index_id: Annotated[Optional[str], Form()] = None
):
    """Agent reinitialization"""
    global search_agent, conversation_histories
    
    try:
        # determine model ID (provided in request or loaded from user settings)
        model_id = model_id if model_id else get_user_model()
        
        # load model configuration
        model_config = load_model_config(model_id)
        max_tokens = model_config.get("max_output_tokens", 4096)
        
        logger.info(f"SearchAgent reinitialization: model_id={model_id}, max_tokens={max_tokens}")
        
        # if existing agent exists, clean up
        if search_agent:
            try:
                await search_agent.shutdown()
            except Exception as e:
                logger.warning(f"Failed to shutdown existing search_agent: {e}")
        
        # recreate agent
        search_agent = SearchAgent(
            model_id=model_id, 
            max_tokens=max_tokens, 
            mcp_config_path=MCP_CONFIG_PATH
        )
        
        # startup the agent - this initializes MCP connections
        await search_agent.startup()
        
        # clear conversation histories - this is critical for memory cleanup
        if thread_id:
            # clear specific thread
            if thread_id in conversation_histories:
                del conversation_histories[thread_id]
                logger.info(f"Cleared conversation history for thread: {thread_id}")
            
            # clear agent-specific conversation for thread
            if hasattr(search_agent, 'clear_conversation_history'):
                success = search_agent.clear_conversation_history(thread_id)
                logger.info(f"Agent conversation clear for thread {thread_id}: {success}")
        else:
            # clear all conversation histories
            conversation_histories.clear()
            logger.info("All conversation histories cleared")
            
            # clear all agent conversations 
            if hasattr(search_agent, 'clear_conversation_history'):
                success = search_agent.clear_conversation_history()  # None clears all
                logger.info(f"All agent conversations cleared: {success}")
        
        logger.info("SearchAgent reinitialization completed successfully")
        
        return {
            "success": True,
            "model_id": model_id,
            "max_tokens": max_tokens,
            "message": "SearchAgent reinitialized successfully with conversation history cleared"
        }
    
    except Exception as e:
        logger.error(f"SearchAgent reinitialization error: {e}")
        # retry with default model if error occurs
        try:
            # if existing agent exists, clean up
            if search_agent:
                try:
                    await search_agent.shutdown()
                except Exception as shutdown_error:
                    logger.warning(f"Failed to shutdown existing search_agent during fallback: {shutdown_error}")
            
            model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
            model_config = load_model_config(model_id)
            max_tokens = model_config.get("max_output_tokens", 4096)
            
            logger.info(f"Fallback SearchAgent reinitialization: model_id={model_id}")
            
            # recreate agent with default model
            search_agent = SearchAgent(model_id=model_id, max_tokens=max_tokens, mcp_config_path=MCP_CONFIG_PATH)
            await search_agent.startup()
            
            # clear conversation histories
            conversation_histories.clear()
            if hasattr(search_agent, 'clear_conversation_history'):
                search_agent.clear_conversation_history()
            
            logger.info("SearchAgent fallback reinitialization completed")
            
            return {
                "success": True,
                "model_id": model_id,
                "max_tokens": max_tokens,
                "message": f"Error occurred after reinitialization, retry with default model (conversation history cleared): {str(e)}"
            }
        except Exception as fallback_error:
            logger.error(f"Error occurred during reinitialization with default model: {fallback_error}")
            raise HTTPException(status_code=500, detail=f"SearchAgent reinitialization failed: {str(e)}")

@router.get("/search/health")
async def search_health():
    """Search agent health check"""
    try:
        if not search_agent:
            return {"status": "not_initialized", "search_agent": False}
        
        health_status = await search_agent.health_check()
        return {"status": "ok", **health_status}
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "error": str(e)}
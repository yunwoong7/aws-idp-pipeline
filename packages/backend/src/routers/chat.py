"""
Agent API router
"""
import json
import logging
import os
import yaml
from typing import Dict, Any, Optional, List, Union, Annotated

from fastapi import APIRouter, HTTPException, Request, Form, File, UploadFile, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import RunnableConfig
from pathlib import Path
from src.agent.react_agent import ReactAgent
from src.agent.react_agent.state.model import InputState
from src.common.configuration import Configuration
from src.mcp_client.mcp_service import MCPService

# logging configuration
logger = logging.getLogger(__name__)

# create router
router = APIRouter(prefix="/api", tags=["chat"])

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

# User settings (these should remain in user directory)
USER_SETTINGS_DIR = os.path.expanduser("~/.mcp-client")
USER_MODEL_FILE = os.path.join(USER_SETTINGS_DIR, "aws_idp_mcp_client.json")

# initialize global agent variable
agent = None

# request and response model
class ChatRequest(BaseModel):
    """chat request model"""
    message: str
    stream: bool = True
    model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    index_id: Optional[str] = None
    thread_id: Optional[str] = None

# attachment file information model
class FileInfo(BaseModel):
    """attachment file information model"""
    name: str
    type: str
    data: Union[str, bytes]
    size: int

class ReinitRequest(BaseModel):
    """agent reinitialization request model"""
    model_id: Optional[str] = None
    reload_prompt: Optional[bool] = False
    thread_id: Optional[str] = None
    index_id: Optional[str] = None

class ReinitResponse(BaseModel):
    """agent reinitialization response model"""
    success: bool
    model_id: str
    max_tokens: int
    message: str

class ToolCall(BaseModel):
    """tool call model"""
    name: str
    input: Dict[str, Any]

class ChatResponse(BaseModel):
    """chat response model"""
    response: str
    tool_calls: Optional[List[ToolCall]] = None


def get_user_model() -> str:
    """load user model"""
    try:
        if not os.path.exists(USER_MODEL_FILE):
            logger.debug("user model setting not found, return default value")
            return "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        
        with open(USER_MODEL_FILE, "r") as f:
            data = json.load(f)
            model_id = data.get("model_id", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
            logger.debug(f"user model load success: {model_id}")
            return model_id
    except Exception as e:
        logger.error(f"user model load failed: {e}")
        return "us.anthropic.claude-3-7-sonnet-20250219-v1:0"

def process_slash_command(message: str, files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Process slash commands and return command context
    
    Args:
        message: Original message with slash command
        files: List of uploaded files
        
    Returns:
        Dictionary with command info and processed message, or None if not a valid command
    """
    try:
        # Extract command and arguments
        parts = message.split(' ', 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Unknown command
        return None
        
    except Exception as e:
        logger.error(f"Error processing slash command: {e}")
        return None

def load_model_config(model_id: str) -> Dict[str, Any]:
    """load model configuration"""
    try:
        if not os.path.exists(MODELS_CONFIG_PATH):
            logger.error(f"model configuration file not found: {MODELS_CONFIG_PATH}")
            return {"max_output_tokens": 4096}
        
        with open(MODELS_CONFIG_PATH, "r") as f:
            models_config = yaml.safe_load(f)
        
        # search model configuration
        for provider_id, provider_data in models_config.get("providers", {}).items():
            for model_config_id, model_data in provider_data.get("models", {}).items():
                if model_data.get("id") == model_id:
                    logger.debug(f"model configuration load success: {model_id}")
                    return model_data
        
        logger.warning(f"no configuration found for specified model ID: {model_id}")
        return {"max_output_tokens": 4096}
    except Exception as e:
        logger.error(f"model configuration load failed: {e}")
        return {"max_output_tokens": 4096}

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
    chat API endpoint
    
    Args:
        request: HTTP request
        message: user message text
        stream: streaming response flag
        model_id: model ID to use
        index_id: Index ID for context
        document_id: Document ID for context
        segment_id: Segment ID for context  
        files: list of attachment files
        
    Returns:
        chat response or streaming response
    """
    try:
        # check if request is JSON or FormData
        content_type = request.headers.get("content-type", "")
        logger.info(f"request Content-Type: {content_type}")
        
        # handle JSON request
        if "application/json" in content_type:
            request_data = await request.json()
            message = request_data.get("message", "")
            stream = request_data.get("stream", True)
            model_id = request_data.get("model_id", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
            index_id = request_data.get("index_id")
            document_id = request_data.get("document_id")
            segment_id = request_data.get("segment_id")
            thread_id = request_data.get("thread_id")  # Extract thread_id from JSON
            files_data = None
            logger.info(f"JSON request processing: message length={len(message)}, streaming={stream}, model={model_id}, index_id={index_id}, thread_id={thread_id}")
            logger.info(f"🔍 [DEBUG] chat.py - Full request data: {request_data}")
        else:
            # FormData request
            logger.info(f"🎯 [PROJECT_CONTEXT] FormData request - index_id: {index_id}")
        
        # handle multipart/form-data request
        processed_files = []
        if files is not None and len(files) > 0:
            logger.info(f"file upload detected: {len(files)} files")
            for file in files:
                if file and file.filename and file.filename.strip():
                    try:
                        # read file content
                        file_data = await file.read()
                        file_size = len(file_data)
                        
                        logger.info(f"file read success: {file.filename} ({file_size / 1024:.2f} KB, {file.content_type})")
                        
                        # create file information
                        file_info = {
                            "name": file.filename,
                            "type": file.content_type or "",
                            "data": file_data,
                            "size": file_size
                        }
                        
                        processed_files.append(file_info)
                        logger.info(f"file added: {file.filename} ({file_size / 1024:.2f} KB)")
                    except Exception as e:
                        logger.error(f"file processing error: {file.filename if file else 'unknown'}, error: {str(e)}")
                        import traceback
                        logger.error(f"detailed error: {traceback.format_exc()}")
                        raise HTTPException(status_code=400, detail=f"error occurred during file upload: {file.filename if file and file.filename else 'unknown file'}")
        
        # process slash commands
        original_message = message
        command_context = None
        
        if message and message.startswith('/'):
            command_context = process_slash_command(message, processed_files)
            if command_context:
                message = command_context["processed_message"]
                logger.info(f"processed slash command: {command_context['command']} -> {message}")
        
        # auto-add image analysis prompt if image files are attached but no slash command is used
        if not command_context and processed_files:
            has_image = any(f.get("type", "").startswith("image/") for f in processed_files)
            if has_image:
                if not message.strip():
                    message = "Please analyze the attached images. Please provide a detailed description of the image's content and features."
                    logger.info("auto-added image analysis prompt for empty message")
                else:
                    # additional prompt for image analysis
                    image_analysis_prompt = "\n\n[Image analysis request: Please analyze the attached images and include the following - image content, technical features, quality status, improvement suggestions]"
                    message = message + image_analysis_prompt
                    logger.info("auto-added image analysis prompt to existing message")
        
        # validate message
        if not message and not processed_files:
            logger.warning("message and attachment files are both empty")
            raise HTTPException(status_code=400, detail="message or attachment files are required")
        
        # check model ID
        if not model_id:
            model_id = get_user_model()
            logger.info(f"use default model ID: {model_id}")
        
        # load model configuration
        model_config = load_model_config(model_id)
        max_tokens = model_config.get("max_output_tokens", 4096)
        logger.info(f"model configuration load: {model_id}, max_tokens={max_tokens}")
        
        # initialize agent
        global agent
        if 'agent' not in globals() or not agent:
            logger.info(f"agent initialization: model ID={model_id}, max_tokens={max_tokens}")
            agent = ReactAgent(model_id=model_id, max_tokens=max_tokens, mcp_json_path=MCP_CONFIG_PATH)
            # ReactAgent의 startup() 메서드를 호출하여 graph를 초기화
            await agent.startup()
            logger.info("ReactAgent startup completed successfully")
        
        # create message
        messages = [HumanMessage(content=message)]
        
        # Use provided thread_id or create a new one
        if not thread_id:
            if index_id:
                # use project-specific fixed thread_id (maintain conversation history)
                thread_id = f"thread_{index_id}"
                logger.info(f"create project-based thread ID: {thread_id}")
            else:
                # use default thread_id if index_id is not provided
                thread_id = f"thread_default_{id(request)}"
                logger.info(f"create default thread ID: {thread_id}")
        else:
            logger.info(f"using provided thread ID: {thread_id}")

        # create execution configuration
        config = RunnableConfig(
            configurable={
                "Configuration": Configuration(
                    mcp_tools=MCP_CONFIG_PATH,
                    index_id=index_id,
                ),
                "thread_id": thread_id
            }
        )
        
        # create input state
        input_state = InputState(messages=messages, index_id=index_id)
        
        # handle streaming response
        if stream:
            logger.info("streaming response processing")
            
            async def stream_response():
                """streaming response generator"""
                # track previous metadata state
                prev_metadata = {
                    "langgraph_node": "",
                    "langgraph_step": -1,
                    "type": ""
                }
                
                # track accumulated text (per node)
                accumulated_text = {}
                current_node_texts = {}
                
                # variables for tracking current step and node
                current_node = ""
                current_step = 0
                
                try:                    
                    # flag for interrupt detection
                    interrupt_occurred = False
                    
                    # tool_references are explicitly initialized after stream completion
                    
                    # 스트리밍 실행
                    async for chunk, metadata in agent.astream(
                        input_state,
                        config,
                        stream_mode="messages", 
                        files=processed_files,
                        index_id=index_id,
                        document_id=document_id,
                        segment_id=segment_id
                    ):
                        # Handle references metadata first (special case for None chunk)
                        if chunk is None and metadata and metadata.get("references"):
                            references = metadata["references"]
                            references_data = {
                                "references": references
                            }
                            logger.info(f"📋 Sending {len(references)} references to frontend")
                            yield f"data: {json.dumps(references_data)}\n\n"
                            continue
                        
                        # extract metadata (use default value if not found)
                        current_node = metadata.get("langgraph_node", current_node or "unknown")
                        current_step = metadata.get("langgraph_step", current_step or 0)
                        
                        # current metadata configuration
                        current_type = ""
                        
                        # infer type based on node
                        if current_node == "agent":
                            current_type = "ai_response"
                        elif current_node == "tools":
                            current_type = "tool_result"
                        else:
                            current_type = "unknown"
                        
                        # metadata can be changed during message processing, so update with current value
                        current_metadata = {
                            "langgraph_node": current_node,
                            "langgraph_step": current_step,
                            "type": current_type
                        }
                        
                        # detect node change (new step start)
                        node_changed = (
                            current_node != prev_metadata["langgraph_node"] or
                            current_step != prev_metadata["langgraph_step"]
                        )
                        
                        # create node key
                        node_key = f"{current_step}-{current_node}"
                        
                        # manage accumulated text for current node
                        if node_key not in current_node_texts:
                            current_node_texts[node_key] = ""
                            # initialize accumulated text for new node
                            accumulated_text[node_key] = ""
                        
                        # process message chunk
                        if hasattr(chunk, "content") and chunk.content:
                            response_content = chunk.content
                            
                            # handle image data in metadata (pace-mcp-client style)
                            if metadata.get("is_image", False) and metadata.get("image_data"):
                                current_metadata["type"] = "image"
                                
                                response_data = {
                                    "chunk": [{
                                        "type": "image",
                                        "image_data": metadata["image_data"],
                                        "mime_type": metadata.get("mime_type", "image/png"),
                                        "index": 0
                                    }],
                                    "toolCalls": None,
                                    "metadata": current_metadata
                                }
                                
                                # update metadata state
                                prev_metadata = current_metadata.copy()
                                
                                yield f"data: {json.dumps(response_data)}\n\n"
                                continue
                            
                            # handle list content (advanced streaming format)
                            if isinstance(response_content, list):
                                for item in response_content:
                                    if isinstance(item, dict):
                                        item_type = item.get("type", "")
                                        
                                        # update current metadata type based on message type
                                        if item_type == "text":
                                            current_type = "ai_response"
                                        elif item_type == "tool_use":
                                            current_type = "tool_use"
                                        elif item_type == "tool_result":
                                            current_type = "tool_result"
                                        
                                        # update current metadata
                                        current_metadata["type"] = current_type
                                        
                                        # handle text type
                                        if item_type == "text":
                                            # update current node text
                                            current_node_texts[node_key] += item.get("text", "")
                                            
                                            response_data = {
                                                "chunk": [item],
                                                "toolCalls": None,
                                                "metadata": current_metadata
                                            }
                                            
                                            # update accumulated text
                                            accumulated_text[node_key] = current_node_texts[node_key]
                                            
                                            # update metadata state
                                            prev_metadata = current_metadata.copy()
                                            
                                            yield f"data: {json.dumps(response_data)}\n\n"
                                        
                                        # handle tool use
                                        elif item_type == "tool_use":
                                            response_data = {
                                                "chunk": [item],
                                                "toolCalls": None,
                                                "metadata": current_metadata
                                            }
                                            
                                            # update metadata state
                                            prev_metadata = current_metadata.copy()
                                            
                                            yield f"data: {json.dumps(response_data)}\n\n"
                                        
                                        # handle tool result
                                        elif item_type == "tool_result":
                                            response_data = {
                                                "chunk": [item],
                                                "toolCalls": None,
                                                "metadata": current_metadata
                                            }
                                            
                                            # update metadata state
                                            prev_metadata = current_metadata.copy()
                                            
                                            yield f"data: {json.dumps(response_data)}\n\n"
                            
                            # handle tool result (string)
                            elif isinstance(response_content, str):
                                # update current node text
                                if node_key not in current_node_texts:
                                    current_node_texts[node_key] = ""
                                    # initialize accumulated text for new node
                                    accumulated_text[node_key] = ""
                                
                                current_node_texts[node_key] += response_content
                                
                                # handle tool node
                                if current_node == "tools":
                                    current_metadata["type"] = "tool_result"
                                    
                                    # Check if tool result contains image data
                                    try:
                                        tool_result_data = json.loads(response_content)
                                        if isinstance(tool_result_data, dict) and tool_result_data.get("type") == "image":
                                            # Handle image tool result
                                            logger.info(f"🖼️ Detected image in tool result")
                                            current_metadata["type"] = "image"
                                            current_metadata["is_image"] = True
                                            current_metadata["image_data"] = tool_result_data.get("image_data", "")
                                            current_metadata["mime_type"] = tool_result_data.get("mime_type", "image/png")
                                            
                                            response_data = {
                                                "chunk": [{
                                                    "type": "image",
                                                    "image_data": tool_result_data.get("image_data", ""),
                                                    "mime_type": tool_result_data.get("mime_type", "image/png"),
                                                    "index": 0
                                                }],
                                                "toolCalls": None,
                                                "metadata": current_metadata
                                            }
                                        else:
                                            # Regular tool result
                                            response_data = {
                                                "chunk": [{
                                                    "type": "tool_result",
                                                    "text": response_content,
                                                    "index": 0
                                                }],
                                                "toolCalls": None,
                                                "metadata": current_metadata
                                            }
                                    except (json.JSONDecodeError, TypeError):
                                        # If not valid JSON, treat as regular tool result
                                        response_data = {
                                            "chunk": [{
                                                "type": "tool_result",
                                                "text": response_content,
                                                "index": 0
                                            }],
                                            "toolCalls": None,
                                            "metadata": current_metadata
                                        }
                                else:
                                    # convert string to text item format
                                    response_data = {
                                        "chunk": [{
                                            "type": "text",
                                            "text": response_content,
                                            "index": 0
                                        }],
                                        "toolCalls": None,
                                        "metadata": current_metadata
                                    }
                                
                                # update accumulated text
                                accumulated_text[node_key] = current_node_texts[node_key]
                                
                                # update metadata state
                                prev_metadata = current_metadata.copy()
                                
                                yield f"data: {json.dumps(response_data)}\n\n"
                            
                            # handle tool call
                            elif hasattr(chunk, "tool_calls") and chunk.tool_calls:
                                # send tool calls if any
                                tool_calls = []
                                for tool_call in chunk.tool_calls:
                                    tool_calls.append({
                                        "name": tool_call.get("name", ""),
                                        "input": tool_call.get("args", {})
                                    })
                                
                                # set tool call metadata
                                current_metadata["type"] = "tool_use"
                                
                                # convert tool call information to tool use item
                                tool_use_items = []
                                for i, tool_call in enumerate(tool_calls):
                                    tool_use_items.append({
                                        "type": "tool_use",
                                        "name": tool_call["name"],
                                        "input": json.dumps(tool_call["input"]),
                                        "id": f"tooluse_{i}",
                                        "index": i
                                    })
                                
                                response_data = {
                                    "chunk": tool_use_items,
                                    "toolCalls": None,
                                    "metadata": current_metadata
                                }
                                
                                # update metadata state
                                prev_metadata = current_metadata.copy()
                                
                                yield f"data: {json.dumps(response_data)}\n\n"
                        
                        # handle ToolMessage (tool result)
                        elif hasattr(chunk, "content") and hasattr(chunk, "tool_call_id"):
                            # ToolMessage processing
                            response_content = chunk.content
                            current_metadata["type"] = "tool_result"
                            
                            # Check if tool result contains image data
                            try:
                                tool_result_data = json.loads(response_content)
                                if isinstance(tool_result_data, dict) and tool_result_data.get("type") == "image":
                                    # Handle image tool result
                                    logger.info(f"🖼️ Detected image in tool result")
                                    current_metadata["type"] = "image"
                                    current_metadata["is_image"] = True
                                    current_metadata["image_data"] = tool_result_data.get("image_data", "")
                                    current_metadata["mime_type"] = tool_result_data.get("mime_type", "image/png")
                                    
                                    response_data = {
                                        "chunk": [{
                                            "type": "image",
                                            "image_data": tool_result_data.get("image_data", ""),
                                            "mime_type": tool_result_data.get("mime_type", "image/png"),
                                            "index": 0
                                        }],
                                        "toolCalls": None,
                                        "metadata": current_metadata
                                    }
                                else:
                                    # Regular tool result
                                    response_data = {
                                        "chunk": [{
                                            "type": "tool_result",
                                            "text": response_content,
                                            "index": 0
                                        }],
                                        "toolCalls": None,
                                        "metadata": current_metadata
                                    }
                            except (json.JSONDecodeError, TypeError):
                                # If not valid JSON, treat as regular tool result
                                response_data = {
                                    "chunk": [{
                                        "type": "tool_result",
                                        "text": response_content,
                                        "index": 0
                                    }],
                                    "toolCalls": None,
                                    "metadata": current_metadata
                                }
                            
                            # update metadata state
                            prev_metadata = current_metadata.copy()
                            
                            yield f"data: {json.dumps(response_data)}\n\n"
                        
                        # handle case where message content is empty but metadata is present (step transition, etc.)
                        elif metadata:
                            # send empty message with only metadata
                            response_data = {
                                "chunk": [],
                                "toolCalls": None,
                                "metadata": current_metadata
                            }
                            
                            # update metadata state
                            prev_metadata = current_metadata.copy()
                            
                            yield f"data: {json.dumps(response_data)}\n\n"
                    
                    # check interrupt state after stream completion
                    logger.info(f"Stream ended - checking for interrupts. interrupt_occurred: {interrupt_occurred}")
                    if not interrupt_occurred:
                        try:
                            # check current state of the graph directly
                            thread_id = config.get("configurable", {}).get("thread_id", "")
                            logger.info(f"Checking interrupt state for thread_id: {thread_id}")
                            
                            if thread_id:
                                # simple method: use graph's get_state method
                                state_snapshot = agent.graph.get_state(config)
                                # logger.info(f"State snapshot: {state_snapshot}")
                                
                                if state_snapshot and hasattr(state_snapshot, 'next'):
                                    logger.info(f"State has next attribute: {state_snapshot.next}")
                                    
                                    if state_snapshot.next:
                                        logger.info(f"Interrupt detected - next nodes: {state_snapshot.next}")
                                        
                                        # check if tool usage is pending
                                        if "tools" in state_snapshot.next:
                                            logger.info("Tool execution interrupt detected - waiting for approval")
                                            
                                            # send interrupt signal to frontend
                                            interrupt_data = {
                                                "chunk": [],
                                                "toolCalls": None,
                                                "metadata": {
                                                    "langgraph_node": "interrupt",
                                                    "langgraph_step": current_step,
                                                    "type": "interrupt",
                                                    "requires_approval": True,
                                                    "thread_id": thread_id
                                                }
                                            }
                                            yield f"data: {json.dumps(interrupt_data)}\n\n"
                                            
                                            # do not send [DONE] signal in interrupt state
                                            logger.info("Tool approval required - streaming paused")
                                            return
                                        else:
                                            logger.info(f"No tools in next nodes: {state_snapshot.next}")
                                    else:
                                        logger.info("No next nodes - execution completed normally")
                                else:
                                    logger.info("State snapshot has no next attribute or is None")
                            else:
                                logger.warning("No thread_id found in config")
                        except Exception as checkpoint_error:
                            logger.error(f"Error checking interrupt state: {checkpoint_error}")
                            import traceback
                            logger.error(f"Traceback: {traceback.format_exc()}")
                            # continue even if error occurs
                
                except Exception as e:
                    # GraphInterrupt exception handling (tool approval required)
                    if "GraphInterrupt" in str(type(e)) or "Tool execution requires user approval" in str(e):
                        logger.info(f"Tool approval interrupt detected: {e}")
                        
                        # send interrupt signal to frontend
                        thread_id = config.get("configurable", {}).get("thread_id", "")
                        interrupt_data = {
                            "chunk": [],
                            "toolCalls": None,
                            "metadata": {
                                "langgraph_node": "interrupt",
                                "langgraph_step": current_step,
                                "type": "interrupt", 
                                "requires_approval": True,
                                "thread_id": thread_id
                            }
                        }
                        yield f"data: {json.dumps(interrupt_data)}\n\n"
                        
                        # do not send [DONE] signal in interrupt state
                        logger.info("Tool approval required - streaming paused")
                        return
                    
                    logger.error(f"streaming processing error: {e}")
                    import traceback
                    logger.error(f"detailed stack trace: {traceback.format_exc()}")
                    error_data = {
                        "error": str(e),
                        "metadata": {
                            "langgraph_node": "error",
                            "langgraph_step": current_step,
                            "type": "error"
                        }
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                
                # Send references before the DONE signal (only if tools were actually used)
                try:
                    thread_id = config.get("configurable", {}).get("thread_id", "")
                    if thread_id:
                        state_snapshot = agent.graph.get_state(config)
                        if state_snapshot and hasattr(state_snapshot, 'values'):
                            tool_references = state_snapshot.values.get('tool_references', [])
                            logger.info(f"Raw tool_references from state: {len(tool_references)} items")
                            logger.info(f"Raw tool_references content: {tool_references[:2] if tool_references else 'Empty'}")
                            
                            # filtering: do not send __clear__ markers or empty references
                            valid_references = [ref for ref in tool_references if not (isinstance(ref, dict) and ref.get('__clear__'))]
                            logger.info(f"Valid references after filtering: {len(valid_references)} items")
                            
                            if valid_references:
                                logger.info(f"Sending {len(valid_references)} valid references to frontend")
                                references_data = {
                                    "chunk": [],
                                    "toolCalls": None,
                                    "metadata": {
                                        "langgraph_node": "references",
                                        "langgraph_step": 0,
                                        "type": "references",
                                        "references": valid_references
                                    }
                                }
                                yield f"data: {json.dumps(references_data)}\n\n"
                            else:
                                logger.info("No valid references to send - skipping reference transmission")
                            
                            # explicitly initialize tool_references after stream completion (for next request)
                            logger.info(f"Clearing tool_references for thread_id: {thread_id} after sending.")
                            final_config = RunnableConfig(configurable={"thread_id": thread_id})
                            agent.graph.update_state(final_config, {"tool_references": []})
                            
                except Exception as ref_error:
                    logger.error(f"Error sending references: {ref_error}")
                
                # streaming end signal
                yield "data: [DONE]\n\n"
                logger.info("streaming response completed")
            
            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream"
            )
        
        # handle normal response (non-streaming)
        else:
            logger.info("normal response processing")
            response = await agent.ainvoke(input_state, config, files=processed_files, index_id=index_id)
            
            # extract response message
            if "messages" in response and response["messages"]:
                last_message = response["messages"][-1]
                response_content = last_message.content if hasattr(last_message, "content") else ""
                
                # extract tool call information
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
                return ChatResponse(response="unable to generate response")
    
    except Exception as e:
        logger.error(f"chat processing error: {e}")
        import traceback
        logger.error(f"detailed error trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"error occurred during chat processing: {str(e)}")

@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    message: str = Form(None),
    model_id: str = Form("us.anthropic.claude-3-7-sonnet-20250219-v1:0"),
    index_id: Optional[str] = Form(None),
    thread_id: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None)
):
    """
    chat streaming API endpoint
    
    Args:
        request: HTTP request
        message: user message text
        model_id: model ID to use
        index_id: Index ID for context
        files: list of attachment files
        
    Returns:
        streaming response
    """
    # Check if request is JSON or FormData
    content_type = request.headers.get("content-type", "")
    logger.info(f"chat/stream request Content-Type: {content_type}")
    
    # Handle JSON request
    if "application/json" in content_type:
        request_data = await request.json()
        message = request_data.get("message", "")
        model_id = request_data.get("model_id", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
        index_id = request_data.get("index_id")
        thread_id = request_data.get("thread_id")
        files = []  # JSON requests don't have files
        logger.info(f"JSON chat/stream request: message={message[:50]}..., model_id={model_id}, index_id={index_id}, thread_id={thread_id}")
    else:
        # FormData request (files may be present)
        logger.info(f"FormData chat/stream request: message={message}, model_id={model_id}, index_id={index_id}, thread_id={thread_id}, files={len(files) if files else 0}")
    
    return await chat(request, message, True, model_id, index_id, thread_id, files)

@router.post("/chat/resume")
async def resume_chat(
    request: Request,
    conversation_id: str = Form(...),
    approved: bool = Form(...),
    tool_call_id: Optional[str] = Form(None),
    index_id: Optional[str] = Form(None)
):
    """
    chat resume API endpoint for tool approval
    
    Args:
        request: HTTP request
        conversation_id: conversation ID
        approved: approval status
        tool_call_id: tool call ID
        index_id: index ID for context
        
    Returns:
        streaming response after tool approval
    """
    try:
        # check if request is JSON or FormData
        content_type = request.headers.get("content-type", "")
        logger.info(f"resume request Content-Type: {content_type}")
        
        # handle JSON request
        if "application/json" in content_type:
            request_data = await request.json()
            conversation_id = request_data.get("conversation_id", "")
            approved = request_data.get("approved", False)
            tool_call_id = request_data.get("tool_call_id")
            index_id = request_data.get("index_id")
            logger.info(f"JSON resume request: conversation_id={conversation_id}, approved={approved}, tool_call_id={tool_call_id}, index_id={index_id}")
        
        # validate input
        if not conversation_id:
            logger.warning("conversation_id is required")
            raise HTTPException(status_code=400, detail="conversation_id is required")
        
        # initialize agent
        global agent
        if 'agent' not in globals() or not agent:
            model_id = get_user_model()
            model_config = load_model_config(model_id)
            max_tokens = model_config.get("max_output_tokens", 4096)
            logger.info(f"agent initialization for resume: model ID={model_id}, max_tokens={max_tokens}")
            agent = ReactAgent(model_id=model_id, max_tokens=max_tokens, mcp_json_path=MCP_CONFIG_PATH)
        
        # create thread ID from conversation ID
        thread_id = f"thread_{conversation_id}"
        logger.info(f"resume thread ID: {thread_id}")

        # create execution configuration with tool approval
        config = RunnableConfig(
            configurable={
                "Configuration": Configuration(
                    mcp_tools=MCP_CONFIG_PATH,
                    index_id=index_id,
                    tool_approved=approved,
                ),
                "thread_id": thread_id
            }
        )
        
        # create resume message based on approval
        if approved:
            resume_message = "Tool execution approved. Please continue."
        else:
            resume_message = "Tool execution rejected."
        
        # create input state for resume
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=resume_message)]
        input_state = InputState(messages=messages, index_id=index_id)
        
        # handle streaming response for resume
        logger.info("resume streaming response processing")
        
        async def stream_resume_response():
            """streaming resume response generator"""
            # track previous metadata state
            prev_metadata = {
                "langgraph_node": "",
                "langgraph_step": -1,
                "type": ""
            }
            
            # track accumulated text (per node)
            accumulated_text = {}
            current_node_texts = {}
            
            # variables for tracking current step and node
            current_node = ""
            current_step = 0
            
            try:
                logger.info(f"agent.astream resume call: index_id={index_id}")
                async for chunk, metadata in agent.astream(
                    input_state,
                    config,
                    stream_mode="messages",
                    files=[],
                    index_id=index_id
                ):
                    # extract metadata (use default value if not found)
                    current_node = metadata.get("langgraph_node", current_node or "unknown")
                    current_step = metadata.get("langgraph_step", current_step or 0)
                    
                    # current metadata configuration
                    current_type = ""
                    
                    # infer type based on node
                    if current_node == "agent":
                        current_type = "ai_response"
                    elif current_node == "tools":
                        current_type = "tool_result"
                    else:
                        current_type = "unknown"
                    
                    # metadata can be changed during message processing, so update with current value
                    current_metadata = {
                        "langgraph_node": current_node,
                        "langgraph_step": current_step,
                        "type": current_type
                    }
                    
                    # create node key
                    node_key = f"{current_step}-{current_node}"
                    
                    # manage accumulated text for current node
                    if node_key not in current_node_texts:
                        current_node_texts[node_key] = ""
                        accumulated_text[node_key] = ""
                    
                    # process message chunk
                    if hasattr(chunk, "content") and chunk.content:
                        response_content = chunk.content
                        
                        # handle tool result (string)
                        if isinstance(response_content, str):
                            current_node_texts[node_key] += response_content
                            
                            # handle tool node
                            if current_node == "tools":
                                current_metadata["type"] = "tool_result"
                                
                                # convert tool result (string) to text item format
                                response_data = {
                                    "chunk": [{
                                        "type": "tool_result",
                                        "text": response_content,
                                        "index": 0
                                    }],
                                    "toolCalls": None,
                                    "metadata": current_metadata
                                }
                            else:
                                # convert string to text item format
                                response_data = {
                                    "chunk": [{
                                        "type": "text",
                                        "text": response_content,
                                        "index": 0
                                    }],
                                    "toolCalls": None,
                                    "metadata": current_metadata
                                }
                            
                            # update accumulated text
                            accumulated_text[node_key] = current_node_texts[node_key]
                            
                            # update metadata state
                            prev_metadata = current_metadata.copy()
                            
                            yield f"data: {json.dumps(response_data)}\n\n"
            
            except Exception as e:
                logger.error(f"resume streaming processing error: {e}")
                import traceback
                logger.error(f"detailed stack trace: {traceback.format_exc()}")
                error_data = {
                    "error": str(e),
                    "metadata": {
                        "langgraph_node": "error",
                        "langgraph_step": current_step,
                        "type": "error"
                    }
                }
                yield f"data: {json.dumps(error_data)}\n\n"
            
            # streaming end signal
            yield "data: [DONE]\n\n"
            logger.info("resume streaming response completed")
        
        return StreamingResponse(
            stream_resume_response(),
            media_type="text/event-stream"
        )
        
    except Exception as e:
        logger.error(f"resume chat processing error: {e}")
        import traceback
        logger.error(f"detailed error trace: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"error occurred during resume chat processing: {str(e)}")

@router.post("/reinit")
async def reinit_agent(request: ReinitRequest = None):
    """
    agent reinitialization API endpoint
    
    Args:
        request: reinitialization request data (optional)
        
    Returns:
        reinitialization result
    """
    global agent
    
    try:
        # determine model ID (provided in request or loaded from user settings)
        model_id = request.model_id if request and request.model_id else get_user_model()
        
        # load model configuration
        model_config = load_model_config(model_id)
        max_tokens = model_config.get("max_output_tokens", 4096)
        
        logger.info(f"agent reinitialization: model_id={model_id}, max_tokens={max_tokens}")
        
        # if existing agent exists, clean up
        if agent:
            try:
                await agent.shutdown()
            except Exception as e:
                logger.warning(f"Failed to shutdown existing agent: {e}")
        
        # recreate agent
        agent = ReactAgent(model_id=model_id, max_tokens=max_tokens, mcp_json_path=MCP_CONFIG_PATH, reload_prompt=True)
        # start agent
        await agent.startup()
        
        # clear conversation history (based on index_id or thread_id)
        if request and request.index_id:
            # clear current thread based on index_id
            current_thread_id = f"thread_{request.index_id}"
            logger.info(f"🔄 Clearing conversation history for index_id: {request.index_id}, thread_id: {current_thread_id}")
            agent.clear_conversation_history(current_thread_id)
        elif request and request.thread_id:
            logger.info(f"🔄 Clearing conversation history for thread_id: {request.thread_id}")
            agent.clear_conversation_history(request.thread_id)
        else:
            # clear all conversation history (default behavior)
            logger.info("🔄 Clearing all conversation history (default)")
            agent.clear_conversation_history()
        
        return ReinitResponse(
            success=True,
            model_id=model_id,
            max_tokens=max_tokens,
            message="agent reinitialized successfully with conversation history cleared"
        )
    
    except Exception as e:
        logger.error(f"agent reinitialization error: {e}")
        # retry with default model if error occurs
        try:
            # if existing agent exists, clean up
            if agent:
                try:
                    await agent.shutdown()
                except Exception as shutdown_error:
                    logger.warning(f"Failed to shutdown existing agent during fallback: {shutdown_error}")
            
            model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
            agent = ReactAgent(model_id=model_id, max_tokens=64000, mcp_json_path=MCP_CONFIG_PATH)
            # start agent
            await agent.startup()
            
            # clear conversation history (based on index_id or thread_id)
            if request and request.index_id:
                # clear current thread based on index_id
                current_thread_id = f"thread_{request.index_id}"
                logger.info(f"🔄 [Fallback] Clearing conversation history for index_id: {request.index_id}, thread_id: {current_thread_id}")
                agent.clear_conversation_history(current_thread_id)
            elif request and request.thread_id:
                logger.info(f"🔄 [Fallback] Clearing conversation history for thread_id: {request.thread_id}")
                agent.clear_conversation_history(request.thread_id)
            else:
                logger.info("🔄 [Fallback] Clearing all conversation history (default)")
                agent.clear_conversation_history()
            
            return ReinitResponse(
                success=False,
                model_id=model_id,
                max_tokens=4096,
                message=f"error occurred after reinitialization, retry with default model (conversation history cleared): {str(e)}"
            )
        except Exception as fallback_error:
            logger.error(f"error occurred during reinitialization with default model: {fallback_error}")
            raise HTTPException(status_code=500, detail=f"agent reinitialization failed: {str(e)}")


# load model information when server starts
model_id = get_user_model()
model_config = load_model_config(model_id)
max_tokens = model_config.get("max_output_tokens", 4096)

# initialize agent when server starts
try:
    logger.info(f"agent initialization: model_id={model_id}, max_tokens={max_tokens}")
    # agent is initialized on the first request
    # MCPService is initialized in the FastAPI startup event
except Exception as e:
    logger.error(f"agent initialization preparation failed: {e}")
    logger.warning("agent will be initialized on the first request")
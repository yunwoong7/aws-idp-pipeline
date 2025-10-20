"""
Strands Analysis Agent - Main Agent Implementation
"""
import logging
import asyncio
import sys
import os
from typing import Dict, Any, List, Optional, AsyncGenerator, Tuple
from datetime import datetime
from strands import Agent
from strands.multiagent import GraphBuilder
from strands.session.file_session_manager import FileSessionManager

# Add current directory to Python path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from prompt import prompt_manager
from conversation_manager import ConversationManager

# Import tools directly from the tools module
from tools.analysis_tools import (
    hybrid_search,
    get_document_info,
    get_page_analysis_details,
    get_segment_image_attachment
)

logger = logging.getLogger(__name__)

class AnalysisAgent:
    """
    Strands SDK based Analysis Agent
    """
    
    def __init__(
        self, 
        model_id: str = "",
        max_tokens: int = 4096, 
        mcp_json_path: str = "",
        reload_prompt: bool = False
    ):
        """
        Initialize Analysis Agent
        
        Args:
            model_id: Model ID to use
            max_tokens: Maximum number of tokens
            mcp_json_path: MCP configuration file path (not used, for compatibility)
            reload_prompt: Whether to reload prompt cache
        """
        # Load configuration
        self.config = config
        self.model_id = model_id or config.get_user_model()
        
        # Load model configuration
        model_config = config.load_model_config(self.model_id)
        self.max_tokens = model_config.get("max_output_tokens", 64000)
        
        # Initialize prompt manager
        if reload_prompt:
            global prompt_manager
            from prompt import PromptManager
            prompt_manager = PromptManager(reload=True)
        
        # Initialize tools list
        self.tools = [
            hybrid_search,
            get_document_info,
            get_page_analysis_details,
            get_segment_image_attachment
        ]
        
        # Initialize conversation manager
        self.conversation_manager = ConversationManager()
        
        # Session management
        self.sessions = {}
        
        # Initialize main agent (will be created in startup)
        self.agent = None
        self.graph = None
        
        logger.info(f"Initialized AnalysisAgent with model: {self.model_id}")
    
    
    async def startup(self):
        """Initialize and start the agent"""
        try:
            # Get system prompt with enhanced formatting
            system_prompt = prompt_manager.format_system_prompt(
                'agent_profile',
                variables={
                    'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            )
            
            # Create main Strands agent with tools
            self.agent = Agent(
                name="analysis_agent",
                system_prompt=system_prompt,
                tools=self.tools,
                model=self.model_id,
                callback_handler=None  # Disable default output for API compatibility
            )
            
            logger.info(f"Agent initialized with {len(self.tools)} tools")
            
            # Build graph structure for complex workflows
            self._build_graph()
            
            logger.info("AnalysisAgent startup completed")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            raise
    
    def _build_graph(self):
        """Build graph structure for agent workflow"""
        builder = GraphBuilder()
        
        # Add main agent as the primary node
        builder.add_node(self.agent, "main")
        
        # Set entry point
        builder.set_entry_point("main")
        
        # Build the graph
        self.graph = builder.build()
        
        logger.info("Graph structure built successfully")
    
    async def shutdown(self):
        """Shutdown the agent and cleanup resources"""
        try:
            # MCP client cleanup is handled by context manager
            logger.info("AnalysisAgent shutdown completed")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def get_or_create_session(self, thread_id: str) -> FileSessionManager:
        """Get or create a session manager for the thread"""
        if thread_id not in self.sessions:
            self.sessions[thread_id] = FileSessionManager(
                session_id=thread_id,
                storage_dir="/tmp/strands_sessions"
            )
        return self.sessions[thread_id]
    
    async def ainvoke(
        self,
        input_state: Any,
        config: Dict[str, Any],
        files: Optional[List[Dict[str, Any]]] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke agent asynchronously (non-streaming)
        
        Args:
            input_state: Input state with messages
            config: Configuration dict
            files: Optional list of files
            index_id: Optional index ID
            document_id: Optional document ID
            segment_id: Optional segment ID
            
        Returns:
            Response dictionary
        """
        try:
            # Extract thread_id from config
            thread_id = config.get("configurable", {}).get("thread_id", "default")
            
            # Get or create session
            session = self.get_or_create_session(thread_id)
            
            # Extract message from input_state
            message = ""
            if hasattr(input_state, 'messages') and input_state.messages:
                message = input_state.messages[0].content
            
            # Format instruction with context
            instruction = prompt_manager.format_instruction(
                'agent_profile',
                variables={
                    'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'INDEX_ID': index_id or '',
                    'DOCUMENT_ID': document_id or '',
                    'SEGMENT_ID': segment_id or '',
                    'QUERY': message,
                    'CONVERSATION_HISTORY': self.conversation_manager.get_history(thread_id),
                    'CONTENT': '',
                    'REFERENCES': ''
                }
            )
            
            # Update agent with session
            self.agent.session_manager = session
            
            # Execute through graph for workflow support
            result = await self.graph.invoke_async(instruction)
            
            # Extract response from result
            response_text = ""
            if result and result.results:
                main_result = result.results.get("main")
                if main_result and main_result.result:
                    response_text = str(main_result.result.message)
            
            # Update conversation history
            self.conversation_manager.add_message(thread_id, "user", message)
            self.conversation_manager.add_message(thread_id, "assistant", response_text)
            
            # Return in expected format
            from types import SimpleNamespace
            response_msg = SimpleNamespace(content=response_text, tool_calls=[])
            
            return {
                "messages": [response_msg]
            }
            
        except Exception as e:
            logger.error(f"Error in ainvoke: {e}")
            # Return error response instead of using handle_errors
            from types import SimpleNamespace
            error_msg = SimpleNamespace(content=f"Error: {str(e)}")
            return {"messages": [error_msg]}
    
    async def astream(
        self,
        input_state: Any,
        config: Dict[str, Any],
        stream_mode: str = "messages",
        files: Optional[List[Dict[str, Any]]] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None
    ) -> AsyncGenerator[Tuple[Any, Dict[str, Any]], None]:
        """
        Stream agent responses with proper tool execution flow
        
        Args:
            input_state: Input state with messages
            config: Configuration dict
            stream_mode: Streaming mode
            files: Optional list of files
            index_id: Optional index ID
            document_id: Optional document ID
            segment_id: Optional segment ID
            
        Yields:
            Tuple of (chunk, metadata)
        """
        try:
            # Extract thread_id from config
            thread_id = config.get("configurable", {}).get("thread_id", "default")
            
            # Get or create session
            session = self.get_or_create_session(thread_id)
            
            # Extract message from input_state
            message = ""
            if hasattr(input_state, 'messages') and input_state.messages:
                message = input_state.messages[0].content
            
            # Format instruction with context
            instruction = prompt_manager.format_instruction(
                'agent_profile',
                variables={
                    'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'INDEX_ID': index_id or '',
                    'DOCUMENT_ID': document_id or '',
                    'SEGMENT_ID': segment_id or '',
                    'QUERY': message,
                    'CONVERSATION_HISTORY': self.conversation_manager.get_history(thread_id),
                    'CONTENT': '',
                    'REFERENCES': ''
                }
            )
            
            # Update agent with session
            self.agent.session_manager = session

            # Build multimodal input if image files are attached
            agent_input = instruction
            try:
                if files and isinstance(files, list) and len(files) > 0:
                    content_blocks = []
                    from io import BytesIO
                    try:
                        from PIL import Image
                    except Exception:
                        Image = None
                    for f in files:
                        try:
                            content_type = (f.get("type") or "").lower()
                            raw_bytes = f.get("data")
                            if not raw_bytes or not isinstance(raw_bytes, (bytes, bytearray)):
                                continue
                            if content_type.startswith("image/"):
                                image_format = "png"
                                if "jpeg" in content_type or "jpg" in content_type:
                                    image_format = "jpeg"
                                elif "png" in content_type:
                                    image_format = "png"

                                processed = raw_bytes
                                if Image is not None:
                                    try:
                                        img = Image.open(BytesIO(raw_bytes))
                                        MAX_DIM = 1024
                                        MAX_SIZE = 4 * 1024 * 1024
                                        w, h = img.size
                                        if w > MAX_DIM or h > MAX_DIM:
                                            ar = w / h
                                            if w >= h:
                                                nw = MAX_DIM
                                                nh = int(nw / ar)
                                            else:
                                                nh = MAX_DIM
                                                nw = int(nh * ar)
                                            img = img.resize((nw, nh), Image.LANCZOS)
                                        out = BytesIO()
                                        if image_format == "png":
                                            img.save(out, format="PNG", optimize=True)
                                        else:
                                            if img.mode not in ("RGB", "L"):
                                                img = img.convert("RGB")
                                            img.save(out, format="JPEG", quality=85, optimize=True)
                                        processed = out.getvalue()
                                        if len(processed) > MAX_SIZE:
                                            out = BytesIO()
                                            if image_format == "png":
                                                img.save(out, format="PNG", optimize=True, compress_level=9)
                                            else:
                                                if img.mode not in ("RGB", "L"):
                                                    img = img.convert("RGB")
                                                img.save(out, format="JPEG", quality=70, optimize=True)
                                            processed = out.getvalue()
                                    except Exception:
                                        processed = raw_bytes

                                content_blocks.append({
                                    "image": {
                                        "format": image_format,
                                        "source": {"bytes": processed}
                                    }
                                })
                        except Exception:
                            continue

                    # Append text instruction at the end
                    content_blocks.append({"text": instruction})
                    agent_input = content_blocks
            except Exception:
                agent_input = instruction

            # Tracking variables for proper flow
            current_step = 0
            current_node = "agent"
            tool_use_step = None
            accumulated_tool_input = ""
            current_tool_name = None
            current_tool_id = None
            tool_use_yielded = False
            
            # Stream through agent
            async for event in self.agent.stream_async(agent_input):
                # Handle current_tool_use events (streaming tool input)
                if "current_tool_use" in event:
                    tool_info = event["current_tool_use"]
                    tool_name = tool_info.get("name", "")
                    tool_input = tool_info.get("input", "")
                    tool_use_id = tool_info.get("toolUseId", "")
                    
                    # Check if this is the start of a new tool use
                    if tool_name and tool_name != current_tool_name:
                        # Step 전환 시 구분자 추가
                        if current_step > 0:
                            from types import SimpleNamespace
                            separator = SimpleNamespace(content="\n\n")
                            sep_metadata = {
                                "strands_node": "agent",
                                "strands_step": current_step,
                                "type": "step_separator"
                            }
                            yield (separator, sep_metadata)
                        
                        current_tool_name = tool_name
                        current_tool_id = tool_use_id
                        accumulated_tool_input = ""
                        tool_use_yielded = False
                        current_node = "tools"
                        current_step += 1
                        tool_use_step = current_step
                    
                    # Accumulate tool input
                    if tool_input:
                        accumulated_tool_input = tool_input
                        
                        # Try to parse as JSON to see if complete
                        try:
                            import json
                            parsed_input = json.loads(accumulated_tool_input)
                            
                            # Tool input is complete JSON, yield it if not already yielded
                            if not tool_use_yielded and current_tool_name:
                                from types import SimpleNamespace
                                tool_use_chunk = SimpleNamespace(
                                    content="",
                                    tool_calls=[{
                                        "name": current_tool_name,
                                        "args": parsed_input,
                                        "id": current_tool_id or f"tool_{current_step}"
                                    }]
                                )
                                
                                metadata = {
                                    "strands_node": current_node,
                                    "strands_step": current_step,
                                    "type": "tool_use"
                                }
                                
                                yield (tool_use_chunk, metadata)
                                tool_use_yielded = True
                                
                        except json.JSONDecodeError:
                            # Input is still building, continue accumulating
                            pass
                
                # Handle message events that contain tool results
                elif "message" in event:
                    message_data = event["message"]
                    
                    # Check if this is a user message with tool results
                    if message_data.get("role") == "user" and "content" in message_data:
                        content = message_data["content"]
                        if isinstance(content, list):
                            for item in content:
                                if "toolResult" in item and tool_use_step is not None:
                                    tool_result = item["toolResult"]
                                    
                                    # Extract result content and check for image signals
                                    result_content = "Tool execution completed"
                                    
                                    # Handle different tool result structures
                                    content_items = []
                                    
                                    if isinstance(tool_result, dict):
                                        if "content" in tool_result and isinstance(tool_result["content"], list):
                                            content_items = tool_result["content"]
                                        elif "status" in tool_result and tool_result["status"] == "error":
                                            result_content = f"Tool error: {tool_result.get('error', 'Unknown error')}"
                                    elif isinstance(tool_result, list):
                                        # Direct list format from tool
                                        content_items = tool_result
                                    
                                    # Extract result content and detect image URL signal
                                    image_url_signal = None
                                    for content_item in content_items:
                                        if isinstance(content_item, dict):
                                            # 1) detect special marker text
                                            if "text" in content_item and isinstance(content_item["text"], str):
                                                text_val = content_item["text"].strip()
                                                if text_val == "[[SEGMENT_IMAGE_URL]]":
                                                    # marker: skip showing
                                                    continue
                                                # If text contains serialized list/dict, try to parse and extract signal
                                                if (text_val.startswith("[") and text_val.endswith("]")) or (text_val.startswith("{") and text_val.endswith("}")):
                                                    try:
                                                        import json, ast as _ast
                                                        parsed = None
                                                        try:
                                                            parsed = json.loads(text_val)
                                                        except Exception:
                                                            parsed = _ast.literal_eval(text_val)
                                                        # normalize to list
                                                        parsed_items = parsed if isinstance(parsed, list) else [parsed]
                                                        for p in parsed_items:
                                                            if isinstance(p, dict) and "json" in p and isinstance(p["json"], dict):
                                                                if p["json"].get("type") == "segment_image_url":
                                                                    image_url_signal = p["json"]
                                                                    break
                                                        # Do not set result_content from serialized wrapper
                                                        continue
                                                    except Exception:
                                                        # fall back to plain text
                                                        result_content = content_item["text"]
                                                else:
                                                    result_content = content_item["text"]
                                            # 2) detect json payload for segment image url
                                            if "json" in content_item and isinstance(content_item["json"], dict):
                                                json_payload = content_item["json"]
                                                if json_payload.get("type") == "segment_image_url":
                                                    image_url_signal = json_payload
                                                    # keep scanning to also capture any human-readable text
                                    
                                    # If we detected an image URL signal, emit a dedicated metadata event
                                    if image_url_signal is not None:
                                        from types import SimpleNamespace
                                        signal_chunk = SimpleNamespace(content="")
                                        signal_metadata = {
                                            "strands_node": "tools",
                                            "strands_step": tool_use_step,
                                            "type": "image_url_signal",
                                            "image": image_url_signal
                                        }
                                        yield (signal_chunk, signal_metadata)
                                        
                                        # Download image and stream as multimodal content to the agent
                                        try:
                                            import requests
                                            from io import BytesIO
                                            from PIL import Image
                                            
                                            image_url = image_url_signal.get("url")
                                            mime_type = image_url_signal.get("mime_type", "image/png")
                                            if not image_url:
                                                raise ValueError("Image URL not provided in signal")
                                            
                                            img_resp = requests.get(image_url, timeout=30)
                                            img_resp.raise_for_status()
                                            raw_image_data = img_resp.content
                                            
                                            # Optimize image size conservatively, keep original format if possible
                                            processed_image_data = raw_image_data
                                            image_format = "png" if "png" in mime_type else ("jpeg" if ("jpeg" in mime_type or "jpg" in mime_type) else "png")
                                            try:
                                                MAX_IMAGE_DIMENSION = 1024
                                                MAX_IMAGE_SIZE = 4 * 1024 * 1024
                                                img = Image.open(BytesIO(raw_image_data))
                                                original_width, original_height = img.size
                                                if original_width > MAX_IMAGE_DIMENSION or original_height > MAX_IMAGE_DIMENSION:
                                                    aspect_ratio = original_width / original_height
                                                    if original_width >= original_height:
                                                        new_width = MAX_IMAGE_DIMENSION
                                                        new_height = int(new_width / aspect_ratio)
                                                    else:
                                                        new_height = MAX_IMAGE_DIMENSION
                                                        new_width = int(new_height * aspect_ratio)
                                                    img = img.resize((new_width, new_height), Image.LANCZOS)
                                                    output = BytesIO()
                                                    if image_format == "png":
                                                        img.save(output, format="PNG", optimize=True)
                                                    else:
                                                        if img.mode not in ("RGB", "L"):
                                                            img = img.convert("RGB")
                                                        img.save(output, format="JPEG", quality=85, optimize=True)
                                                    processed_image_data = output.getvalue()
                                                # Ensure under size cap
                                                if len(processed_image_data) > MAX_IMAGE_SIZE:
                                                    output = BytesIO()
                                                    if image_format == "png":
                                                        img.save(output, format="PNG", optimize=True, compress_level=9)
                                                    else:
                                                        if img.mode not in ("RGB", "L"):
                                                            img = img.convert("RGB")
                                                        img.save(output, format="JPEG", quality=70, optimize=True)
                                                    processed_image_data = output.getvalue()
                                            except Exception:
                                                # fallback to raw
                                                processed_image_data = raw_image_data
                                            
                                            # Prepare content blocks per Strands ContentBlock spec
                                            multimodal_message = [
                                                {
                                                    "image": {
                                                        "format": image_format,
                                                        "source": {
                                                            "bytes": processed_image_data
                                                        }
                                                    }
                                                },
                                                {
                                                    "text": f"Please analyze this image for segment {segment_id or ''} in document {document_id or ''}."
                                                }
                                            ]
                                            
                                            # Separate steps visually
                                            current_step += 1
                                            boundary_chunk2 = SimpleNamespace(content="\n\n---\n\n")
                                            boundary_metadata2 = {
                                                "strands_node": "agent",
                                                "strands_step": current_step,
                                                "type": "step_boundary"
                                            }
                                            yield (boundary_chunk2, boundary_metadata2)
                                            
                                            # Stream the multimodal follow-up
                                            async for img_event in self.agent.stream_async(multimodal_message):
                                                if "data" in img_event:
                                                    content2 = img_event["data"]
                                                    if content2:
                                                        chunk2 = SimpleNamespace(content=content2)
                                                        metadata2 = {
                                                            "strands_node": "agent",
                                                            "strands_step": current_step,
                                                            "type": "ai_response"
                                                        }
                                                        yield (chunk2, metadata2)
                                                elif "content_delta" in img_event:
                                                    delta2 = img_event["content_delta"]
                                                    text2 = delta2.get("text", "")
                                                    if text2:
                                                        chunk2 = SimpleNamespace(content=text2)
                                                        metadata2 = {
                                                            "strands_node": "agent",
                                                            "strands_step": current_step,
                                                            "type": "ai_response"
                                                        }
                                                        yield (chunk2, metadata2)
                                                elif "result" in img_event:
                                                    result2 = img_event["result"]
                                                    if result2 and hasattr(result2, 'message'):
                                                        # save into conversation history
                                                        self.conversation_manager.add_message(thread_id, "assistant", str(result2.message))
                                        
                                        except Exception as e:
                                            from types import SimpleNamespace
                                            err_chunk = SimpleNamespace(content=f"Error fetching image: {str(e)}")
                                            err_metadata = {
                                                "strands_node": "tools",
                                                "strands_step": tool_use_step,
                                                "type": "image_download_error"
                                            }
                                            yield (err_chunk, err_metadata)
                                    
                                    from types import SimpleNamespace
                                    tool_result_chunk = SimpleNamespace(content=str(result_content))
                                    
                                    metadata = {
                                        "strands_node": "tools",
                                        "strands_step": tool_use_step,
                                        "type": "tool_result"
                                    }
                                    
                                    yield (tool_result_chunk, metadata)
                                    
                                    # Reset tool tracking
                                    current_tool_name = None
                                    current_tool_id = None
                                    accumulated_tool_input = ""
                                    tool_use_yielded = False
                                    tool_use_step = None
                
                # AI response content
                elif "data" in event:
                    content = event["data"]
                    if content:  # Only yield if there's actual content
                        # Check if we're starting a new step
                        if current_node == "tools":
                            # Transitioning from tools back to agent means new step
                            current_node = "agent"
                            current_step += 1
                            
                            # Send a step boundary marker
                            from types import SimpleNamespace
                            boundary_chunk = SimpleNamespace(content="\n\n---\n\n")
                            boundary_metadata = {
                                "strands_node": "agent",
                                "strands_step": current_step,
                                "type": "step_boundary"
                            }
                            yield (boundary_chunk, boundary_metadata)
                        
                        from types import SimpleNamespace
                        chunk = SimpleNamespace(content=content)
                        
                        metadata = {
                            "strands_node": current_node,
                            "strands_step": current_step,
                            "type": "ai_response"
                        }
                        
                        yield (chunk, metadata)
                
                # Handle content_delta events (alternative format)
                elif "content_delta" in event:
                    delta = event["content_delta"]
                    text = delta.get("text", "")
                    if text:
                        from types import SimpleNamespace
                        chunk = SimpleNamespace(content=text)
                        
                        if current_node == "tools":
                            current_node = "agent"
                            current_step += 1
                        
                        metadata = {
                            "strands_node": current_node,
                            "strands_step": current_step,
                            "type": "ai_response"
                        }
                        
                        yield (chunk, metadata)
                
                elif "result" in event:
                    # Final result - update conversation history and handle pending images
                    result = event["result"]
                    if result and hasattr(result, 'message'):
                        self.conversation_manager.add_message(thread_id, "user", message)
                        self.conversation_manager.add_message(thread_id, "assistant", str(result.message))
                    
            
        except Exception as e:
            logger.error(f"Error in astream: {e}")
            # Yield error
            from types import SimpleNamespace
            error_chunk = SimpleNamespace(content=f"Error: {str(e)}")
            error_metadata = {
                "strands_node": "error",
                "strands_step": 0,
                "type": "error"
            }
            yield (error_chunk, error_metadata)
    
    def clear_conversation_history(self, thread_id: Optional[str] = None):
        """Clear conversation history for a thread or all threads"""
        if thread_id:
            self.conversation_manager.clear_history(thread_id)
            if thread_id in self.sessions:
                del self.sessions[thread_id]
            logger.info(f"Cleared conversation history for thread: {thread_id}")
        else:
            self.conversation_manager.clear_all()
            self.sessions.clear()
            logger.info("Cleared all conversation history")
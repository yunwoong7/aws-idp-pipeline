"""
ReactAgent - Main Class
"""
import os
import sys
import ast
import asyncio
import logging
from typing import Dict, List, Any, AsyncGenerator, Optional, Tuple
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from colorama import Fore, Style

from src.common.utils import process_attachments, create_message_with_attachments
from src.common.llm import get_llm
from src.mcp_client.mcp_service import MCPService
from src.monitoring.phoenix import setup_phoenix

from .state.model import InputState, State
from .prompt import prompt_manager
from .checkpoint import init_checkpointer, cleanup_checkpointer_data
from .graph_builder import GraphBuilder
from .metrics import get_metrics
from .logger_config import get_agent_logger
from .conversation_manager import ConversationManager
from .health_checker import MCPHealthChecker
from .utils.core_utils import normalize_content
from .error_handler import global_error_handler, handle_errors
from .config import config_manager

logger = logging.getLogger(__name__)


class ReactAgent:
    """
    Refactored LangGraph-based ReAct Agent Class
    """
    
    def __init__(self, model_id: str = "", max_tokens: int = 4096, mcp_json_path: str = "", reload_prompt: bool = False):
        """
        Initialize ReactAgent with improved configuration and error handling
        
        Args:
            model_id: Model ID to use
            max_tokens: Maximum number of tokens
            mcp_json_path: MCP configuration file path
            reload_prompt: Whether to reload prompt cache
        """
        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv()
        tracer_provider = setup_phoenix()
        
        # Use configuration manager for settings
        config = config_manager.config
        if model_id:
            config.model_id = model_id
        if mcp_json_path:
            config.mcp_json_path = mcp_json_path
        if max_tokens != 4096:
            config.max_tokens = max_tokens
        
        # Model and settings from config
        self.config = config
        self.model_id = config.model_id or model_id
        self.mcp_json_path = config.mcp_json_path or mcp_json_path
        self.model = get_llm(
            model_id=self.model_id, 
            max_tokens=config.max_tokens, 
            tracer_provider=tracer_provider
        )
        self.debug_mode = config.debug_mode
        self.error_handler = global_error_handler

        # Clear prompt cache if requested
        if reload_prompt:
            prompt_manager.clear_cache()
            logger.info("Prompt cache cleared")
        
        # Create instances with configuration
        self.mcp_service = MCPService(self.mcp_json_path)
        self.health_checker = MCPHealthChecker(self.mcp_service)
        
        # Use configuration for conversation manager
        memory_config = config.get_memory_limits()
        self.convo_manager = ConversationManager(
            debug_mode=self.debug_mode,
            max_threads=memory_config["max_threads"],
            max_messages_per_thread=memory_config["max_messages_per_thread"]
        )
        self.graph_builder = GraphBuilder(self.model, self.health_checker, self.mcp_service)
        
        # Runtime state
        self.checkpointer = None
        self.graph = None
        
        # Initialize metrics and logging
        self.metrics = get_metrics()
        self.agent_logger = get_agent_logger("ReactAgent")
        
        logger.info(f"ReactAgent initialized with config: threads={memory_config['max_threads']}, messages_per_thread={memory_config['max_messages_per_thread']}")
        self.agent_logger.log_memory_usage(
            memory_config['max_threads'], 
            memory_config['max_messages_per_thread'], 
            0
        )

    async def startup(self):
        """
        Start MCP service and initialize graph
        """
        logger.info("ReactAgent started - checkpoint and graph initialized")
        try:
            # 1. 체크포인터 초기화
            logger.info("Initializing checkpoint...")
            self.checkpointer = await init_checkpointer()
            logger.info("Checkpoint initialized")
            
            # 2. MCP 서비스 시작
            logger.info("Starting MCP service...")
            await self.mcp_service.startup()
            
            # 3. 헬스 체크 수행
            logger.info("Performing health check...")
            health_status = await self.health_checker.check_mcp_health()
            
            # 4. 그래프 빌드
            logger.info("Building agent graph...")
            self.graph = self.graph_builder.build(self.checkpointer)
            logger.info("Agent graph built")
            
            if health_status.get("healthy", False):
                logger.info(f"ReactAgent started - {health_status.get('tools_count', 0)} tools available")
            else:
                logger.warning(f"ReactAgent started (issues) - {health_status.get('error', 'unknown error')}")
                
        except Exception as e:
            logger.error(f"ReactAgent start failed: {str(e)}")
            # Update health status and handle error
            self.health_checker.set_unhealthy(str(e))
            error_response = self.error_handler.handle_error(e, {"phase": "startup"})
            logger.info(f"Error handled during startup: {error_response.content}")
            raise e

    async def shutdown(self):
        """
        Shutdown MCP service
        """
        logger.info("ReactAgent shutdown - simplified version, MCP shutdown not needed")
        pass

    async def _prepare_graph_input(
        self, 
        input_state: InputState, 
        config: RunnableConfig,
        files: List[Dict[str, Any]] = [],
        index_id: Optional[str] = "",
        document_id: Optional[str] = "",
        segment_id: Optional[str] = ""
    ) -> InputState:
        """
        Prepare graph input data
        
        Args:
            input_state: input state
            config: execution configuration
            files: attachment file list
            index_id: index ID
            document_id: document ID
            segment_id: segment ID
        Returns:
            prepared input state
        """
        # process attachments
        attachments = []
        attachment_errors = []
        if files:
            try:
                logger.info(f"{len(files)} attachments processing")
                attachments, attachment_errors = await process_attachments(files)
                logger.info(f"Attachment processing completed: {len(attachments)} success, {len(attachment_errors)} errors")
                
                # if there are errors, log them
                for error in attachment_errors:
                    logger.warning(f"Attachment error: {error}")
            except Exception as e:
                logger.error(f"Error processing attachments: {str(e)}")
                attachment_errors.append("Error processing attachments")
        
        # if there are attachment errors, return errors
        if attachment_errors:
            raise Exception(f"Attachment processing errors:\n" + "\n".join(f"- {error}" for error in attachment_errors))
        
        # get thread ID
        thread_id = config.get("configurable", {}).get("thread_id", "default_thread")
        
        # prepare conversation from conversation history
        conversation = self.convo_manager.prepare_conversation(thread_id, input_state.messages, index_id, document_id, segment_id)
        
        # if there are attachments, convert message format
        if conversation and isinstance(conversation[-1], BaseMessage) and attachments:
            last_message = conversation[-1]
            original_content = last_message.content
            
            # convert message to attachment format
            formatted_message = create_message_with_attachments(original_content, attachments)
            
            # replace last message
            if isinstance(formatted_message, dict) and "content" in formatted_message:
                # convert to LangChain format (direct content array)
                from langchain_core.messages import HumanMessage
                conversation[-1] = HumanMessage(content=formatted_message["content"])
                logger.info("Attachment message conversion completed (content array)")
            else:
                # if it's a string, use it as is
                from langchain_core.messages import HumanMessage
                conversation[-1] = HumanMessage(content=formatted_message)
                logger.info("Attachment message conversion completed")
        
        # prevent duplicate system messages
        from langchain_core.messages import SystemMessage
        pure_conversation = [msg for msg in conversation if not isinstance(msg, SystemMessage)]
        input_state.messages = pure_conversation
        if index_id:
            input_state.index_id = index_id
        if document_id:
            input_state.document_id = document_id
        if segment_id:
            input_state.segment_id = segment_id

        return input_state

    async def astream(
        self, 
        input_state: InputState, 
        config: RunnableConfig,
        stream_mode: str = "messages",
        files: List[Dict[str, Any]] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None
    ) -> AsyncGenerator[Tuple[BaseMessage, Dict[str, Any]], None]:
        """
        Run agent in streaming mode (improved references handling)
        
        Args:
            input_state: input state
            config: execution configuration
            stream_mode: streaming mode
            files: attachment file list (optional)
            index_id: index ID for context
            document_id: document ID for context
            segment_id: segment ID for context
        Yields:
            message chunks and metadata (references are sent only once at the end)
        """
        print(f"document_id: {document_id}, segment_id: {segment_id}")
        # get thread ID
        thread_id = config.get("configurable", {}).get("thread_id", "default_thread")
        
        # check if graph is initialized
        if self.graph is None:
            error_message = AIMessage(content="ReactAgent is not initialized. Please call the startup() method first.")
            error_metadata = {
                "langgraph_node": "error",
                "langgraph_step": 0,
                "type": "initialization_error"
            }
            yield error_message, error_metadata
            return

        # final references information storage variable
        final_references = []

        try:
            # 1. prepare graph input
            prepared_input = await self._prepare_graph_input(input_state, config, files, index_id, document_id, segment_id)
            
            print(f"\n{Fore.CYAN}=== ReAct Agent started ==={Style.RESET_ALL}\n")

            # variables for streaming
            last_chunk = None
            full_response = ""
            
            # log message size
            message_size = sys.getsizeof(str(prepared_input))
            logger.debug(f"Message size: {message_size/1024:.2f} KB")
            
            # 2. run graph streaming
            async for chunk in self.graph.astream(
                prepared_input, 
                config,
                stream_mode=stream_mode
            ):
                # process chunk and metadata
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    message_chunk, metadata = chunk
                    
                    # process metadata with references
                    if "references" in metadata and metadata["references"]:
                        # accumulate references information
                        if isinstance(metadata["references"], list):
                            final_references.extend(metadata["references"])
                        else:
                            final_references.append(metadata["references"])
                        
                        logger.debug(f"References collected: {len(metadata['references'])}")
                        
                        # if there are only references, skip and continue
                        # but if there is a message content, send the message
                        if (not hasattr(message_chunk, "content") or 
                            not message_chunk.content or 
                            message_chunk.content.strip() == ""):
                            continue
                        
                        # if there is a message, send the message with references removed
                        clean_metadata = {k: v for k, v in metadata.items() if k != "references"}
                        metadata = clean_metadata
                    
                    # save last chunk
                    last_chunk = message_chunk
                    
                    # accumulate response content
                    if isinstance(message_chunk, AIMessage) and hasattr(message_chunk, "content"):
                        chunk_content = normalize_content(message_chunk.content)
                        if isinstance(chunk_content, dict) and chunk_content.get("type") == "text":
                            full_response += chunk_content.get("text", "")
                        elif isinstance(chunk_content, str):
                            # if the string is a dictionary, process it
                            if chunk_content.startswith("{'type': 'text'") or chunk_content.startswith("{'text'"):
                                try:
                                    # convert the string to a dictionary
                                    dict_content = ast.literal_eval(chunk_content)
                                    
                                    # if the 'text' key exists, extract the value
                                    if 'text' in dict_content:
                                        text = dict_content['text']
                                        full_response += text
                                except Exception as e:
                                    logger.error(f"String-dictionary conversion error: {str(e)}")
                                    # if the conversion fails, use the original string
                                    full_response += chunk_content
                            else:   
                                full_response += chunk_content
                    
                    # add LangGraph step information to metadata
                    if "langgraph_step" not in metadata:
                        metadata["langgraph_step"] = 0
                        
                    # add node type to metadata
                    if "langgraph_node" not in metadata:
                        # infer node type based on message type
                        if hasattr(message_chunk, "tool_calls") and message_chunk.tool_calls:
                            metadata["langgraph_node"] = "tools"
                        else:
                            metadata["langgraph_node"] = "agent"

                    # yield chunk and metadata (references are removed)
                    yield message_chunk, metadata
                    
        except Exception as e:
            # log error when exception occurs
            logger.error(f"Error occurred during model call: {str(e)}")
            
            # create error message
            error_message = AIMessage(content=f"{str(e)}")
            
            # set error metadata
            error_metadata = {
                "langgraph_node": "error",
                "langgraph_step": 0,
                "type": "error"
            }
            
            # send error message
            yield error_message, error_metadata
            return
        
        # 3. after streaming ends, if there are collected references, send them last
        if final_references:
            logger.info(f"Final references sent: {len(final_references)}")
            
            # remove duplicates (if needed)
            unique_references = []
            seen_ids = set()
            for ref in final_references:
                # if the reference is a dictionary and has a unique ID, remove duplicates
                if isinstance(ref, dict):
                    ref_id = ref.get('id') or ref.get('document_id') or str(ref)
                    if ref_id not in seen_ids:
                        unique_references.append(ref)
                        seen_ids.add(ref_id)
                else:
                    unique_references.append(ref)
            
            # send empty AIMessage with references metadata last
            yield AIMessage(content=""), {
                "references": unique_references,
                "type": "references",
                "langgraph_node": "final_references",
                "langgraph_step": 999  # indicate the last step
            }
        
        # 4. save the final response to the conversation history
        if last_chunk and isinstance(last_chunk, AIMessage):
            self.convo_manager.add_assistant_message_to_history(thread_id, full_response)

    def clear_conversation_history(self, thread_id: str = None) -> bool:
        """
        Clear conversation history
        
        Args:
            thread_id: specific thread ID (None for all)
            
        Returns:
            success or failure
        """
        try:
            # clear memory history
            success = self.convo_manager.clear_conversation_history(thread_id)
            
            # clear permanent storage
            if self.checkpointer:
                cleanup_success = cleanup_checkpointer_data(self.checkpointer, thread_id)
                if not cleanup_success:
                    logger.warning("Permanent storage clear failed")
            
            return success
            
        except Exception as e:
            logger.error(f"Error occurred during conversation history clear: {e}")
            return False

    def reinit_conversation(self, thread_id: str) -> bool:
        """
        Completely new conversation start (completely delete existing data)
        
        Args:
            thread_id: thread ID to reinitialize
            
        Returns:
            success or failure
        """
        try:
            # clear conversation history for this thread
            success = self.clear_conversation_history(thread_id)
            
            # initialize execution state
            if hasattr(self.graph_builder, 'execution_state') and thread_id in self.graph_builder.execution_state:
                del self.graph_builder.execution_state[thread_id]
            
            logger.info(f"Thread {thread_id} conversation reinitialized")
            return success
            
        except Exception as e:
            logger.error(f"Error occurred during conversation reinitialization: {e}")
            return False

    def get_health_status(self) -> Dict[str, Any]:
        """
        Return MCP health status
        
        Returns:
            health status information
        """
        return self.health_checker.get_health_status()

    def get_conversation_stats(self) -> Dict[str, Any]:
        """
        Return conversation statistics
        
        Returns:
            conversation statistics information
        """
        return {
            "active_threads": self.convo_manager.get_thread_count(),
            "total_messages": self.convo_manager.get_total_message_count(),
            "mcp_healthy": self.health_checker.is_healthy(),
            "mcp_tools_count": self.health_checker.get_tools_count()
        }
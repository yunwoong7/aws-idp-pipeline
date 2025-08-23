"""
GraphBuilder - LangGraph structure builder and manager class
"""
import logging
import os
from typing import Dict, Any, Literal, List
from datetime import datetime, timezone
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph

from src.common.configuration import Configuration
from .state.model import InputState, State
from .prompt import prompt_manager
from .node.tool_node import CustomToolNode
from .utils import retry_with_backoff, normalize_content
from .state_manager import (
    should_summarize, 
    get_messages_for_summarization, 
    prepare_messages_for_summary,
    create_summary_prompt,
    remove_image_data_from_content
)
from .error_handler import global_error_handler
from .config import config_manager
import requests

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    LangGraph structure builder and manager class
    """
    
    def __init__(self, model, health_checker, mcp_service):
        """
        Initialize GraphBuilder
        
        Args:
            model: LLM model instance
            health_checker: MCP health checker instance
            mcp_service: MCP service instance
        """
        self.model = model
        self.health_checker = health_checker
        self.mcp_service = mcp_service
        self.execution_state = {}

    async def _fetch_attachments_from_references(self, state: State) -> List[Dict[str, Any]]:
        """Fetch small image attachments from tool_references using Document API.
        - Only uses references that carry metadata.segment_id
        - Calls /api/segments/{segment_id}/image to get base64
        - Applies strict limits to avoid token overflow
        """
        try:
            api_base = os.getenv('DOC_API_BASE_URL') or os.getenv('API_BASE_URL')
            if not api_base:
                return []

            refs = getattr(state, 'tool_references', []) or []
            if not isinstance(refs, list) or not refs:
                return []

            max_attach = int(os.getenv('REF_IMAGE_MAX_ATTACH', '1'))
            max_b64_len = int(os.getenv('REF_IMAGE_MAX_BASE64_LEN', str(500_000)))

            selected: List[Dict[str, Any]] = []
            for ref in refs:
                if not isinstance(ref, Dict):
                    continue
                meta = ref.get('metadata', {}) if isinstance(ref.get('metadata'), dict) else {}
                segment_id = meta.get('segment_id') or ref.get('segment_id')
                if not segment_id:
                    continue
                url = f"{api_base}/api/segments/{segment_id}/image"
                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code != 200:
                        continue
                    payload = r.json()
                    data = payload.get('data') or payload
                    image_b64 = data.get('image_data')
                    mime_type = data.get('mime_type', 'image/png')
                    if not image_b64 or not isinstance(image_b64, str):
                        continue
                    if len(image_b64) > max_b64_len:
                        # skip overly large images to protect context
                        continue
                    selected.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_b64,
                        }
                    })
                    if len(selected) >= max_attach:
                        break
                except Exception:
                    continue

            return selected
        except Exception:
            return []

    def build(self, checkpointer) -> StateGraph:
        """
        Build and return the graph
        
        Args:
            checkpointer: checkpointer instance
            
        Returns:
            compiled StateGraph instance
        """
        # define StateGraph
        builder = StateGraph(State, input=InputState, config_schema=Configuration)

        # define nodes
        builder.add_node("call_model", self._call_model)
        builder.add_node("tools", self._tool_node)
        builder.add_node("summarize", self._summarize_conversation)

        # set start point
        builder.add_edge("__start__", "call_model")

        # add conditional edges
        builder.add_conditional_edges(
            "call_model",
            self._route_model_output,
        )

        # add edges
        builder.add_edge("tools", "call_model")
        builder.add_edge("summarize", "call_model")

        # compile graph
        graph = builder.compile(
            checkpointer=checkpointer,
            interrupt_before=[],
            interrupt_after=[],
        )
        
        graph.name = "ReAct Agent"
        logger.info("GraphBuilder: graph built")
        return graph

    async def _call_model(self, state: State, config: RunnableConfig) -> Dict[str, Any]:
        """
        Call the LLM to execute the agent
        
        Args:
            state: current conversation state
            config: execution configuration
            
        Returns:
            dictionary containing model response
        """
        # check if summary is needed
        if should_summarize(state):
            logger.info("Summary is needed")
            return {"needs_summarization": True}
        
        # extract user query
        user_query = ""
        for msg in reversed(state.messages):
            if isinstance(msg, HumanMessage):
                user_query = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
        
        # extract thread ID
        thread_id = config.get("configurable", {}).get("thread_id", "default_thread")
        
        # get project ID
        index_id = getattr(state, 'index_id', 'unknown')
        document_id = getattr(state, 'document_id', 'unknown')
        segment_id = getattr(state, 'segment_id', 'unknown')
        
        # extract tool content and references
        content_text = getattr(state, 'tool_content', "")
        references_text = ""
        
        if hasattr(state, 'tool_references') and state.tool_references:
            references_text = "\n".join([
                f"[{ref.get('title', 'Document')}]({ref.get('value', '')})" 
                for ref in state.tool_references if ref.get('value')
            ])
        
        # add conversation summary
        summary_context = ""
        if state.conversation_summary:
            summary_context = f"\n\n[Previous conversation summary]\n{state.conversation_summary}"

        # create prompt (apply safe length to CONTENT)
        SAFE_CONTENT = content_text or ""
        if len(SAFE_CONTENT) > 32000:
            SAFE_CONTENT = SAFE_CONTENT[:32000]
            logger.info("CONTENT truncated to 32000 chars for safety")
        full_prompt = prompt_manager.get_prompt(
            "agent_profile", 
            DATETIME=datetime.now(tz=timezone.utc).isoformat(),
            INDEX_ID=index_id,
            DOCUMENT_ID=document_id,
            SEGMENT_ID=segment_id,
            QUERY=user_query,
            CONVERSATION_HISTORY=summary_context,
            CONTENT=SAFE_CONTENT,
            REFERENCES=references_text
        )
        
        instruction = full_prompt["instruction"]
        
        # create system message
        current_system_message = SystemMessage(content=full_prompt["system_prompt"])
        
        # configure conversation messages
        conversation_messages = list(state.messages)
        prompt_messages = [current_system_message]
        
        # replace last HumanMessage with instruction
        last_human_replaced = False
        for msg in conversation_messages:
            if isinstance(msg, HumanMessage) and not last_human_replaced:
                prompt_messages.append(HumanMessage(content=instruction))
                last_human_replaced = True
            else:
                prompt_messages.append(msg)
        
        # if there is no HumanMessage, add instruction
        if not last_human_replaced:
            prompt_messages.append(HumanMessage(content=instruction))

        # If previous tool produced LLM-ready attachments, inject them as a new HumanMessage before calling model
        try:
            # 1) Optional direct tool attachments
            tool_attachments = getattr(state, 'tool_attachments', []) or []
            enable_imgs = os.getenv('ENABLE_TOOL_IMAGE_ATTACHMENTS_TO_LLM', 'false').lower() == 'true'
            if enable_imgs and tool_attachments:
                MAX_ATTACH = 1
                filtered: List[dict] = []
                for att in tool_attachments:
                    if not isinstance(att, dict):
                        continue
                    src = att.get('source', {}) if isinstance(att.get('source'), dict) else {}
                    data_str = src.get('data', '')
                    if isinstance(data_str, str) and len(data_str) > 500_000:
                        continue
                    filtered.append(att)
                    if len(filtered) >= MAX_ATTACH:
                        break
                if filtered:
                    prompt_messages.append(HumanMessage(content=filtered))
                    logger.info(f"Injected tool attachments into model call: {len(filtered)}/{len(tool_attachments)} items (env-enabled)")

            # 2) If there are image references, fetch base64 on-demand (logic-level, not via MCP content)
            enable_ref_fetch = os.getenv('ENABLE_REF_IMAGE_FETCH_TO_LLM', 'false').lower() == 'true'
            if enable_ref_fetch:
                fetched = await self._fetch_attachments_from_references(state)
                if fetched:
                    prompt_messages.append(HumanMessage(content=fetched))
                    logger.info(f"Injected fetched reference images: {len(fetched)} items")
        except Exception as _:
            pass

        # get MCP tools
        tools = await self.health_checker.get_tools_with_health_check()
        if not tools:
            logger.warning("MCP tools are not available. Proceeding with empty tool list.")
            tools = []

        # log tools
        self._log_tools_info(tools)

        # update execution state
        self._update_execution_state(thread_id)
        
        # call model
        model_with_tools = self.model.bind_tools(tools)
        
        try:
            async def call_model():
                return await model_with_tools.ainvoke(prompt_messages)
            
            config = config_manager.config
            response = await retry_with_backoff(
                call_model, 
                max_retries=config.max_retries, 
                timeout=config.model_timeout
            )
            
        except Exception as e:
            logger.error(f"Model call failed: {str(e)}")
            # Use error handler for better error management
            context = {"thread_id": thread_id, "tools_count": len(tools), "prompt_size": len(str(prompt_messages))}
            error_response = global_error_handler.handle_error(e, context)
            response = error_response

        # if last step and tool calls are needed, process
        if state.is_last_step and response.tool_calls:
            result_message = AIMessage(
                id=response.id,
                content="Sorry, I couldn't find an answer within the specified number of steps. Please try again later. (Error: {str(e)})"
            )
            
            return {
                "messages": [result_message],
                "tool_content": "",
                "needs_summarization": False
            }

        # update AI response (tool_references are automatically preserved)
        updated_state = {
            "messages": [response],
            "needs_summarization": False
        }
        
        # initialize tool_content only if there are no tool calls
        if not response.tool_calls:
            updated_state["tool_content"] = ""
        
        logger.info(f"_call_model: response type={type(response).__name__}, has_tool_calls={bool(response.tool_calls) if hasattr(response, 'tool_calls') else 'N/A'}")
        logger.info(f"_call_model: returning messages count={len(updated_state['messages'])}")
        return updated_state

    async def _tool_node(self, state: State, config: RunnableConfig) -> Dict[str, Any]:
        """
        Execute MCP tools and extract results
        
        Args:
            state: current conversation state
            config: execution configuration
            
        Returns:
            dictionary updated with tool results
        """
        logger.info("=== _tool_node called ===")
        
        # get MCP tools
        tools = self.mcp_service.get_tools()
        if not tools:
            logger.warning("MCP tools are not initialized")
            return {"messages": []}
        
        logger.info(f"Creating CustomToolNode with {len(tools)} MCP tools")
        
        # create and execute CustomToolNode
        custom_tool_node = CustomToolNode(tools)
        result = await custom_tool_node(state, config)
        
        logger.info(f"CustomToolNode execution result: tool_references={len(result.get('tool_references', []))}, tool_content_length={len(result.get('tool_content', '') or '')}")
        
        return result

    async def _summarize_conversation(self, state: State, config: RunnableConfig) -> Dict[str, Any]:
        """
        Summarize conversation history and remove image data
        
        Args:
            state: current conversation state
            config: execution configuration
            
        Returns:
            dictionary updated with summarized conversation
        """
        logger.info("=== _summarize_conversation called ===")
        
        # get messages to summarize
        messages_to_summarize = get_messages_for_summarization(state)
        
        if not messages_to_summarize:
            logger.info("No messages to summarize")
            return {"needs_summarization": False}
        
        # prepare message text
        conversation_text = prepare_messages_for_summary(messages_to_summarize)
        
        # create summary prompt
        summary_prompt = create_summary_prompt(conversation_text)
        
        try:
            # execute summary
            summary_response = await self.model.ainvoke([HumanMessage(content=summary_prompt)])
            new_summary = summary_response.content if hasattr(summary_response, 'content') else str(summary_response)
            
            # combine with existing summary
            if state.conversation_summary:
                combined_summary = f"{state.conversation_summary}\n\n[Recent conversation summary]\n{new_summary}"
            else:
                combined_summary = new_summary
            
            # keep only recent messages (last 4)
            recent_messages = state.messages[-4:] if len(state.messages) > 4 else state.messages
            original_count = len(state.messages)
            
            logger.info(f"Conversation summary completed: {len(messages_to_summarize)} messages → {len(recent_messages)} messages")
            
            return {
                "messages": recent_messages,
                "conversation_summary": combined_summary,
                "message_count": state.message_count + len(messages_to_summarize),
                "last_summarization_at": original_count,
                "needs_summarization": False
            }
            
        except Exception as e:
            logger.error(f"Error occurred during conversation summary: {str(e)}")
            # if summary fails, perform basic cleanup
            recent_messages = state.messages[-4:] if len(state.messages) > 4 else state.messages
            original_count = len(state.messages)
            return {
                "messages": recent_messages,
                "last_summarization_at": original_count,
                "needs_summarization": False
            }

    def _route_model_output(self, state: State) -> Literal["__end__", "tools", "summarize"]:
        """
        Determine next node based on model output
        
        Args:
            state: current conversation state
            
        Returns:
            name of the next node to call
        """
        # check if summary is needed
        if state.needs_summarization:
            return "summarize"
        
        # add debugging information
        logger.info(f"_route_model_output: messages count={len(state.messages)}")
        if state.messages:
            for i, msg in enumerate(state.messages[-3:]):  # log only last 3 messages
                # logger.info(f"_route_model_output: message[{i}] type={type(msg).__name__}, content={str(msg.content)[:100]}...")
                logger.info(f"_route_model_output: message[{i}] type={type(msg).__name__}, content={str(msg.content)}")
        
        last_message = state.messages[-1]
        if not isinstance(last_message, AIMessage):
            logger.error(f"_route_model_output: last message type is wrong. expected: AIMessage, actual: {type(last_message).__name__}")
            logger.error(f"_route_model_output: last message content: {str(last_message.content)[:200]}...")
            raise ValueError(
                f"Expected AIMessage in output edge, but received {type(last_message).__name__}"
            )
            
        # if there are no tool calls, end
        if not last_message.tool_calls:
            return "__end__"
            
        # otherwise, execute tools
        return "tools"

    def _log_tools_info(self, tools: List[Any]) -> None:
        """
        log tool information
        
        Args:
            tools: tool list
        """
        tool_names = set()
        server_tool_counts = {}
        
        for tool in tools:
            if hasattr(tool, "name"):
                tool_names.add(tool.name)
                server_name = tool.name.split('_')[0] if '_' in tool.name else "etc"
                server_tool_counts[server_name] = server_tool_counts.get(server_name, 0) + 1
        
        logger.info(f"Available MCP tools: {len(server_tool_counts)} servers, {len(tools)} tools")
        
        server_summary = ", ".join([f"{server}: {count} tools" for server, count in server_tool_counts.items()])
        if server_summary:
            logger.debug(f"Tool distribution: {server_summary}")

    def _update_execution_state(self, thread_id: str) -> None:
        """
        update execution state for the specified thread ID
        
        Args:
            thread_id: thread identifier
        """
        if thread_id not in self.execution_state:
            self.execution_state[thread_id] = {"step": 0, "current_phase": "initial"}
        else:
            self.execution_state[thread_id]["step"] += 1
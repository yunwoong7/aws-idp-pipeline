"""
Planner Node - Plans tasks and determines execution strategy
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, AsyncIterator, List, Optional
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain.schema import OutputParserException

from ..state.model import ChatState, Plan, Task, TaskStatus
from ..prompt import prompt_manager
from src.mcp_client.mcp_service import MCPService
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class PlannerNode:
    """
    Planner node that creates execution plans with streaming support
    """
    
    def __init__(
        self, 
        model: ChatBedrock, 
        mcp_service: MCPService,
        verbose: bool = False
    ):
        """
        Initialize the planner node
        
        Args:
            model: Language model for planning
            mcp_service: MCP service for tool information
            verbose: Enable verbose logging
        """
        self.model = model.with_structured_output(Plan)
        self.raw_model = model  # For streaming
        self.mcp_service = mcp_service
        self.verbose = verbose
        
        # Will load system prompt from YAML

    async def _get_tools_description(self) -> str:
        """Get available MCP tools description"""
        try:
            tools_info = self.mcp_service.get_tools()
            if not tools_info:
                return "No MCP tools available"
            
            descriptions = []
            for tool in tools_info:
                # Handle both dict format and tool object format
                if hasattr(tool, 'name'):
                    tool_desc = f"- {tool.name}: {getattr(tool, 'description', 'No description')}"
                elif isinstance(tool, dict):
                    tool_desc = f"- {tool.get('name', 'Unknown')}: {tool.get('description', 'No description')}"
                else:
                    tool_desc = f"- {str(tool)}: MCP tool"
                descriptions.append(tool_desc)
            
            return "\n".join(descriptions)
        except Exception as e:
            logger.error(f"Failed to get MCP tools: {e}")
            return "Error retrieving MCP tools"


    async def astream(self, state: ChatState) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream planning process with real-time updates
        
        Args:
            state: Current chat state
            
        Yields:
            Planning updates and final plan
        """
        logger.info("Starting planning phase...")
        start_time = time.time()
        
        try:
            # Get available tools
            tools_description = await self._get_tools_description()
            
            # Build context for current query
            current_input = state.input
            context_info = []
            
            if state.index_id:
                context_info.append(f"Index ID: {state.index_id}")
            if state.document_id:
                context_info.append(f"Document ID: {state.document_id}")
            if state.segment_id:
                context_info.append(f"Segment ID: {state.segment_id}")
            
            context_text = " | ".join(context_info) if context_info else ""
            
            # Format conversation history
            conversation_text = ""
            for msg in state.message_history:
                conversation_text += f"{msg['role']}: {msg['content']}\n"
            
            # Get formatted prompt from YAML
            prompt = prompt_manager.get_prompt(
                "planner",
                DATETIME=datetime.now(tz=timezone.utc).isoformat(),
                INDEX_ID=state.index_id or "",
                DOCUMENT_ID=state.document_id or "",
                SEGMENT_ID=state.segment_id or "",
                QUERY=current_input,
                CONVERSATION_HISTORY=conversation_text.strip(),
                AVAILABLE_TOOLS=tools_description
            )
            
            # Create messages from prompt
            messages = [
                SystemMessage(content=prompt["system_prompt"]),
                HumanMessage(content=prompt["instruction"])
            ]
            
            # Stream planning tokens first
            yield {
                "type": "planning_start",
                "message": "Analyzing your request and creating execution plan...",
                "timestamp": time.time()
            }
            
            # Try streaming with structured output
            planning_text = ""
            
            try:
                # Use the structured output model to get the plan
                async for event in self.model.astream_events(messages, version='v2'):
                    if event["event"] == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        if hasattr(chunk, 'content') and chunk.content:
                            # Stream planning reasoning
                            if isinstance(chunk.content, list):
                                for content_item in chunk.content:
                                    if content_item.get('type') == 'text':
                                        token = content_item.get('text', '')
                                        if token:
                                            planning_text += token
                                            yield {
                                                "type": "planning_token",
                                                "token": token,
                                                "timestamp": time.time()
                                            }
                                            
                            elif isinstance(chunk.content, str):
                                planning_text += chunk.content
                                yield {
                                    "type": "planning_token", 
                                    "token": chunk.content,
                                    "timestamp": time.time()
                                }
                                        
                    elif event["event"] == "on_chain_end":
                        # Get the final structured plan
                        plan_result = event["data"]["output"]
                        if isinstance(plan_result, Plan):
                            plan = plan_result
                        else:
                            # Handle case where result is not a Plan object
                            plan = Plan.model_validate(plan_result)
                            
                        break
                else:
                    # Fallback if streaming doesn't work
                    plan = await self.model.ainvoke(messages)
                    
            except Exception as e:
                logger.warning(f"Structured streaming failed, using fallback: {e}")
                
                # Fallback: Generate plan directly  
                yield {
                    "type": "planning_token",
                    "token": "Generating execution strategy...",
                    "timestamp": time.time()
                }
                
                plan = await self.model.ainvoke(messages)
            
            # Validate plan
            if not isinstance(plan, Plan):
                if isinstance(plan, dict):
                    plan = Plan.model_validate(plan)
                else:
                    raise ValueError(f"Invalid plan format: {type(plan)}")
            
            planning_time = time.time() - start_time
            logger.info(f"Planning completed in {planning_time:.2f}s")
            
            # Yield final plan
            yield {
                "type": "plan_complete",
                "plan": plan,
                "planning_time": planning_time,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            yield {
                "type": "planning_error",
                "error": str(e),
                "timestamp": time.time()
            }

    async def ainvoke(self, state: ChatState) -> Plan:
        """
        Generate plan without streaming (for testing/fallback)
        
        Args:
            state: Current chat state
            
        Returns:
            Generated plan
        """
        # Get available tools
        tools_description = await self._get_tools_description()
        
        # Build context for current query
        current_input = state.input
        context_info = []
        
        if state.index_id:
            context_info.append(f"Index ID: {state.index_id}")
        if state.document_id:
            context_info.append(f"Document ID: {state.document_id}")
        if state.segment_id:
            context_info.append(f"Segment ID: {state.segment_id}")
        
        context_text = " | ".join(context_info) if context_info else ""
        
        # Format conversation history
        conversation_text = ""
        for msg in state.message_history:
            conversation_text += f"{msg['role']}: {msg['content']}\n"
        
        # Get formatted prompt from YAML
        prompt = prompt_manager.get_prompt(
            "planner",
            DATETIME=datetime.now(tz=timezone.utc).isoformat(),
            INDEX_ID=state.index_id or "",
            DOCUMENT_ID=state.document_id or "",
            SEGMENT_ID=state.segment_id or "",
            QUERY=current_input,
            CONVERSATION_HISTORY=conversation_text.strip(),
            AVAILABLE_TOOLS=tools_description
        )
        
        # Create messages from prompt
        messages = [
            SystemMessage(content=prompt["system_prompt"]),
            HumanMessage(content=prompt["instruction"])
        ]
        
        plan = await self.model.ainvoke(messages)
        
        if not isinstance(plan, Plan):
            if isinstance(plan, dict):
                plan = Plan.model_validate(plan)
            else:
                raise ValueError(f"Invalid plan format: {type(plan)}")
        
        return plan
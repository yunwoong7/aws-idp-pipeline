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
from langchain_core.exceptions import OutputParserException

from ..state.model import SearchState, Plan, Task, TaskStatus
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


    async def astream(self, state: SearchState) -> AsyncIterator[Dict[str, Any]]:
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
            
            # Use raw model for streaming first, then parse to structured format
            planning_text = ""
            
            try:
                # First stream the raw planning text
                logger.info("Streaming planning thoughts...")
                async for chunk in self.raw_model.astream(messages):
                    if hasattr(chunk, 'content') and chunk.content:
                        token = chunk.content
                        planning_text += token
                        yield {
                            "type": "planning_token",
                            "token": token,
                            "timestamp": time.time()
                        }
                
                # Add a small pause to show thinking is complete
                yield {
                    "type": "planning_token",
                    "token": "\n\n✅ Planning complete, generating structured plan...",
                    "timestamp": time.time()
                }
                
                # Now get structured plan (without streaming)
                logger.info("Generating structured plan...")
                plan = await self.model.ainvoke(messages)
                    
            except Exception as e:
                logger.warning(f"Raw streaming failed, using structured output directly: {e}")
                
                # Fallback: Show thinking process and generate plan directly  
                thinking_messages = [
                    "Analyzing your request...",
                    "Checking available tools...",
                    "Creating execution strategy...",
                    "Finalizing plan details..."
                ]
                
                for msg in thinking_messages:
                    yield {
                        "type": "planning_token",
                        "token": f"{msg}\n",
                        "timestamp": time.time()
                    }
                    # Small delay to simulate thinking
                    await asyncio.sleep(0.2)
                
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

    async def ainvoke(self, state: SearchState) -> Plan:
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
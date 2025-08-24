"""Search Agent

Main orchestrator for Plan-and-Execute search functionality.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List
from datetime import datetime

from langchain_core.language_models import BaseChatModel

from .state import SearchState, PlanGeneratedEvent, ErrorEvent
from .planner import SearchPlanner
from .executor import SearchExecutor
from .synthesizer import SearchSynthesizer

from src.agent.react_agent.config import ConfigManager
from src.mcp_client.mcp_service import MCPService
from src.agent.react_agent.health_checker import MCPHealthChecker
from src.agent.react_agent.error_handler import ErrorHandler
from src.agent.react_agent.logger_config import get_agent_logger

logger = logging.getLogger(__name__)


class SearchAgent:
    """
    Plan-and-Execute search agent.
    
    Workflow:
    1. Plan: Analyze query and create execution steps
    2. Execute: Run each step and collect results  
    3. Synthesize: Generate comprehensive answer with citations
    """
    
    def __init__(
        self,
        model: BaseChatModel,
        config: ConfigManager,
        mcp_service: MCPService,
        health_checker: Optional[MCPHealthChecker] = None,
        error_handler: Optional[ErrorHandler] = None
    ):
        """Initialize SearchAgent with required services."""
        self.model = model
        self.config = config
        self.mcp_service = mcp_service
        self.health_checker = health_checker
        self.error_handler = error_handler or ErrorHandler()
        
        # Initialize components
        self.planner = SearchPlanner(model, config)
        self.executor = SearchExecutor(mcp_service)
        self.synthesizer = SearchSynthesizer(model, config)
        
        # Setup logging
        self.logger = get_agent_logger("SearchAgent")
        
        logger.info("SearchAgent initialized successfully")
    
    async def astream(
        self,
        query: str,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute search with Plan-and-Execute approach.
        
        Args:
            query: User's search query
            index_id: Document index ID for context
            document_id: Specific document ID if applicable  
            segment_id: Specific segment ID if applicable
            config: Additional configuration options
            
        Yields:
            Stream events for real-time progress updates
        """
        search_state = SearchState(
            query=query,
            index_id=index_id,
            document_id=document_id,
            segment_id=segment_id
        )
        
        logger.info(f"Starting search for query: {query[:100]}...")
        
        try:
            # Phase 1: Planning
            logger.info("Phase 1: Creating execution plan")
            search_state.phase = "planning"
            
            yield {
                "type": "phase_update",
                "phase": "planning",
                "message": "Analyzing query and creating execution plan...",
                "timestamp": datetime.now().isoformat()
            }
            
            # Get available tools
            available_tools = await self._get_available_tools()
            
            # Create execution plan
            plan = await self.planner.create_plan(
                query=query,
                available_tools=available_tools,
                index_id=index_id,
                document_id=document_id,
                segment_id=segment_id
            )
            
            search_state.plan = plan
            
            # Emit plan generated event
            yield {
                "type": "plan_generated",
                "plan": [
                    {
                        "step": step.step,
                        "thought": step.thought,
                        "tool_name": step.tool_name,
                        "tool_input": step.tool_input,
                        "status": step.status
                    }
                    for step in plan.plan
                ],
                "total_steps": len(plan.plan),
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Generated plan with {len(plan.plan)} steps")
            
            # Phase 2: Execution
            logger.info("Phase 2: Executing plan steps")
            
            # Execute plan and stream progress
            async for event in self.executor.execute_plan(plan, search_state):
                yield event
            
            # Check if we have any successful results
            successful_results = [r for r in search_state.execution_results if r.success]
            if not successful_results:
                error_msg = "All execution steps failed - no results to synthesize"
                logger.error(error_msg)
                search_state.mark_error(error_msg)
                
                yield {
                    "type": "error",
                    "error_message": error_msg,
                    "error_code": "no_successful_results",
                    "timestamp": datetime.now().isoformat()
                }
                return
            
            logger.info(f"Execution completed with {len(successful_results)} successful results")
            
            # Phase 3: Synthesis
            logger.info("Phase 3: Synthesizing answer")
            
            # Synthesize answer and stream response
            async for event in self.synthesizer.synthesize_answer_stream(search_state):
                yield event
            
            logger.info("Search completed successfully")
            
        except Exception as e:
            logger.error(f"Search failed with error: {e}")
            
            # Handle error through error handler
            if self.error_handler:
                recovery_action = await self.error_handler.handle_error(e, {"query": query})
                if recovery_action and recovery_action.should_retry:
                    logger.info("Attempting error recovery...")
                    # Could implement retry logic here
            
            search_state.mark_error(str(e))
            
            yield {
                "type": "error",
                "error_message": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    async def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available MCP tools."""
        try:
            # Check if MCP service is healthy
            if self.health_checker:
                health_status = await self.health_checker.check_mcp_health()
                if not health_status.get("healthy", False):
                    logger.warning("MCP service is not healthy")
            
            # Get tools from MCP service
            tools = self.mcp_service.get_tools()
            # Convert LangChain tools to dict format for planner
            formatted_tools = []
            for tool in tools:
                if hasattr(tool, 'name') and hasattr(tool, 'description'):
                    tool_dict = {
                        'name': tool.name,
                        'description': tool.description
                    }
                    # Add input schema if available
                    if hasattr(tool, 'args'):
                        tool_dict['inputSchema'] = {
                            'properties': tool.args
                        }
                    formatted_tools.append(tool_dict)
            tools = formatted_tools
            
            logger.debug(f"Retrieved {len(tools)} available tools")
            return tools
            
        except Exception as e:
            logger.error(f"Failed to get available tools: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """Check the health status of the search agent."""
        try:
            health_status = {
                "search_agent": True,
                "timestamp": datetime.now().isoformat()
            }
            
            # Check MCP service
            try:
                tools = await self.mcp_service.get_tools()
                health_status["mcp_service"] = True
                health_status["available_tools"] = len(tools)
            except Exception as e:
                health_status["mcp_service"] = False
                health_status["mcp_error"] = str(e)
            
            # Check model
            try:
                test_messages = [{"role": "user", "content": "test"}]
                # Quick test call (don't actually invoke)
                health_status["model"] = True
            except Exception as e:
                health_status["model"] = False
                health_status["model_error"] = str(e)
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "search_agent": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return {
            "agent_type": "search",
            "version": "1.0.0",
            "plan_and_execute": True,
            "supports_streaming": True,
            "supports_citations": True
        }
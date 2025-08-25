"""
SearchAgent Workflow - Orchestrates Plan-Execute-Respond pattern
"""

import asyncio
import logging
import time
from typing import Dict, Any, AsyncIterator, Optional

from langchain_aws import ChatBedrock

from .state.model import SearchState, Plan
from .node.planner import PlannerNode
from .node.executor import ExecutorNode
from .node.responder import ResponderNode
from src.mcp_client.mcp_service import MCPService

logger = logging.getLogger(__name__)

class SearchAgentWorkflow:
    """
    Main workflow orchestrator for SearchAgent with Plan-Execute-Respond pattern
    """
    
    def __init__(
        self,
        model_id: str = "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        max_tokens: int = 4096,
        mcp_config_path: Optional[str] = None,
        show_thought_process: bool = False,
        verbose: bool = False
    ):
        """
        Initialize the SearchAgent workflow
        
        Args:
            model_id: Bedrock model ID to use
            max_tokens: Maximum tokens for responses
            mcp_config_path: Path to MCP configuration
            show_thought_process: Whether to show reasoning process
            verbose: Enable verbose logging
        """
        self.model_id = model_id
        self.max_tokens = max_tokens
        self.mcp_config_path = mcp_config_path
        self.show_thought_process = show_thought_process
        self.verbose = verbose
        
        # Initialize components
        self._setup_model()
        self._setup_mcp_service()
        self._setup_nodes()

    def _setup_model(self):
        """Setup the language model"""
        self.model = ChatBedrock(
            model_id=self.model_id,
            model_kwargs={
                "max_tokens": self.max_tokens,
                "temperature": 0.1,
                "top_p": 0.9,
            }
        )
        logger.info(f"Model initialized: {self.model_id}")

    def _setup_mcp_service(self):
        """Setup MCP service"""
        self.mcp_service = MCPService(self.mcp_config_path) if self.mcp_config_path else None
        if self.mcp_service:
            logger.info("MCP service initialized")
        else:
            logger.warning("MCP service not available")

    def _setup_nodes(self):
        """Setup workflow nodes"""
        self.planner = PlannerNode(
            model=self.model,
            mcp_service=self.mcp_service,
            verbose=self.verbose
        )
        
        self.executor = ExecutorNode(
            mcp_service=self.mcp_service,
            model_id=self.model_id,
            verbose=self.verbose
        )
        
        self.responder = ResponderNode(
            model=self.model,
            show_thought_process=self.show_thought_process,
            verbose=self.verbose
        )
        
        logger.info("Workflow nodes initialized")

    async def astream(
        self,
        input_text: str,
        message_history: Optional[list] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream the complete Plan-Execute-Respond workflow
        
        Args:
            input_text: User input
            message_history: Previous conversation history
            index_id: Index ID for context
            document_id: Document ID for context
            segment_id: Segment ID for context
            
        Yields:
            Workflow events and updates
        """
        workflow_start_time = time.time()
        
        # Initialize state
        state = SearchState.initial_state(
            input_text=input_text,
            message_history=message_history or [],
            index_id=index_id,
            document_id=document_id,
            segment_id=segment_id
        )
        
        logger.info(f"Starting SearchAgent workflow for: {input_text[:50]}...")
        
        yield {
            "type": "workflow_start",
            "message": "Starting intelligent conversation workflow...",
            "input": input_text,
            "timestamp": time.time()
        }

        try:
            # Phase 1: Planning
            logger.info("Phase 1: Planning")
            yield {
                "type": "phase_start",
                "phase": "planning",
                "message": "Analyzing request and creating execution plan...",
                "timestamp": time.time()
            }

            plan = None
            async for event in self.planner.astream(state):
                # Forward planning events
                yield event
                
                if event["type"] == "plan_complete":
                    plan = event["plan"]
                    state.plan = plan
                elif event["type"] == "planning_error":
                    yield {
                        "type": "workflow_error",
                        "phase": "planning", 
                        "error": event["error"],
                        "timestamp": time.time()
                    }
                    return

            if not plan:
                yield {
                    "type": "workflow_error",
                    "phase": "planning",
                    "error": "Failed to generate plan",
                    "timestamp": time.time()
                }
                return

            # Phase 2: Execution (if tools required)
            if plan.requires_tool and plan.tasks:
                logger.info("Phase 2: Execution")
                yield {
                    "type": "phase_start", 
                    "phase": "execution",
                    "message": f"Executing {len(plan.tasks)} tasks...",
                    "timestamp": time.time()
                }

                async for event in self.executor.astream(state):
                    # Forward execution events
                    yield event
                    
                    if event["type"] == "execution_complete":
                        state.executed_tasks = event["executed_tasks"]
                        # Note: references will be filtered in responder
                        
            else:
                logger.info("Skipping execution - direct response available")
                yield {
                    "type": "phase_skip",
                    "phase": "execution", 
                    "message": "Using direct response, no tool execution needed",
                    "timestamp": time.time()
                }

            # Phase 3: Response Generation
            logger.info("Phase 3: Response Generation")
            yield {
                "type": "phase_start",
                "phase": "response",
                "message": "Generating comprehensive response...",
                "timestamp": time.time()
            }

            async for event in self.responder.astream(state):
                # Forward response events
                yield event
                
                if event["type"] == "response_complete":
                    state.response = event["response"]
                    state.references = [
                        ref if isinstance(ref, dict) else ref.model_dump()
                        for ref in event["references"]
                    ]
                    state.message_history = event["message_history"]
                    
                    # Calculate total workflow time
                    workflow_time = time.time() - workflow_start_time
                    
                    # Final workflow completion
                    yield {
                        "type": "workflow_complete",
                        "response": state.response,
                        "references": state.references,
                        "message_history": state.message_history,
                        "plan": plan.model_dump() if plan else None,
                        "workflow_time": workflow_time,
                        "message": f"Workflow completed successfully in {workflow_time:.2f}s",
                        "timestamp": time.time()
                    }
                    
                    logger.info(f"Workflow completed in {workflow_time:.2f}s")
                    return
                    
                elif event["type"] == "response_error":
                    yield {
                        "type": "workflow_error",
                        "phase": "response",
                        "error": event["error"],
                        "timestamp": time.time()
                    }
                    return

        except Exception as e:
            logger.error(f"Workflow error: {e}")
            yield {
                "type": "workflow_error",
                "phase": "unknown",
                "error": str(e),
                "timestamp": time.time()
            }

    async def ainvoke(
        self,
        input_text: str,
        message_history: Optional[list] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute workflow without streaming (for testing/fallback)
        
        Args:
            input_text: User input
            message_history: Previous conversation history
            index_id: Index ID for context
            document_id: Document ID for context  
            segment_id: Segment ID for context
            
        Returns:
            Complete workflow result
        """
        result = {}
        async for event in self.astream(
            input_text=input_text,
            message_history=message_history,
            index_id=index_id,
            document_id=document_id,
            segment_id=segment_id
        ):
            if event["type"] == "workflow_complete":
                return {
                    "response": event["response"],
                    "references": event["references"],
                    "message_history": event["message_history"],
                    "plan": event["plan"]
                }
            elif event["type"] == "workflow_error":
                return {
                    "response": f"Error: {event['error']}",
                    "references": [],
                    "message_history": message_history or [],
                    "plan": None
                }
        
        return {
            "response": "Workflow failed to complete",
            "references": [],
            "message_history": message_history or [],
            "plan": None
        }

    async def startup(self):
        """Initialize MCP service if available"""
        if self.mcp_service:
            tools = await self.mcp_service.startup()
            logger.info(f"MCP service startup completed - {len(tools) if tools else 0} tools loaded")
            
            # Refresh tools in executor after MCP startup
            if hasattr(self, 'executor'):
                await self.executor.refresh_tools()
                logger.info("Executor tools refreshed after MCP startup")
        else:
            logger.warning("MCP service not configured - no tools will be available")

    async def shutdown(self):
        """Cleanup resources"""
        if self.mcp_service:
            await self.mcp_service.shutdown()
            logger.info("MCP service shutdown completed")
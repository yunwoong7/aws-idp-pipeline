"""
Main ChatAgent class - High-level interface for Plan-Execute-Respond chat agent
"""

import logging
from typing import Dict, Any, AsyncIterator, Optional, List

from .workflow import ChatAgentWorkflow

logger = logging.getLogger(__name__)

class ChatAgent:
    """
    High-level ChatAgent interface with Plan-Execute-Respond pattern
    
    This agent:
    1. Analyzes queries to determine if tools are needed
    2. Creates execution plans for complex queries  
    3. Executes tasks using MCP tools
    4. Generates comprehensive responses with reference filtering
    5. Supports streaming for real-time user feedback
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
        Initialize the ChatAgent
        
        Args:
            model_id: Bedrock model ID to use
            max_tokens: Maximum tokens for responses
            mcp_config_path: Path to MCP configuration file
            show_thought_process: Whether to show reasoning process
            verbose: Enable verbose logging
        """
        self.workflow = ChatAgentWorkflow(
            model_id=model_id,
            max_tokens=max_tokens,
            mcp_config_path=mcp_config_path,
            show_thought_process=show_thought_process,
            verbose=verbose
        )
        
        logger.info(f"ChatAgent initialized with model {model_id}")

    async def astream(
        self,
        message: str,
        message_history: Optional[List[Dict[str, str]]] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream chat response with Plan-Execute-Respond workflow
        
        Args:
            message: User message
            message_history: Previous conversation history
            index_id: Index ID for context
            document_id: Document ID for context
            segment_id: Segment ID for context
            **kwargs: Additional parameters
            
        Yields:
            Streaming events from the workflow
        """
        async for event in self.workflow.astream(
            input_text=message,
            message_history=message_history,
            index_id=index_id,
            document_id=document_id,
            segment_id=segment_id
        ):
            yield event

    async def ainvoke(
        self,
        message: str,
        message_history: Optional[List[Dict[str, str]]] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get complete chat response without streaming
        
        Args:
            message: User message
            message_history: Previous conversation history
            index_id: Index ID for context
            document_id: Document ID for context
            segment_id: Segment ID for context
            **kwargs: Additional parameters
            
        Returns:
            Complete response with references and updated history
        """
        return await self.workflow.ainvoke(
            input_text=message,
            message_history=message_history,
            index_id=index_id,
            document_id=document_id,
            segment_id=segment_id
        )

    async def startup(self):
        """Initialize the agent and its components"""
        await self.workflow.startup()
        logger.info("ChatAgent startup completed")

    async def shutdown(self):
        """Cleanup agent resources"""
        await self.workflow.shutdown()
        logger.info("ChatAgent shutdown completed")

    def toggle_thought_process(self, show: bool):
        """Toggle whether to show thought process in responses"""
        self.workflow.responder.show_thought_process = show
        return self

    @property
    def model_id(self) -> str:
        """Get current model ID"""
        return self.workflow.model_id

    @property
    def mcp_available(self) -> bool:
        """Check if MCP service is available"""
        return self.workflow.mcp_service is not None

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health status of agent components
        
        Returns:
            Health status information
        """
        status = {
            "agent": True,
            "model": self.model_id,
            "mcp_available": self.mcp_available,
            "timestamp": None
        }
        
        if self.mcp_available:
            try:
                # Check MCP service health
                tools = self.workflow.mcp_service.get_tools()
                status["mcp_tools_count"] = len(tools) if tools else 0
                status["mcp_healthy"] = True
            except Exception as e:
                status["mcp_healthy"] = False
                status["mcp_error"] = str(e)
        
        import time
        status["timestamp"] = time.time()
        
        return status
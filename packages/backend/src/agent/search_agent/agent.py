"""
Search Agent - Main Agent Implementation with Plan-Execute-Respond Pattern
"""
import logging
import asyncio
import traceback
from typing import Dict, Any, List, Optional, AsyncGenerator, Tuple
from datetime import datetime
from strands import Agent

from .config import config
from .prompt import prompt_manager
from .conversation_manager import ConversationManager
from .tools import hybrid_search
from .workflow import PlannerAgent, ExecutorAgent, ResponderAgent, ImageAnalyzerAgent

logger = logging.getLogger(__name__)


class SearchAgent:
    """
    Search Agent using Strands SDK with Agents as Tools pattern
    """

    def __init__(
        self,
        model_id: str = "",
        max_tokens: int = 4096,
        mcp_config_path: str = "",
        reload_prompt: bool = False
    ):
        """
        Initialize Search Agent

        Args:
            model_id: Model ID to use
            max_tokens: Maximum number of tokens
            mcp_config_path: MCP configuration file path (not used, for compatibility)
            reload_prompt: Whether to reload prompt cache
        """
        # Load configuration
        self.config = config
        self.model_id = model_id or config.get_user_model()

        # Load model configuration
        model_config = config.load_model_config(self.model_id)
        self.max_tokens = model_config.get("max_output_tokens", 4096)

        # Initialize prompt manager
        if reload_prompt:
            global prompt_manager
            from .prompt import PromptManager
            prompt_manager = PromptManager(reload=True)

        # Initialize conversation manager
        self.conversation_manager = ConversationManager()

        # Initialize workflow agents
        self.planner = None
        self.executor = None
        self.responder = None
        self.image_analyzer_agent = None

        logger.info(f"Initialized SearchAgent with model: {self.model_id}")

    async def startup(self):
        """Initialize and start the agent"""
        try:
            logger.info("SearchAgent startup() called - beginning initialization...")

            # Initialize tools
            logger.info("Initializing tools...")
            from .tools.hybrid_search import HybridSearchTool

            tools = {
                "hybrid_search": HybridSearchTool(verbose=True)
            }
            logger.info(f"Tools initialized: {list(tools.keys())}")

            # Initialize workflow agents
            logger.info("Initializing workflow agents...")
            self.planner = PlannerAgent(model_id=self.model_id)
            self.executor = ExecutorAgent(tools=tools)
            self.responder = ResponderAgent(model_id=self.model_id)
            self.image_analyzer_agent = ImageAnalyzerAgent(model_id=self.model_id)
            logger.info("Workflow agents initialized")
            logger.info(f"Image analyzer agent initialized: {self.image_analyzer_agent is not None}")

            logger.info("SearchAgent startup completed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def shutdown(self):
        """Shutdown the agent and cleanup resources"""
        try:
            logger.info("SearchAgent shutdown completed")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


    async def ainvoke(
        self,
        message: str,
        message_history: Optional[List[Dict[str, str]]] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke agent asynchronously (non-streaming)

        Args:
            message: User message
            message_history: Previous conversation history
            index_id: Optional index ID
            document_id: Optional document ID
            segment_id: Optional segment ID

        Returns:
            Response dictionary
        """
        try:
            # Format instruction with context
            conversation_text = ""
            if message_history:
                for msg in message_history:
                    conversation_text += f"{msg['role']}: {msg['content']}\n"

            instruction = prompt_manager.format_instruction(
                'orchestrator',
                variables={
                    'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'INDEX_ID': index_id or '',
                    'DOCUMENT_ID': document_id or '',
                    'SEGMENT_ID': segment_id or '',
                    'QUERY': message,
                    'CONVERSATION_HISTORY': conversation_text.strip()
                }
            )

            # Execute
            result = await self.agent.invoke_async(instruction)

            # Extract response
            response_text = ""
            if result and hasattr(result, 'message'):
                response_text = str(result.message)
            else:
                response_text = str(result)

            # Update conversation history
            updated_history = (message_history or []) + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": response_text}
            ]

            return {
                "response": response_text,
                "references": [],  # Will be populated during streaming
                "message_history": updated_history
            }

        except Exception as e:
            logger.error(f"Error in ainvoke: {e}")
            return {
                "response": f"Error: {str(e)}",
                "references": [],
                "message_history": message_history or []
            }

    async def astream(
        self,
        message: str,
        message_history: Optional[List[Dict[str, str]]] = None,
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream agent responses with Plan-Execute-Respond workflow

        Args:
            message: User message
            message_history: Previous conversation history
            index_id: Optional index ID
            document_id: Optional document ID
            segment_id: Optional segment ID
            files: Optional list of uploaded files (for image analysis)

        Yields:
            Event dictionaries compatible with existing router format
        """
        try:
            # Yield workflow start
            yield {
                "type": "workflow_start",
                "message": "Starting search workflow...",
                "timestamp": datetime.now().timestamp()
            }

            # Phase 0: Image Analysis (if files provided)
            enhanced_message = message
            if files and len(files) > 0:
                logger.info(f"Phase 0: Analyzing {len(files)} image(s)")
                logger.info(f"Files received: {[f.get('name') for f in files]}")
                yield {
                    "type": "phase_start",
                    "phase": "image_analysis",
                    "message": f"Analyzing {len(files)} image(s)...",
                    "timestamp": datetime.now().timestamp()
                }

                # Use ImageAnalyzerAgent to analyze images
                image_analysis = await self.image_analyzer_agent.analyze(files)

                if image_analysis:
                    # Yield image analysis result
                    yield {
                        "type": "image_analysis_complete",
                        "analysis": image_analysis,
                        "message": "Image analysis completed",
                        "timestamp": datetime.now().timestamp()
                    }

                    # Enhance user message with image analysis
                    enhanced_message = f"""{message}

[Image Analysis]
{image_analysis}
"""
                    logger.info("User query enhanced with image analysis")
                else:
                    logger.warning("Image analysis returned empty result")
                    yield {
                        "type": "image_analysis_skip",
                        "message": "No images to analyze or analysis failed",
                        "timestamp": datetime.now().timestamp()
                    }

            # Format conversation history
            conversation_text = ""
            if message_history:
                for msg in message_history:
                    conversation_text += f"{msg['role']}: {msg['content']}\n"

            # Tracking variables
            full_response = ""
            collected_references = []
            plan = None
            executed_tasks = []

            # Phase 1: Planning
            logger.info("Phase 1: Planning")
            yield {
                "type": "phase_start",
                "phase": "planning",
                "message": "Analyzing request and creating execution plan...",
                "timestamp": datetime.now().timestamp()
            }

            # Use enhanced_message (with image analysis) for planning
            async for event in self.planner.astream(
                query=enhanced_message,
                index_id=index_id or "",
                document_id=document_id or "",
                segment_id=segment_id or "",
                conversation_history=conversation_text.strip()
            ):
                # Forward planning events
                yield event

                if event["type"] == "plan_complete":
                    plan = event["plan"]
                elif event["type"] == "planning_error":
                    yield {
                        "type": "workflow_error",
                        "phase": "planning",
                        "error": event["error"],
                        "timestamp": datetime.now().timestamp()
                    }
                    return

            if not plan:
                yield {
                    "type": "workflow_error",
                    "phase": "planning",
                    "error": "Failed to generate plan",
                    "timestamp": datetime.now().timestamp()
                }
                return

            # Convert plan dict to Plan object
            from .workflow.state import Plan
            plan_obj = Plan.model_validate(plan)

            # Phase 2: Execution (if tools required)
            if plan_obj.requires_tool and plan_obj.tasks:
                logger.info("Phase 2: Execution")
                yield {
                    "type": "phase_start",
                    "phase": "execution",
                    "message": f"Executing {len(plan_obj.tasks)} tasks...",
                    "timestamp": datetime.now().timestamp()
                }

                async for event in self.executor.astream(plan_obj):
                    # Forward execution events
                    yield event

                    if event["type"] == "execution_complete":
                        executed_tasks = event["executed_tasks"]
                        collected_references = event.get("all_references", [])

            else:
                logger.info("Skipping execution - direct response available")
                yield {
                    "type": "phase_skip",
                    "phase": "execution",
                    "message": "Using direct response, no tool execution needed",
                    "timestamp": datetime.now().timestamp()
                }

            # Phase 3: Response Generation
            logger.info("Phase 3: Response Generation")
            yield {
                "type": "phase_start",
                "phase": "response",
                "message": "Generating comprehensive response...",
                "timestamp": datetime.now().timestamp()
            }

            async for event in self.responder.astream(
                query=message,
                plan=plan_obj,
                executed_tasks=executed_tasks,
                index_id=index_id or "",
                document_id=document_id or "",
                segment_id=segment_id or "",
                conversation_history=conversation_text.strip()
            ):
                # Forward response events
                yield event

                if event["type"] == "response_token":
                    full_response += event["token"]
                elif event["type"] == "response_complete":
                    full_response = event["response"]

            # Update conversation history
            updated_history = (message_history or []) + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": full_response}
            ]

            # Yield references if collected
            if collected_references:
                yield {
                    "type": "references",
                    "references": collected_references,
                    "timestamp": datetime.now().timestamp()
                }

            # Yield workflow completion
            yield {
                "type": "workflow_complete",
                "response": full_response,
                "references": collected_references,
                "message_history": updated_history,
                "message": "Workflow completed successfully",
                "timestamp": datetime.now().timestamp()
            }

        except Exception as e:
            logger.error(f"Error in astream: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            yield {
                "type": "workflow_error",
                "error": str(e),
                "timestamp": datetime.now().timestamp()
            }

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health status of agent components

        Returns:
            Health status information
        """
        status = {
            "agent": True,
            "model": self.model_id,
            "timestamp": datetime.now().timestamp()
        }

        return status

    @property
    def model_id(self) -> str:
        """Get current model ID"""
        return self._model_id

    @model_id.setter
    def model_id(self, value: str):
        """Set model ID"""
        self._model_id = value

"""
Responder Agent - Generates final responses
"""
import logging
from typing import Dict, Any, AsyncIterator, List
from datetime import datetime
from strands import Agent

from .state import Plan
from ..prompt import prompt_manager
from ..config import config

logger = logging.getLogger(__name__)


class ResponderAgent:
    """
    Responder agent that generates final responses with streaming
    """

    def __init__(self, model_id: str = None):
        """Initialize responder agent"""
        self.model_id = model_id or config.get_user_model()
        self.agent = None

    def _create_agent(self):
        """Create Strands agent for response generation"""
        # Get system prompt
        system_prompt = prompt_manager.format_system_prompt(
            'responder',
            variables={
                'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        )

        # Create agent
        self.agent = Agent(
            name="responder",
            system_prompt=system_prompt,
            tools=[],  # No tools for responder
            model=self.model_id,
            callback_handler=None
        )

    async def astream(
        self,
        query: str,
        plan: Plan,
        executed_tasks: List[Dict[str, Any]],
        index_id: str = "",
        document_id: str = "",
        segment_id: str = "",
        conversation_history: str = ""
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream response generation

        Args:
            query: Original user query
            plan: Execution plan
            executed_tasks: Executed tasks with results
            index_id: Index ID for context
            document_id: Document ID for context
            segment_id: Segment ID for context
            conversation_history: Previous conversation

        Yields:
            Response tokens and completion
        """
        try:
            # Create agent if not exists
            if not self.agent:
                self._create_agent()

            # Build execution results text
            results_text = self._build_results_text(executed_tasks)

            # Build plan text
            plan_text = f"Overview: {plan.overview}\n"
            if plan.tasks:
                plan_text += "Tasks:\n"
                for i, task in enumerate(plan.tasks, 1):
                    plan_text += f"{i}. {task.title}: {task.description}\n"

            # Format instruction
            instruction = prompt_manager.format_instruction(
                'responder',
                variables={
                    'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'QUERY': query,
                    'PLAN': plan_text,
                    'RESULTS': results_text,
                    'INDEX_ID': index_id,
                    'DOCUMENT_ID': document_id,
                    'SEGMENT_ID': segment_id,
                    'CONVERSATION_HISTORY': conversation_history
                }
            )

            # Yield response start
            yield {
                "type": "response_start",
                "message": "Generating comprehensive response...",
                "timestamp": datetime.now().timestamp()
            }

            # Stream response tokens
            full_response = ""
            async for event in self.agent.stream_async(instruction):
                # Handle different event types
                if "data" in event:
                    token = event["data"]
                    if token:
                        full_response += token
                        yield {
                            "type": "response_token",
                            "token": token,
                            "timestamp": datetime.now().timestamp()
                        }
                elif "content_delta" in event:
                    delta = event["content_delta"]
                    token = delta.get("text", "")
                    if token:
                        full_response += token
                        yield {
                            "type": "response_token",
                            "token": token,
                            "timestamp": datetime.now().timestamp()
                        }
                elif "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"]
                    if "delta" in delta and "text" in delta["delta"]:
                        token = delta["delta"]["text"]
                        full_response += token
                        yield {
                            "type": "response_token",
                            "token": token,
                            "timestamp": datetime.now().timestamp()
                        }

            # Yield response complete
            yield {
                "type": "response_complete",
                "response": full_response,
                "timestamp": datetime.now().timestamp()
            }

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            yield {
                "type": "response_error",
                "error": str(e),
                "timestamp": datetime.now().timestamp()
            }

    def _build_results_text(self, executed_tasks: List[Dict[str, Any]]) -> str:
        """Build results text from executed tasks"""
        results_parts = []

        for i, task_info in enumerate(executed_tasks, 1):
            task = task_info.get("task")
            success = task_info.get("success", False)

            if not success:
                error = task_info.get("error", "Unknown error")
                results_parts.append(f"Task {i} ({task.title}): Failed - {error}")
                continue

            # Get task result - handle both Task object and dict
            result = ""
            if isinstance(task, dict):
                # Task is a dict (from model_dump)
                result = task.get("result", "")
                task_title = task.get("title", f"Task {i}")
            else:
                # Task is a Task object
                result = task.result if hasattr(task, 'result') and task.result else ""
                task_title = task.title if hasattr(task, 'title') else f"Task {i}"

            if result:
                results_parts.append(f"Task {i} ({task_title}):\n{result}")
            else:
                logger.warning(f"Task {i} has no result content")
                results_parts.append(f"Task {i} ({task_title}): No content available")

        return "\n\n".join(results_parts) if results_parts else "No results available"

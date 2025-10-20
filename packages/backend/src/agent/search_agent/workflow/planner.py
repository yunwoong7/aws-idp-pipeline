"""
Planner Agent - Creates execution plans
"""
import json
import logging
import re
from typing import Dict, Any, AsyncIterator
from datetime import datetime
from strands import Agent

from .state import Plan, Task
from ..prompt import prompt_manager
from ..config import config

logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    Planner agent that creates execution plans with streaming support
    """

    def __init__(self, model_id: str = None):
        """Initialize planner agent"""
        self.model_id = model_id or config.get_user_model()
        self.agent = None

    def _create_agent(self):
        """Create Strands agent for planning"""
        # Get system prompt
        system_prompt = prompt_manager.format_system_prompt(
            'planner',
            variables={
                'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        )

        # Create agent
        self.agent = Agent(
            name="planner",
            system_prompt=system_prompt,
            tools=[],  # No tools for planner
            model=self.model_id,
            callback_handler=None
        )

    async def astream(
        self,
        query: str,
        index_id: str = "",
        document_id: str = "",
        segment_id: str = "",
        conversation_history: str = ""
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream planning process

        Args:
            query: User query to plan for
            index_id: Index ID for context
            document_id: Document ID for context
            segment_id: Segment ID for context
            conversation_history: Previous conversation

        Yields:
            Planning events
        """
        try:
            # Create agent if not exists
            if not self.agent:
                self._create_agent()

            # Format instruction
            instruction = prompt_manager.format_instruction(
                'planner',
                variables={
                    'DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'QUERY': query,
                    'INDEX_ID': index_id,
                    'DOCUMENT_ID': document_id,
                    'SEGMENT_ID': segment_id,
                    'CONVERSATION_HISTORY': conversation_history
                }
            )

            # Yield planning start
            yield {
                "type": "planning_start",
                "message": "Analyzing request and creating execution plan...",
                "timestamp": datetime.now().timestamp()
            }

            # Stream planning tokens
            planning_text = ""
            async for event in self.agent.stream_async(instruction):
                # Handle different event types
                if "data" in event:
                    token = event["data"]
                    if token:
                        planning_text += token
                        yield {
                            "type": "planning_token",
                            "token": token,
                            "timestamp": datetime.now().timestamp()
                        }
                elif "content_delta" in event:
                    delta = event["content_delta"]
                    token = delta.get("text", "")
                    if token:
                        planning_text += token
                        yield {
                            "type": "planning_token",
                            "token": token,
                            "timestamp": datetime.now().timestamp()
                        }

            # Parse planning text to extract JSON
            plan = self._parse_plan(planning_text, index_id)

            # Yield plan complete
            yield {
                "type": "plan_complete",
                "plan": plan.model_dump(),
                "timestamp": datetime.now().timestamp()
            }

        except Exception as e:
            logger.error(f"Planning failed: {e}")
            yield {
                "type": "planning_error",
                "error": str(e),
                "timestamp": datetime.now().timestamp()
            }

    def _parse_plan(self, planning_text: str, index_id: str) -> Plan:
        """Parse planning text to extract Plan object"""
        try:
            # Extract JSON from text (handle markdown code blocks)
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', planning_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find any JSON object
                json_match = re.search(r'\{.*\}', planning_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    # No JSON found, create default plan
                    return Plan(
                        requires_tool=False,
                        overview="Unable to parse plan",
                        tasks=[],
                        reasoning="Failed to parse planning output"
                    )

            # Parse JSON
            plan_dict = json.loads(json_str)

            # Replace {{INDEX_ID}} in tool_args
            if plan_dict.get("tasks"):
                for task in plan_dict["tasks"]:
                    if task.get("tool_args") and "index_id" in task["tool_args"]:
                        if task["tool_args"]["index_id"] == "{{INDEX_ID}}":
                            task["tool_args"]["index_id"] = index_id

            # Create Plan object
            return Plan.model_validate(plan_dict)

        except Exception as e:
            logger.error(f"Failed to parse plan: {e}")
            # Return fallback plan
            return Plan(
                requires_tool=False,
                overview="Plan parsing failed",
                tasks=[],
                reasoning=f"Error: {str(e)}"
            )

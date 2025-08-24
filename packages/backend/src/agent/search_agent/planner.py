"""Search Agent Planner

Generates execution plans for complex search queries.
"""

import json
import yaml
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from .state import ExecutionPlan, PlanStep
from src.agent.react_agent.config import ConfigManager

logger = logging.getLogger(__name__)


class SearchPlanner:
    """Generates execution plans for search queries."""
    
    def __init__(self, model: BaseChatModel, config: ConfigManager):
        self.model = model
        self.config = config
        self.prompt_path = Path(__file__).parent / "prompt" / "planner_prompt.yaml"
        self._load_prompt_template()
    
    def _load_prompt_template(self):
        """Load the planner prompt template."""
        try:
            with open(self.prompt_path, "r", encoding="utf-8") as f:
                self.prompt_config = yaml.safe_load(f)
            logger.info("Planner prompt template loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load planner prompt template: {e}")
            # Fallback minimal template
            self.prompt_config = {
                "system_prompt": "You are a search planner. Create execution plans in JSON format.",
                "user_prompt_template": "Query: {query}\nAvailable tools: {available_tools}"
            }
    
    async def create_plan(
        self,
        query: str,
        available_tools: List[Dict[str, Any]],
        index_id: Optional[str] = None,
        document_id: Optional[str] = None,
        segment_id: Optional[str] = None
    ) -> ExecutionPlan:
        """
        Create an execution plan for the given query.
        
        Args:
            query: User's search query
            available_tools: List of available MCP tools with descriptions
            index_id: Document index ID for context
            document_id: Specific document ID if applicable
            segment_id: Specific segment ID if applicable
            
        Returns:
            ExecutionPlan with steps to execute
        """
        logger.info(f"Creating execution plan for query: {query[:100]}...")
        
        try:
            # Format available tools for the prompt
            tools_description = self._format_tools_for_prompt(available_tools)
            
            # Create the prompt
            system_prompt = self.prompt_config["system_prompt"].format(
                available_tools=tools_description,
                index_id=index_id or "Not specified",
                document_id=document_id or "Not specified", 
                segment_id=segment_id or "Not specified",
                datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            user_prompt = self.prompt_config["user_prompt_template"].format(
                query=query
            )
            
            # Get plan from model
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            logger.debug("Sending planning request to model")
            response = await self.model.ainvoke(messages)
            plan_json = self._extract_json_from_response(response.content)
            
            # Validate and create ExecutionPlan
            plan = self._create_execution_plan(plan_json)
            
            logger.info(f"Created execution plan with {len(plan.plan)} steps")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to create execution plan: {e}")
            # Return a fallback simple plan
            return self._create_fallback_plan(query, available_tools)
    
    def _format_tools_for_prompt(self, available_tools: List[Dict[str, Any]]) -> str:
        """Format available tools for inclusion in prompt."""
        if not available_tools:
            return "No tools available"
        
        formatted_tools = []
        for tool in available_tools:
            tool_desc = f"- **{tool.get('name', 'Unknown')}**: {tool.get('description', 'No description')}"
            
            # Add input schema if available
            if 'inputSchema' in tool and 'properties' in tool['inputSchema']:
                params = tool['inputSchema']['properties']
                param_list = [f"{k}: {v.get('description', 'No description')}" for k, v in params.items()]
                if param_list:
                    tool_desc += f"\n  Parameters: {', '.join(param_list)}"
            
            formatted_tools.append(tool_desc)
        
        return "\n".join(formatted_tools)
    
    def _extract_json_from_response(self, response_content: str) -> Dict[str, Any]:
        """Extract JSON from model response."""
        try:
            # Try to find JSON in the response
            start_idx = response_content.find('{')
            end_idx = response_content.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = response_content[start_idx:end_idx + 1]
                return json.loads(json_str)
            else:
                # If no JSON braces found, try parsing the entire response
                return json.loads(response_content.strip())
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from response: {e}")
            logger.debug(f"Response content: {response_content}")
            raise ValueError(f"Invalid JSON in model response: {e}")
    
    def _create_execution_plan(self, plan_json: Dict[str, Any]) -> ExecutionPlan:
        """Create ExecutionPlan from parsed JSON."""
        if "plan" not in plan_json:
            raise ValueError("Missing 'plan' key in response")
        
        steps = []
        for step_data in plan_json["plan"]:
            try:
                step = PlanStep(
                    step=step_data.get("step", len(steps) + 1),
                    thought=step_data.get("thought", ""),
                    tool_name=step_data.get("tool_name", ""),
                    tool_input=step_data.get("tool_input", {}),
                    status="pending"
                )
                steps.append(step)
            except Exception as e:
                logger.warning(f"Skipping invalid step: {e}")
                continue
        
        if not steps:
            raise ValueError("No valid steps found in plan")
        
        return ExecutionPlan(plan=steps, total_steps=len(steps))
    
    def _create_fallback_plan(self, query: str, available_tools: List[Dict[str, Any]]) -> ExecutionPlan:
        """Create a simple fallback plan when planning fails."""
        logger.warning("Creating fallback execution plan")
        
        if not available_tools:
            logger.error("No tools available for fallback plan")
            raise ValueError("Cannot create fallback plan: no tools available")
        
        # Try to find a search tool as fallback
        search_tool = None
        for tool in available_tools:
            tool_name = tool.get("name", "").lower()
            if any(keyword in tool_name for keyword in ["search", "find", "query", "hybrid"]):
                search_tool = tool
                break
        
        if search_tool:
            fallback_step = PlanStep(
                step=1,
                thought=f"Perform a basic search to find relevant information for the query: {query}",
                tool_name=search_tool["name"],
                tool_input={"query": query, "index_id": "{index_id}"},
                status="pending"
            )
        else:
            # Use the first available tool
            first_tool = available_tools[0]
            fallback_step = PlanStep(
                step=1,
                thought="Execute available tool to gather information",
                tool_name=first_tool["name"],
                tool_input={"query": query},
                status="pending"
            )
        
        return ExecutionPlan(plan=[fallback_step], total_steps=1)
"""Search Agent Executor

Executes the steps in the generated execution plan.
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, AsyncGenerator, TYPE_CHECKING
from datetime import datetime
import time

from src.mcp_client.mcp_service import MCPService
from .state import (
    ExecutionPlan, 
    ExecutionResult, 
    SearchState,
    StepExecutingEvent,
    StepCompletedEvent
)

if TYPE_CHECKING:
    from .state import PlanStep

logger = logging.getLogger(__name__)


class SearchExecutor:
    """Executes search plans step by step."""
    
    def __init__(self, mcp_service: MCPService):
        self.mcp_service = mcp_service
        self._next_source_id = 1
    
    async def execute_plan(
        self,
        plan: ExecutionPlan,
        search_state: SearchState
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute the execution plan step by step with streaming events.
        
        Args:
            plan: The execution plan to execute
            search_state: Current search state
            
        Yields:
            Dictionary events for step execution progress
        """
        logger.info(f"Starting execution of plan with {len(plan.plan)} steps")
        
        search_state.phase = "executing"
        execution_results = []
        
        for step in plan.plan:
            try:
                # Update step status and emit event
                step.status = "executing"
                search_state.current_step = step.step
                
                yield {
                    "type": "step_executing",
                    "step": step.step,
                    "thought": step.thought,
                    "tool_name": step.tool_name,
                    "timestamp": datetime.now().isoformat()
                }
                
                logger.info(f"Executing step {step.step}: {step.tool_name}")
                
                # Execute the step
                result = await self._execute_step(step, search_state)
                execution_results.append(result)
                
                # Update step status
                step.status = "completed" if result.success else "failed"
                step.result_summary = result.result_summary
                step.source_id = result.source_id
                
                # Emit completion event
                # Extract references from result_data if available
                refs = []
                try:
                    if isinstance(result.result_data, dict) and "references" in result.result_data:
                        refs = result.result_data.get("references", [])
                except Exception:
                    refs = []

                yield {
                    "type": "step_completed",
                    "step": step.step,
                    "success": result.success,
                    "result_summary": result.result_summary,
                    "source_id": result.source_id,
                    "execution_time": result.execution_time,
                    "references": refs,
                    "timestamp": datetime.now().isoformat()
                }
                
                if not result.success:
                    logger.warning(f"Step {step.step} failed: {result.error_message}")
                    # Continue with next step despite failure
                
                # Small delay between steps for better UX
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error executing step {step.step}: {e}")
                step.status = "failed"
                
                # Create failed result
                failed_result = ExecutionResult(
                    step_number=step.step,
                    tool_name=step.tool_name,
                    success=False,
                    result_data={},
                    source_id=self._get_next_source_id(),
                    error_message=str(e),
                    execution_time=0.0,
                    result_summary=f"Failed to execute {step.tool_name}: {str(e)}"
                )
                execution_results.append(failed_result)
                
                yield {
                    "type": "step_completed",
                    "step": step.step,
                    "success": False,
                    "result_summary": failed_result.result_summary,
                    "source_id": failed_result.source_id,
                    "execution_time": 0.0,
                    "timestamp": datetime.now().isoformat()
                }
        
        # Update search state with results
        search_state.execution_results = execution_results
        search_state.phase = "synthesizing"
        
        logger.info(f"Completed execution of {len(execution_results)} steps")
    
    async def _execute_step(self, step: "PlanStep", search_state: SearchState) -> ExecutionResult:
        """Execute a single step."""
        start_time = time.time()
        source_id = self._get_next_source_id()
        
        try:
            # Prepare tool input with context
            tool_input = self._prepare_tool_input(step.tool_input, search_state)
            
            logger.debug(f"Executing {step.tool_name} with input: {tool_input}")
            
            # Execute the MCP tool via client
            client = self.mcp_service.get_client()
            if not client:
                raise Exception("MCP client is not available")
            
            # Find the tool by name
            tools = self.mcp_service.get_tools()
            target_tool = None
            for tool in tools:
                if hasattr(tool, 'name') and tool.name == step.tool_name:
                    target_tool = tool
                    break
            
            if not target_tool:
                raise Exception(f"Tool '{step.tool_name}' not found in available tools")
            
            # Execute the tool
            raw_result = await target_tool.ainvoke(tool_input)
            
            # Handle different result formats
            if isinstance(raw_result, str):
                # Try to parse JSON string
                try:
                    result_data = json.loads(raw_result)
                except json.JSONDecodeError:
                    # If not JSON, wrap in dict
                    result_data = {"content": raw_result}
            elif isinstance(raw_result, dict):
                result_data = raw_result
            else:
                # Convert other types to dict
                result_data = {"result": str(raw_result)}
            
            execution_time = time.time() - start_time
            
            # Process and summarize the result
            result_summary = self._create_result_summary(step.tool_name, result_data)
            
            return ExecutionResult(
                step_number=step.step,
                tool_name=step.tool_name,
                success=True,
                result_data=result_data,
                source_id=source_id,
                execution_time=execution_time,
                result_summary=result_summary
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Tool execution failed for {step.tool_name}: {e}")
            
            return ExecutionResult(
                step_number=step.step,
                tool_name=step.tool_name,
                success=False,
                result_data={},
                source_id=source_id,
                error_message=str(e),
                execution_time=execution_time,
                result_summary=f"Failed to execute {step.tool_name}: {str(e)}"
            )
    
    def _prepare_tool_input(self, tool_input: Dict[str, Any], search_state: SearchState) -> Dict[str, Any]:
        """Prepare tool input with context information."""
        prepared_input = tool_input.copy()
        
        # Add context if not already present
        if search_state.index_id and "index_id" not in prepared_input:
            prepared_input["index_id"] = search_state.index_id
        
        if search_state.document_id and "document_id" not in prepared_input:
            prepared_input["document_id"] = search_state.document_id
        
        if search_state.segment_id and "segment_id" not in prepared_input:
            prepared_input["segment_id"] = search_state.segment_id
        
        # Process template variables in input values
        for key, value in prepared_input.items():
            if isinstance(value, str):
                prepared_input[key] = self._process_template_variables(value, search_state)
        
        return prepared_input
    
    def _process_template_variables(self, text: str, search_state: SearchState) -> str:
        """Process template variables like {query} in input values."""
        replacements = {
            "{query}": search_state.query,
            "{index_id}": search_state.index_id or "",
            "{document_id}": search_state.document_id or "",
            "{segment_id}": search_state.segment_id or ""
        }
        
        result = text
        for var, replacement in replacements.items():
            result = result.replace(var, replacement)
        
        return result
    
    def _create_result_summary(self, tool_name: str, result_data: Dict[str, Any]) -> str:
        """Create a human-readable summary of the tool execution result."""
        try:
            # Handle different types of tool results
            if isinstance(result_data, dict):
                if "results" in result_data and isinstance(result_data["results"], list):
                    # Search-type results
                    count = len(result_data["results"])
                    return f"{tool_name} found {count} results"
                
                elif "content" in result_data:
                    # Content extraction results
                    content_len = len(str(result_data["content"]))
                    return f"{tool_name} extracted {content_len} characters of content"
                
                elif "analysis" in result_data:
                    # Analysis results
                    return f"{tool_name} completed analysis"
                
                elif "summary" in result_data:
                    # Summary results
                    summary_len = len(str(result_data["summary"]))
                    return f"{tool_name} generated {summary_len} character summary"
                
                else:
                    # Generic result
                    return f"{tool_name} executed successfully"
            
            elif isinstance(result_data, list):
                return f"{tool_name} returned {len(result_data)} items"
            
            else:
                return f"{tool_name} executed successfully"
                
        except Exception as e:
            logger.warning(f"Failed to create result summary: {e}")
            return f"{tool_name} executed"
    
    def _get_next_source_id(self) -> int:
        """Get the next available source ID for citation."""
        source_id = self._next_source_id
        self._next_source_id += 1
        return source_id
"""
Executor Agent - Executes tasks from the plan
"""
import logging
import time
from typing import Dict, Any, AsyncIterator, List

from .state import Plan, Task, TaskStatus
from ..tools.base import BaseTool

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    Executor agent that runs tasks using tools
    """

    def __init__(self, tools: Dict[str, BaseTool] = None):
        """
        Initialize executor agent

        Args:
            tools: Dictionary of tool instances keyed by tool name
        """
        self.tools = tools or {}

    async def astream(
        self,
        plan: Plan
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream task execution with real-time updates

        Args:
            plan: Execution plan with tasks

        Yields:
            Execution updates and results
        """
        if not plan.tasks:
            logger.warning("No tasks to execute")
            yield {
                "type": "execution_skip",
                "message": "No tasks to execute",
                "timestamp": time.time()
            }
            return

        logger.info(f"Executing {len(plan.tasks)} tasks...")

        executed_tasks = []
        all_references = []

        for i, task in enumerate(plan.tasks):
            task_start_time = time.time()

            # Update task status
            task.status = TaskStatus.EXECUTING

            yield {
                "type": "task_start",
                "task_index": i,
                "task": task.model_dump(),
                "message": f"Executing: {task.title}",
                "timestamp": time.time()
            }

            try:
                # Execute tool
                logger.info(f"Executing task: {task.title} with tool: {task.tool_name}")

                # Get tool from registry
                tool = self.tools.get(task.tool_name)

                if not tool:
                    # Unknown tool
                    task.status = TaskStatus.FAILED
                    task.result = f"Unknown tool: {task.tool_name}"
                    task.execution_time = time.time() - task_start_time
                    logger.error(f"Tool not found: {task.tool_name}")
                else:
                    # Execute tool using BaseTool interface
                    tool_result = await tool.execute(**task.tool_args)

                    # Process standardized ToolResult
                    references = []

                    if tool_result["success"]:
                        # Success case
                        task.status = TaskStatus.COMPLETED
                        task.result = tool_result["llm_text"] or "Task completed"
                        task.execution_time = time.time() - task_start_time

                        # Collect references
                        references = tool_result.get("references", [])
                        all_references.extend(references)

                        logger.info(f"Tool executed successfully: {tool_result['count']} results")

                    else:
                        # Error case
                        error_msg = tool_result.get("error", "Unknown error")
                        task.status = TaskStatus.FAILED
                        task.result = error_msg
                        task.execution_time = time.time() - task_start_time
                        logger.error(f"Tool execution failed: {error_msg}")

                # Store execution info (convert task to dict for serialization)
                executed_task_info = {
                    "task": task.model_dump(),  # Convert to dict
                    "success": task.status == TaskStatus.COMPLETED,
                    "execution_time": task.execution_time
                }
                executed_tasks.append(executed_task_info)

                logger.info(f"Task completed in {task.execution_time:.2f}s")

                yield {
                    "type": "task_complete",
                    "task_index": i,
                    "task": task.model_dump(),
                    "references": references,
                    "execution_time": task.execution_time,
                    "message": f"Completed: {task.title}",
                    "timestamp": time.time()
                }

            except Exception as e:
                logger.error(f"Task execution failed: {e}")

                task.status = TaskStatus.FAILED
                task.result = str(e)
                task.execution_time = time.time() - task_start_time

                executed_task_info = {
                    "task": task.model_dump(),  # Convert to dict
                    "success": False,
                    "execution_time": task.execution_time,
                    "error": str(e)
                }
                executed_tasks.append(executed_task_info)

                yield {
                    "type": "task_failed",
                    "task_index": i,
                    "task": task.model_dump(),
                    "error": str(e),
                    "execution_time": task.execution_time,
                    "message": f"Failed: {task.title}",
                    "timestamp": time.time()
                }

        # Summary
        successful_count = sum(1 for task_info in executed_tasks if task_info["success"])
        logger.info(f"Execution complete: {successful_count}/{len(executed_tasks)} successful")

        yield {
            "type": "execution_complete",
            "total_tasks": len(executed_tasks),
            "successful_tasks": successful_count,
            "failed_tasks": len(executed_tasks) - successful_count,
            "executed_tasks": executed_tasks,
            "all_references": all_references,
            "message": f"Execution complete: {successful_count}/{len(executed_tasks)} successful",
            "timestamp": time.time()
        }

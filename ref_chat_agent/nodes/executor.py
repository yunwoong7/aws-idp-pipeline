# src/agent/nodes/executor.py
from typing import cast
from colorama import Fore, Style
from langchain_core.tools import StructuredTool
from src.chat_agent.states.schemas import AgentState, Task
import time

# ===== Define the Executor class =====
class ExecutorNode:
    def __init__(self, tools: list[StructuredTool], verbose: bool = False) -> None:
        self.tools = {tool.name: tool for tool in tools}
        self.verbose = verbose

    def __call__(self, state: AgentState) -> AgentState:
        """Execute remaining tasks in the plan"""
        if not state.plan or not state.plan.tasks:
            print("\n📝 No tasks to execute")
            return state

        executed_tasks = []
        remaining_tasks = []

        print(Fore.GREEN + "\n🎯 Executing tasks" + Style.RESET_ALL)

        if self.verbose:
            print(Fore.WHITE + "────────────────────────────────────────────────────" + Style.RESET_ALL)
            print(Fore.WHITE + f"▶️ Executing task: {task.title}" + Style.RESET_ALL)

        tool_start_time = time.time()
        task = state.plan.tasks.pop(0)
        tool = self.tools[task.tool_name]

        try:
            result = tool.invoke(task.tool_args)
            executed_tasks.append({
                "task": task,
                "result": result,
                "success": True
            })
            tool_elapsed = time.time() - tool_start_time
            print(Fore.YELLOW + f"⏱️ Task took: {tool_elapsed:.2f} seconds" + Style.RESET_ALL)
        except Exception as e:
            print(f"❌ Task failed: {str(e)}")
            executed_tasks.append({
                "task": task,
                "result": str(e),
                "success": False
            })
            remaining_tasks.append(task)
        
        # Save execution results
        return {
            **state.model_dump(),
            "executed_tasks": executed_tasks,
            "remaining_tasks": remaining_tasks,
        }

    def _format_results(self, executed_tasks: list[dict]) -> str:
        """Format execution results for next steps"""
        result_str = []
        for exec_task in executed_tasks:
            task = exec_task["task"]
            result = exec_task["result"]
            success = exec_task["success"]
            
            result_str.append(f"Task: {task.title}")
            result_str.append(f"Status: {'Success' if success else 'Failed'}")
            result_str.append(f"Result: {result}")
            result_str.append("")
            
        return "\n".join(result_str)
    
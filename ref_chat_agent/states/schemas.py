#src/agent/states/schemas.py
from pydantic import BaseModel, Field
from typing import List, Dict
from colorama import Fore, Style 

# ===== Define the structure of the task =====
class Task(BaseModel):
    """A single task in the plan"""
    title: str = Field(default=None, description="The title of the task")
    tool_name: str|None = Field(alias="toolName", default="", description="The name of the tool to use for this task")
    tool_args: dict = Field(alias="toolArgs", default={}, description="The arguments to be passed to the tool")
    description: str = Field(default="", description="The detailed description of what needs to be done")
    
    def __str__(self) -> str:
        task_str = []
        if self.title:
            task_str.append(f"🔸 {self.title}")
        if self.tool_name:
            task_str.append(f"[Tool: {self.tool_name}]")
            task_str.append(f"[Args: {self.tool_args}]")
        if self.description:
            task_str.append(f"[{self.description}]")
        return " ".join(task_str)


# ===== Define the structure of the plan =====
class Plan(BaseModel):
    """Plan consists of tasks to complete a given query"""
    requires_tool: bool = Field(alias="requiresTool", default=False, description="Whether the plan requires a tool to execute")
    direct_response: str = Field(alias="directResponse", default="", description="Direct response if no tool is required") 
    overview: str = Field(default="", description="Brief overview of the plan")
    tasks: List[Task] = Field(default_factory=list, description="List of tasks to execute")
    
    def __str__(self) -> str:
        """Regular string representation for normal display"""
        plan_str = [
            # "────────────────────────────────────────────────────",
            f"🚀 Requires Tool: {self.requires_tool}",
        ]

        if self.direct_response:
            plan_str.append(f"📝 Direct Response: {self.direct_response}")
        
        if self.overview:
            plan_str.append(f"📋 Overview: {self.overview}")
        
        if self.tasks:
            plan_str.append("🔸 Tasks")
        
        for i, task in enumerate(self.tasks, 1):
            plan_str.append(f"{i}. {task.title}")
            if task.tool_name:
                plan_str.append(f"   Tool: {task.tool_name}")
                plan_str.append(f"   Args: {task.tool_args}")
            plan_str.append(f"   Description: {task.description}")
            plan_str.append("")
            
        # plan_str.append("────────────────────────────────────────────────────")
        return "\n".join(plan_str)
    

# ===== Define the structure of the agent state =====
class AgentState(BaseModel):
    """manage the state of the agent"""
    input: str
    plan: Plan
    executed_tasks: List[Dict] = []
    remaining_tasks: List[Task] = []
    response: str = ""
    message_history: List[Dict] = []
    references: List = []

    def initial_state():
        return AgentState(
            input="",
            plan=Plan(
                requires_tool=False,
                direct_response="",
                overview="",
                tasks=[]
            ),
            executed_tasks=[],
            remaining_tasks=[],
            response="",
            message_history=[],
            references=[]
        )
    
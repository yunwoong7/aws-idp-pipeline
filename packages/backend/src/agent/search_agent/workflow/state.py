"""
State models for Plan-Execute-Respond workflow
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum


class TaskStatus(str, Enum):
    """Task execution status"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """A single task in the execution plan"""
    title: str = Field(description="The title of the task")
    tool_name: Optional[str] = Field(default=None, description="The name of the tool to use")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")
    description: str = Field(default="", description="Detailed description of the task")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current status of the task")
    result: Optional[str] = Field(default=None, description="Result of task execution")
    execution_time: Optional[float] = Field(default=None, description="Time taken to execute the task")


class Plan(BaseModel):
    """Execution plan containing tasks and routing decisions"""
    requires_tool: bool = Field(default=False, description="Whether tools are required")
    direct_response: Optional[str] = Field(default=None, description="Direct response if no tools needed")
    overview: str = Field(default="", description="Brief overview of the plan")
    tasks: List[Task] = Field(default_factory=list, description="List of tasks to execute")
    reasoning: Optional[str] = Field(default=None, description="Reasoning behind the plan")

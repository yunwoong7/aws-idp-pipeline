"""
State management for Search Agent
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
    tool_name: Optional[str] = Field(default=None, description="The name of the MCP tool to use")
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

class Reference(BaseModel):
    """Reference information for citations"""
    id: str = Field(description="Unique reference ID")
    type: str = Field(description="Type of reference (link, image, document, etc.)")
    value: str = Field(description="Reference value (URL, path, etc.)")
    title: Optional[str] = Field(default=None, description="Reference title")
    description: Optional[str] = Field(default=None, description="Reference description")

class SearchState(BaseModel):
    """Complete state of the search agent"""
    input: str = Field(description="User input")
    plan: Optional[Plan] = Field(default=None, description="Generated execution plan")
    executed_tasks: List[Dict[str, Any]] = Field(default_factory=list, description="Completed tasks")
    response: str = Field(default="", description="Final response")
    raw_response: str = Field(default="", description="Raw response before processing")
    message_history: List[Dict[str, str]] = Field(default_factory=list, description="Conversation history")
    references: List[Reference] = Field(default_factory=list, description="Reference citations")
    
    # Context fields for MCP tool calls
    index_id: Optional[str] = Field(default=None, description="Index ID for document search context")
    document_id: Optional[str] = Field(default=None, description="Document ID for specific document context")
    segment_id: Optional[str] = Field(default=None, description="Segment ID for specific segment context")
    @classmethod
    def initial_state(cls, input_text: str = "", message_history: List[Dict[str, str]] = None, **kwargs) -> "SearchState":
        """Create initial state"""
        return cls(
            input=input_text,
            plan=None,
            executed_tasks=[],
            response="",
            raw_response="",
            message_history=message_history or [],
            references=[],
            **kwargs
        )
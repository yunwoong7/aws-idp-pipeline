"""Search Agent State Models

Defines state management for Plan-and-Execute search workflow.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class PlanStep(BaseModel):
    """A single step in the execution plan."""
    
    step: int = Field(description="Step number in the plan")
    thought: str = Field(description="Reasoning behind this step")
    tool_name: str = Field(description="Name of the tool to execute")
    tool_input: Dict[str, Any] = Field(description="Input parameters for the tool")
    status: Literal["pending", "executing", "completed", "failed"] = Field(
        default="pending", description="Current status of this step"
    )
    result_summary: Optional[str] = Field(
        default=None, description="Summary of execution result"
    )
    source_id: Optional[int] = Field(
        default=None, description="Unique ID for citation reference"
    )


class ExecutionPlan(BaseModel):
    """Complete execution plan with all steps."""
    
    plan: List[PlanStep] = Field(description="List of execution steps")
    created_at: datetime = Field(default_factory=datetime.now)
    total_steps: int = Field(description="Total number of steps in the plan")
    
    def __init__(self, **data):
        super().__init__(**data)
        self.total_steps = len(self.plan)


class ExecutionResult(BaseModel):
    """Result from executing a plan step."""
    
    step_number: int = Field(description="Step number that was executed")
    tool_name: str = Field(description="Name of the tool that was executed")
    success: bool = Field(description="Whether execution was successful")
    result_data: Dict[str, Any] = Field(description="Raw result data from tool")
    source_id: int = Field(description="Unique ID for citation reference")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    execution_time: float = Field(description="Time taken to execute in seconds")
    result_summary: str = Field(description="Human-readable summary of the result")


class SearchState(BaseModel):
    """Overall state of the search agent."""
    
    query: str = Field(description="Original user query")
    phase: Literal["planning", "executing", "synthesizing", "completed", "error"] = Field(
        default="planning", description="Current phase of execution"
    )
    plan: Optional[ExecutionPlan] = Field(default=None, description="Generated execution plan")
    execution_results: List[ExecutionResult] = Field(
        default_factory=list, description="Results from executed steps"
    )
    current_step: int = Field(default=0, description="Currently executing step number")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = Field(default=None, description="When execution completed")
    
    # Context information
    index_id: Optional[str] = Field(default=None, description="Document index ID")
    document_id: Optional[str] = Field(default=None, description="Specific document ID")
    segment_id: Optional[str] = Field(default=None, description="Specific segment ID")
    
    def mark_completed(self):
        """Mark the search as completed."""
        self.phase = "completed"
        self.completed_at = datetime.now()
    
    def mark_error(self, error_message: str):
        """Mark the search as failed with error."""
        self.phase = "error"
        self.error_message = error_message
        self.completed_at = datetime.now()
    
    def next_step(self):
        """Move to the next step in execution."""
        self.current_step += 1
        if self.plan and self.current_step >= len(self.plan.plan):
            self.phase = "synthesizing"


class CitationData(BaseModel):
    """Citation information for text chunks."""
    
    target_text_id: str = Field(description="ID of the text chunk to cite")
    source_ids: List[int] = Field(description="List of source IDs to cite")


class TextChunk(BaseModel):
    """A chunk of text in the final answer."""
    
    text_id: str = Field(description="Unique ID for this text chunk")
    content: str = Field(description="Text content")
    citations: List[int] = Field(default_factory=list, description="Source IDs for citations")


class StreamEvent(BaseModel):
    """Base class for streaming events."""
    
    type: str = Field(description="Type of the event")
    timestamp: datetime = Field(default_factory=datetime.now)


class PlanGeneratedEvent(StreamEvent):
    """Event when plan is generated."""
    
    type: Literal["plan_generated"] = "plan_generated"
    plan: List[Dict[str, Any]] = Field(description="Generated execution plan")


class StepExecutingEvent(StreamEvent):
    """Event when a step starts executing."""
    
    type: Literal["step_executing"] = "step_executing"
    step: int = Field(description="Step number being executed")
    thought: str = Field(description="Reasoning for this step")
    tool_name: str = Field(description="Tool being executed")


class StepCompletedEvent(StreamEvent):
    """Event when a step completes."""
    
    type: Literal["step_completed"] = "step_completed"
    step: int = Field(description="Step number that completed")
    success: bool = Field(description="Whether step was successful")
    result_summary: str = Field(description="Summary of the result")
    source_id: int = Field(description="Source ID for citation")


class SynthesizingStartEvent(StreamEvent):
    """Event when answer synthesis begins."""
    
    type: Literal["synthesizing_start"] = "synthesizing_start"
    message: str = Field(default="Starting to synthesize final answer...")


class TextChunkEvent(StreamEvent):
    """Event for streaming text chunks."""
    
    type: Literal["text_chunk"] = "text_chunk"
    text_id: str = Field(description="Unique ID for this text chunk")
    text: str = Field(description="Text content")


class CitationEvent(StreamEvent):
    """Event for citation data."""
    
    type: Literal["citation_data"] = "citation_data"
    target_text_id: str = Field(description="ID of text chunk to cite")
    source_ids: List[int] = Field(description="Source IDs for citation")


class StreamEndEvent(StreamEvent):
    """Event marking end of stream."""
    
    type: Literal["stream_end"] = "stream_end"
    message: str = Field(default="Search completed successfully")


class ErrorEvent(StreamEvent):
    """Event for errors."""
    
    type: Literal["error"] = "error"
    error_message: str = Field(description="Error message")
    error_code: Optional[str] = Field(default=None, description="Error code")
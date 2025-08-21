# packages/backend/src/agent/analysis_agent/state/model.py
from typing import List, Optional, Any
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

class InputState(BaseModel):
    """Input state model (same as backend)"""
    messages: List[BaseMessage] = Field(default_factory=list, description="Conversation messages list")
    index_id: Optional[str] = Field(default=None, description="Index ID")

class State(BaseModel):
    """Full state model (same as backend)"""
    messages: List[BaseMessage] = Field(default_factory=list, description="Conversation messages list")
    index_id: Optional[str] = Field(default=None, description="Index ID")
    current_step: int = Field(default=0, description="Current execution step")
    max_iterations: int = Field(default=10, description="Maximum iterations")
    
    class Config:
        arbitrary_types_allowed = True 
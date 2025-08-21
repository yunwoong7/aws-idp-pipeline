"""
LangGraph State model for Agent Context sharing
Contains agent context data that needs to be shared across all workflow nodes and tools
"""

from typing import Dict, Any, List, Optional, TypedDict
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    LangGraph State container for sharing agent context data
    This replaces the tool_registry context approach with proper State-based sharing
    """
    # Standard LangGraph fields
    messages: List[BaseMessage]
    
    # Agent context fields
    index_id: str
    document_id: Optional[str]
    segment_id: Optional[str]  
    segment_index: Optional[int]
    media_type: Optional[str]
    file_path: Optional[str] 
    image_path: Optional[str]
    segment_type: Optional[str]
    start_timecode_smpte: Optional[str]
    end_timecode_smpte: Optional[str]
    
    # Session and execution context
    session_id: Optional[str]
    thread_id: Optional[str]
    user_query: Optional[str]
    
    # Analysis context
    previous_analysis_context: Optional[str]
    current_step: int
    max_iterations: int
    
    # Tool execution tracking
    tools_used: List[str]
    tool_results: List[Dict[str, Any]]
    tool_references: List[Dict[str, Any]]
    tool_content: Optional[str]
    
    # Real-time analysis history
    analysis_history: List[Dict[str, Any]]
    combined_analysis_context: Optional[str]
    
    # OpenSearch and processing flags
    skip_opensearch_query: bool
    enable_opensearch: bool
"""
Vision ReAct Agent State definition
"""

from typing import List, Dict, Any, Optional, TypedDict

class AgentState(TypedDict):
    """Agent state for Vision ReAct"""
    # Basic info
    index_id: str
    document_id: str
    segment_id: str
    segment_index: int
    
    # Image and file paths
    image_uri: str
    file_path: Optional[str]
    
    # User query and context
    user_query: str
    previous_analysis_context: str
    
    # ReAct specific fields
    iteration_count: int
    max_iterations: int
    thoughts: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    next_action: Optional[Dict[str, Any]]
    should_continue: bool
    
    # Results
    final_response: Optional[str]
    references: List[Dict[str, Any]]
    
    # Media type info
    media_type: str
    segment_type: Optional[str]
    start_timecode_smpte: Optional[str]
    end_timecode_smpte: Optional[str]
    
    # Thread ID for continuity
    thread_id: Optional[str]
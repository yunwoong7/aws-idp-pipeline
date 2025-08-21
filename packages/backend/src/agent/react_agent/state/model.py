from typing import List, Dict, Any, Optional, Annotated
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
import operator

def replace_tool_references(left: List[Dict[str, Any]], right: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Simple replacement function for tool_references - always use new value
    This allows explicit clearing with update_state({"tool_references": []})
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"replace_tool_references: left={len(left) if left else 0}, right={len(right) if right else 0}")
    logger.info(f"replace_tool_references: returning {len(right) if right else 0} references")
    
    return right

def manage_conversation_history(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """
    Manage conversation history with size limits and system message deduplication
    
    Args:
        left: Existing messages
        right: New messages to add
        
    Returns:
        Combined list of messages with size management and no duplicate system messages
    """
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    
    if not right:
        return left
    if not left:
        return right
    
    # 🔧 시스템 메시지 중복 방지 로직
    # 1. left와 right에서 시스템 메시지와 일반 대화 분리
    left_system_messages = [msg for msg in left if isinstance(msg, SystemMessage)]
    left_conversation = [msg for msg in left if not isinstance(msg, SystemMessage)]
    
    right_system_messages = [msg for msg in right if isinstance(msg, SystemMessage)]
    right_conversation = [msg for msg in right if not isinstance(msg, SystemMessage)]
    
    # 2. 시스템 메시지는 가장 최신 것만 유지 (right가 더 최신)
    final_system_messages = []
    if right_system_messages:
        final_system_messages = [right_system_messages[-1]]  # 가장 최신 것만
    elif left_system_messages:
        final_system_messages = [left_system_messages[-1]]  # 가장 최신 것만
    
    # 3. 일반 대화는 그대로 결합
    combined_conversation = left_conversation + right_conversation
    
    # 4. 최종 메시지 구성: 시스템 메시지 + 일반 대화
    combined = final_system_messages + combined_conversation
    
    # 5. 메시지 수 제한 (시스템 메시지는 제외하고 일반 대화만 제한)
    MAX_CONVERSATION_MESSAGES = 10
    if len(combined_conversation) > MAX_CONVERSATION_MESSAGES:
        # 시스템 메시지는 유지하고 일반 대화만 제한
        recent_conversation = combined_conversation[-MAX_CONVERSATION_MESSAGES:]
        combined = final_system_messages + recent_conversation
    
    return combined

class InputState(BaseModel):
    """Agent input state class"""
    messages: List[BaseMessage] = Field(default_factory=list)
    message_history: List[Dict] = Field(default_factory=list)
    index_id: Optional[str] = Field(default=None, description="Index ID")
    document_id: Optional[str] = Field(default=None, description="Document ID")
    segment_id: Optional[str] = Field(default=None, description="Segment ID")
    
class State(BaseModel):
    """Agent state class"""
    messages: Annotated[List[BaseMessage], manage_conversation_history] = Field(default_factory=list)
    is_last_step: bool = False
    message_history: List[Dict] = Field(default_factory=list)
    tool_references: Annotated[List[Dict[str, Any]], replace_tool_references] = Field(default_factory=list)
    tool_content: Optional[str] = Field(default="", description="Tool execution result content")
    
    # 대화 요약 관리
    conversation_summary: Optional[str] = Field(default="", description="대화 요약 내용")
    message_count: int = Field(default=0, description="총 메시지 수")
    needs_summarization: bool = Field(default=False, description="요약 필요 여부")
    last_summarization_at: int = Field(default=0, description="마지막 요약 시 메시지 수")
    
    # Context information for MCP tools
    index_id: Optional[str] = Field(default=None, description="Index ID")
    document_id: Optional[str] = Field(default=None, description="Document ID")
    page_id: Optional[str] = Field(default=None, description="Page ID")
    page_index: Optional[int] = Field(default=None, description="Page index (0-based)")
    file_path: Optional[str] = Field(default=None, description="File path")
    image_path: Optional[str] = Field(default=None, description="Image path")
    user_query: Optional[str] = Field(default=None, description="User query")
    thread_id: Optional[str] = Field(default=None, description="Thread ID")
    session_id: Optional[str] = Field(default=None, description="Session ID")
    
    def __init__(self, **data: Any):
        super().__init__(**data)
        
    def get_context(self) -> Dict[str, Any]:
        """Return context information for MCP tools"""
        return {
            "index_id": self.index_id,
            "document_id": self.document_id,
            "page_id": self.page_id,
            "page_index": self.page_index,
            "file_path": self.file_path,
            "image_path": self.image_path,
            "user_query": self.user_query,
            "thread_id": self.thread_id,
            "session_id": self.session_id,
        }
        

"""
State-aware base tool class for LangGraph integration
Tools that extend this class will automatically receive agent context from LangGraph State
"""

import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
from langchain_core.tools import BaseTool as LangChainBaseTool
from agent.tools.base import ToolResult

logger = logging.getLogger(__name__)


class StateAwareBaseTool(LangChainBaseTool, ABC):
    """
    Base class for tools that need access to LangGraph State
    Automatically extracts agent context from State instead of tool_registry
    """
    def _run(self, **kwargs) -> str:
        """LangChain required method - delegates to execute"""
        # Try to get state from LangGraph context if available
        if hasattr(self, '_current_state') and self._current_state:
            logger.info(f"🔗 StateAware 도구 '{self.name}' 상태 기반 실행 중...")
            logger.info(f"🔍 상태 정보: document_id={self._current_state.get('document_id')}")
            result = self.execute_with_state(self._current_state, **kwargs)
        else:
            # Fallback to regular execute without state
            logger.warning(f"❌ StateAware 도구 '{self.name}': No LangGraph State available, executing without state context")
            logger.warning(f"❌ hasattr(_current_state): {hasattr(self, '_current_state')}")
            if hasattr(self, '_current_state'):
                logger.warning(f"❌ _current_state value: {self._current_state}")
            result = self.execute(**kwargs)
        
        # 도구 실행 결과를 컨테이너에 저장 (model_node에서 수집용)
        logger.info(f"🔍 도구 '{self.name}' 실행 완료 - hasattr(_execution_results): {hasattr(self, '_execution_results')}")
        logger.info(f"🔍 도구 '{self.name}' - result.data 존재: {result.data is not None}")
        if result.data:
            logger.info(f"🔍 도구 '{self.name}' - result.data 내용: {result.data}")
        
        if hasattr(self, '_execution_results') and result.data:
            self._execution_results[self.name] = result.data
            logger.info(f"📦 도구 '{self.name}' 실행 결과 저장됨: {len(str(result.data))} 문자")
        elif hasattr(self, '_execution_results'):
            logger.warning(f"⚠️ 도구 '{self.name}' - _execution_results 있지만 result.data가 없음")
        else:
            logger.warning(f"⚠️ 도구 '{self.name}' - _execution_results 속성이 없음")
        
        return result.message
    
    async def _arun(self, **kwargs) -> str:
        """LangChain required async method"""
        return self._run(**kwargs)
    
    def __init__(self, state: Optional[Dict[str, Any]] = None):
        """
        Initialize state-aware tool
        
        Args:
            state: LangGraph State dictionary containing agent context
        """
        # Generate default name and description for LangChain BaseTool
        tool_name = self.__class__.__name__.replace('Tool', '').lower()
        tool_description = f'{self.__class__.__name__} 도구'
        
        super().__init__(name=tool_name, description=tool_description)
        object.__setattr__(self, '_state', state or {})
            
        # Set args_schema for LangChain compatibility if get_schema exists
        if hasattr(self, 'get_schema'):
            object.__setattr__(self, 'args_schema', self.get_schema())
            
        # Set tool_name for compatibility with custom BaseTool methods
        object.__setattr__(self, 'tool_name', tool_name)
        
    def set_state(self, state: Dict[str, Any]) -> None:
        """
        Set the LangGraph State for this tool
        
        Args:
            state: LangGraph State dictionary
        """
        self._state = state
        
    def get_agent_context(self) -> Dict[str, Any]:
        """
        Extract agent context from LangGraph State
        
        Returns:
            Agent context dictionary
        """
        if not self._state:
            logger.warning("No LangGraph State available, returning empty context")
            return {}
            
        context = {
            "index_id": self._state.get("index_id"),
            "document_id": self._state.get("document_id"),
            "segment_id": self._state.get("segment_id"),
            "segment_index": self._state.get("segment_index"),
            "file_path": self._state.get("file_path"),
            "image_path": self._state.get("image_path"),
            "session_id": self._state.get("session_id"),
            "thread_id": self._state.get("thread_id"),
            "user_query": self._state.get("user_query", ""),
            "previous_analysis_context": self._state.get("previous_analysis_context", ""),
            "combined_analysis_context": self._state.get("combined_analysis_context", ""),
            "analysis_history": self._state.get("analysis_history", []),
            "skip_opensearch_query": self._state.get("skip_opensearch_query", False),
            "enable_opensearch": self._state.get("enable_opensearch", True),
            "segment_type": self._state.get("segment_type", ""),
            "start_timecode_smpte": self._state.get("start_timecode_smpte", ""),
            "end_timecode_smpte": self._state.get("end_timecode_smpte", "")
        }
        
        # Debug logging
        logger.info(f"🔍 StateAware tool context: "
                   f"document_id={context.get('document_id')}, segment_id={context.get('segment_id')}")
        
        return context
        
    def execute_with_state(self, state: Dict[str, Any], **kwargs) -> ToolResult:
        """
        Execute tool with LangGraph State context
        
        Args:
            state: LangGraph State dictionary
            **kwargs: Tool-specific arguments
            
        Returns:
            ToolResult
        """
        # Set state for this execution
        self.set_state(state)
        
        # Extract agent context and add to kwargs
        agent_context = self.get_agent_context()
        kwargs.update(agent_context)
        
        # Execute the tool with context
        return self.execute(**kwargs)
        
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool - must be implemented by subclasses
        
        Args:
            **kwargs: Tool arguments including agent context
            
        Returns:
            ToolResult
        """
        pass
    
    def _create_result(self, success: bool, message: str, data: Optional[Dict[str, Any]] = None, 
                      execution_time: Optional[float] = None) -> ToolResult:
        """통일된 결과 객체 생성 헬퍼 메서드"""
        return ToolResult(
            success=success,
            message=message,
            data=data or {},
            tool_name=self.tool_name,
            execution_time=execution_time
        )
    
    def _create_success_result(self, message: str, data: Dict[str, Any] = None, 
                              execution_time: Optional[float] = None) -> ToolResult:
        """성공 결과 생성"""
        return ToolResult(success=True, message=message, data=data, 
                         tool_name=self.tool_name, execution_time=execution_time)
    
    def _create_error_result(self, message: str, data: Dict[str, Any] = None,
                            execution_time: Optional[float] = None) -> ToolResult:
        """오류 결과 생성"""
        return ToolResult(success=False, message=message, data=data,
                         tool_name=self.tool_name, execution_time=execution_time)
    
    def _get_agent_context(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Agent 컨텍스트 추출 (호환성 메서드)"""
        return kwargs.get('_agent_context', {})
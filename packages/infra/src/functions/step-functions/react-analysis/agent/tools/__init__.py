"""
순수 도구들 패키지
LangGraph에서 사용할 수 있는 도구들을 정의
"""

from .base import BaseTool, ToolResult
from .state_aware_base import StateAwareBaseTool
from .image_analyzer import ImageAnalyzerTool
from .video_analyzer import VideoAnalyzerTool
from .registry import get_all_tools

# 백워드 호환성을 위해 유지 (나중에 제거 예정)
from .tool_registry import ToolRegistry

def get_tool_registry() -> ToolRegistry:
    """도구 레지스트리 인스턴스 반환 (Deprecated: registry.get_all_tools() 사용 권장)"""
    return ToolRegistry(enable_opensearch=True)

# 백워드 호환성
tool_registry = get_tool_registry()

__all__ = [
    'BaseTool', 
    'ToolResult', 
    'StateAwareBaseTool',
    'ImageAnalyzerTool',
    'VideoAnalyzerTool',
    'get_all_tools',
    # Deprecated
    'get_tool_registry',
    'tool_registry'
] 
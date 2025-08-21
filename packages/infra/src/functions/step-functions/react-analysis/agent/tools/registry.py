"""
Tool registration and management
Register and return tools for use in LangGraph
"""

import logging
from typing import List
from langchain_core.tools import BaseTool

from .image_analyzer import ImageAnalyzerTool
from .video_analyzer import VideoAnalyzerTool
# Import other tools later
# from .text_analyzer import TextAnalyzerTool

logger = logging.getLogger(__name__)


def get_all_tools() -> List[BaseTool]:
    """
    사용 가능한 모든 도구를 LangChain 형태로 반환
    
    Returns:
        List[BaseTool]: LangChain 호환 도구 리스트
    """
    tools = []
    logger.info("🔧 도구 등록 시작")
    
    try:
        # 이미지 분석 도구
        logger.info("📷 ImageAnalyzerTool 생성 중...")
        image_analyzer = ImageAnalyzerTool()
        logger.info(f"📷 ImageAnalyzerTool 생성 완료: {image_analyzer.__class__.__name__}")
        
        langchain_tool = _create_langchain_tool(image_analyzer)
        logger.info(f"🔗 LangChain 도구 래핑 완료: {langchain_tool.name}")
        
        tools.append(langchain_tool)
        
        # 동영상 분석 도구
        logger.info("🎬 VideoAnalyzerTool 생성 중...")
        video_analyzer = VideoAnalyzerTool()
        logger.info(f"🎬 VideoAnalyzerTool 생성 완료: {video_analyzer.__class__.__name__}")
        
        video_langchain_tool = _create_langchain_tool(video_analyzer)
        logger.info(f"🔗 LangChain 도구 래핑 완료: {video_langchain_tool.name}")
        
        tools.append(video_langchain_tool)
        
        # 추후 다른 도구들 추가
        # text_analyzer = TextAnalyzerTool()
        # tools.append(_create_langchain_tool(text_analyzer))
        
        logger.info(f"✅ 도구 등록 완료: {[tool.name for tool in tools]}")
        
    except Exception as e:
        logger.error(f"❌ 도구 등록 중 오류: {str(e)}")
        logger.error(f"❌ 오류 세부사항: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"❌ 스택 트레이스: {traceback.format_exc()}")
        # 오류가 있어도 사용 가능한 도구들은 반환
    
    return tools


def _create_langchain_tool(tool_instance) -> BaseTool:
    """
    도구 인스턴스를 LangChain 호환 도구로 변환
    
    Args:
        tool_instance: 도구 인스턴스
        
    Returns:
        BaseTool: LangChain 호환 도구
    """
    from langchain_core.tools import StructuredTool
    from agent.tools.state_aware_base import StateAwareBaseTool
    
    # StateAware 도구는 그대로 반환 (이미 LangChain BaseTool)
    if isinstance(tool_instance, StateAwareBaseTool):
        object.__setattr__(tool_instance, '_is_state_aware', True)
        return tool_instance
    
    # 일반 도구는 LangChain StructuredTool로 래핑
    def wrapper(**kwargs) -> str:
        """LangChain 도구 래퍼"""
        try:
            result = tool_instance.execute(**kwargs)
            return result.message
        except Exception as e:
            error_msg = f"도구 '{tool_instance.__class__.__name__}' 실행 실패: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    schema = tool_instance.get_schema()
    tool_name = tool_instance.__class__.__name__.replace('Tool', '').lower()
    
    langchain_tool = StructuredTool(
        name=tool_name,
        description=f'{tool_name} 도구',
        args_schema=schema,
        func=wrapper
    )
    
    return langchain_tool
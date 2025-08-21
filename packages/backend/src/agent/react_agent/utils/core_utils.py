"""
ReAct Agent core utility functions
"""
import asyncio
import logging
from typing import List, Callable, Any
from pathlib import Path
import os
from langchain_core.messages import BaseMessage, SystemMessage

logger = logging.getLogger(__name__)

# 타임아웃 및 재시도 설정 (환경변수에서 읽기)
DEFAULT_TIMEOUT = float(os.getenv("DEFAULT_TIMEOUT", "300.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "1.0"))


async def retry_with_backoff(
    func: Callable, 
    max_retries: int = MAX_RETRIES, 
    delay: float = RETRY_DELAY, 
    timeout: float = DEFAULT_TIMEOUT
) -> Any:
    """
    지수 백오프를 사용한 재시도 로직
    
    Args:
        func: 실행할 함수
        max_retries: 최대 재시도 횟수
        delay: 초기 지연 시간
        timeout: 타임아웃 시간
        
    Returns:
        함수 실행 결과
    """
    for attempt in range(max_retries + 1):
        try:
            # 타임아웃 적용
            result = await asyncio.wait_for(func(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Timeout occurred (attempt {attempt + 1}/{max_retries + 1})")
            if attempt == max_retries:
                raise Exception(f"Operation timed out after {max_retries + 1} attempts")
        except Exception as e:
            logger.warning(f"Error occurred (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
            if attempt == max_retries:
                raise e
            
            # 지수 백오프
            await asyncio.sleep(delay * (2 ** attempt))


def manage_conversation_history(messages: List[BaseMessage], max_messages: int = 10) -> List[BaseMessage]:
    """
    대화 이력 관리 함수 - 시스템 프롬프트를 제외한 순수 대화만 제한
    
    Args:
        messages: 전체 메시지 리스트
        max_messages: 유지할 최대 메시지 수
        
    Returns:
        관리된 메시지 리스트 (시스템 프롬프트 + 최근 대화)
    """
    if not messages:
        return []
    
    # 시스템 메시지와 일반 대화 분리
    system_messages = []
    conversation_messages = []
    
    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_messages.append(msg)
        else:
            conversation_messages.append(msg)
    
    # 순수 대화만 제한 (시스템 메시지는 제한하지 않음)
    if len(conversation_messages) > max_messages:
        # 최근 메시지만 유지
        conversation_messages = conversation_messages[-max_messages:]
        logger.info(f"대화 이력 관리: {len(conversation_messages)}개 메시지로 제한 (시스템 메시지 제외)")
    
    # 시스템 메시지를 맨 앞에, 대화를 그 뒤에 배치
    # 중요: 시스템 메시지는 하나만 유지 (최신 것)
    final_messages = []
    if system_messages:
        final_messages.append(system_messages[-1])  # 가장 최신 시스템 메시지만
    final_messages.extend(conversation_messages)
    
    return final_messages


def normalize_content(content: Any) -> str:
    """
    메시지 내용을 문자열로 정규화
    
    Args:
        content: 메시지 내용 (string, list, 또는 기타)
        
    Returns:
        정규화된 문자열 내용
    """
    if content is None:
        return ""
    
    if isinstance(content, list):
        return "".join(str(item) for item in content)
    
    return str(content)
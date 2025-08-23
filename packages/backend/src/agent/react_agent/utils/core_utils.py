"""
ReAct Agent core utility functions - Enhanced version
"""
import asyncio
import logging
import time
import json
import re
from typing import List, Callable, Any, Dict, Optional, Union, TypeVar
from pathlib import Path
from functools import wraps
from datetime import datetime
from langchain_core.messages import BaseMessage, SystemMessage

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ContentNormalizer:
    """Utility class for content normalization"""
    
    @staticmethod
    def normalize_content(content: Any) -> str:
        """
        Normalize various content types to string format - Enhanced version
        
        Args:
            content: Content to normalize (str, dict, list, etc.)
            
        Returns:
            Normalized string content
        """
        if content is None:
            return ""
        
        if isinstance(content, str):
            return content.strip()
        
        if isinstance(content, dict):
            # Handle different dictionary structures
            if "text" in content:
                return str(content["text"]).strip()
            elif "type" in content and content["type"] == "text" and "text" in content:
                return str(content["text"]).strip()
            else:
                return str(content).strip()
        
        if isinstance(content, list):
            # Extract text from list of content items
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and "text" in item:
                        text_parts.append(str(item["text"]))
                    elif "text" in item:
                        text_parts.append(str(item["text"]))
                elif isinstance(item, str):
                    text_parts.append(item)
                else:
                    text_parts.append(str(item))
            return " ".join(text_parts).strip()
        
        return str(content).strip()


class RetryHandler:
    """Enhanced retry handler with exponential backoff"""
    
    @staticmethod
    async def retry_with_backoff(
        func: Callable,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        timeout: Optional[float] = None,
        exceptions: tuple = (Exception,)
    ) -> Any:
        """
        Enhanced retry function with exponential backoff
        
        Args:
            func: Function to retry
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
            timeout: Total timeout in seconds
            exceptions: Exceptions to catch and retry on
            
        Returns:
            Result of the function call
            
        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        start_time = time.time()
        
        for attempt in range(max_retries + 1):
            try:
                # Check timeout
                if timeout and (time.time() - start_time) > timeout:
                    raise TimeoutError(f"Operation timed out after {timeout} seconds")
                
                # Apply timeout to individual call if specified
                if timeout:
                    remaining_time = timeout - (time.time() - start_time)
                    if remaining_time <= 0:
                        raise TimeoutError("No time remaining for retry")
                    
                    return await asyncio.wait_for(func(), remaining_time)
                else:
                    return await func()
                        
            except exceptions as e:
                last_exception = e
                
                if attempt == max_retries:
                    logger.error(f"All retry attempts failed. Last error: {str(e)}")
                    raise e
                
                # Calculate delay with exponential backoff
                delay = min(base_delay * (exponential_base ** attempt), max_delay)
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {delay:.2f}s")
                
                await asyncio.sleep(delay)
        
        if last_exception:
            raise last_exception


# Legacy support
retry_with_backoff = RetryHandler.retry_with_backoff


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


class ValidationUtils:
    """Utility class for validation operations"""
    
    @staticmethod
    def validate_thread_id(thread_id: str) -> bool:
        """
        Validate thread ID format
        
        Args:
            thread_id: Thread ID to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not thread_id or not isinstance(thread_id, str):
            return False
        
        # Basic validation: length and character set
        if len(thread_id) < 1 or len(thread_id) > 100:
            return False
        
        # Allow alphanumeric, hyphens, underscores
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', thread_id))
    
    @staticmethod
    def validate_message_content(content: Any) -> bool:
        """
        Validate message content
        
        Args:
            content: Content to validate
            
        Returns:
            True if valid, False otherwise
        """
        if content is None:
            return False
        
        # Normalize and check if non-empty
        normalized = ContentNormalizer.normalize_content(content)
        return bool(normalized.strip())


class PerformanceUtils:
    """Utility class for performance monitoring"""
    
    @staticmethod
    def measure_execution_time(func: Callable) -> Callable:
        """
        Decorator to measure function execution time
        
        Args:
            func: Function to measure
            
        Returns:
            Decorated function
        """
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.debug(f"{func.__name__} executed in {execution_time:.3f}s")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.debug(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.debug(f"{func.__name__} executed in {execution_time:.3f}s")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.debug(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


# Legacy support - maintain backward compatibility
normalize_content = ContentNormalizer.normalize_content
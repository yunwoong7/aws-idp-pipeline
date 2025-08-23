"""
Error handling utilities for ReAct Agent
"""
import logging
import time
from typing import Dict, Any, Optional, Callable, Type
from enum import Enum
from dataclasses import dataclass, field
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Error types for categorization and handling"""
    MCP_CONNECTION_FAILED = "mcp_connection_failed"
    MCP_TOOL_EXECUTION_FAILED = "mcp_tool_execution_failed"
    MODEL_TIMEOUT = "model_timeout"
    MODEL_RATE_LIMIT = "model_rate_limit"
    VALIDATION_ERROR = "validation_error"
    MEMORY_ERROR = "memory_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class AgentError:
    """Structured error information"""
    error_type: ErrorType
    message: str
    recoverable: bool
    retry_count: int = 0
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)
    original_exception: Optional[Exception] = None


class ErrorRecoveryStrategy:
    """Base class for error recovery strategies"""
    
    def can_handle(self, error: AgentError) -> bool:
        """Check if this strategy can handle the error"""
        raise NotImplementedError
    
    def recover(self, error: AgentError) -> Optional[AIMessage]:
        """Attempt to recover from the error"""
        raise NotImplementedError


class MCPConnectionErrorStrategy(ErrorRecoveryStrategy):
    """Recovery strategy for MCP connection errors"""
    
    def can_handle(self, error: AgentError) -> bool:
        return error.error_type == ErrorType.MCP_CONNECTION_FAILED
    
    def recover(self, error: AgentError) -> Optional[AIMessage]:
        logger.warning(f"MCP connection failed, attempting graceful degradation: {error.message}")
        return AIMessage(
            content="일시적으로 외부 도구에 접근할 수 없습니다. 기본 지식으로 답변드리겠습니다."
        )


class ModelTimeoutErrorStrategy(ErrorRecoveryStrategy):
    """Recovery strategy for model timeout errors"""
    
    def can_handle(self, error: AgentError) -> bool:
        return error.error_type == ErrorType.MODEL_TIMEOUT
    
    def recover(self, error: AgentError) -> Optional[AIMessage]:
        if error.retry_count < 2:
            logger.info(f"Model timeout, will retry (attempt {error.retry_count + 1})")
            return None  # Signal to retry
        else:
            logger.warning(f"Model timeout after {error.retry_count} retries")
            return AIMessage(
                content="처리 시간이 초과되었습니다. 더 간단한 요청으로 다시 시도해 주세요."
            )


class RateLimitErrorStrategy(ErrorRecoveryStrategy):
    """Recovery strategy for rate limit errors"""
    
    def can_handle(self, error: AgentError) -> bool:
        return error.error_type == ErrorType.MODEL_RATE_LIMIT
    
    def recover(self, error: AgentError) -> Optional[AIMessage]:
        logger.warning("Rate limit exceeded, requesting user to wait")
        return AIMessage(
            content="현재 많은 요청으로 인해 처리가 지연되고 있습니다. 잠시 후 다시 시도해 주세요."
        )


class ErrorHandler:
    """Central error handler for the ReAct Agent"""
    
    def __init__(self):
        self.strategies: list[ErrorRecoveryStrategy] = [
            MCPConnectionErrorStrategy(),
            ModelTimeoutErrorStrategy(),
            RateLimitErrorStrategy(),
        ]
        self.error_history: list[AgentError] = []
        self.max_error_history = 100
    
    def classify_error(self, exception: Exception, context: Dict[str, Any] = None) -> AgentError:
        """Classify an exception into an AgentError"""
        context = context or {}
        error_message = str(exception)
        
        # Classify by exception type and message content
        if "connection" in error_message.lower() or "mcp" in error_message.lower():
            if "tool" in error_message.lower():
                error_type = ErrorType.MCP_TOOL_EXECUTION_FAILED
            else:
                error_type = ErrorType.MCP_CONNECTION_FAILED
        elif "timeout" in error_message.lower():
            error_type = ErrorType.MODEL_TIMEOUT
        elif "rate limit" in error_message.lower() or "429" in error_message:
            error_type = ErrorType.MODEL_RATE_LIMIT
        elif isinstance(exception, (ValueError, TypeError)):
            error_type = ErrorType.VALIDATION_ERROR
        elif isinstance(exception, MemoryError):
            error_type = ErrorType.MEMORY_ERROR
        else:
            error_type = ErrorType.UNKNOWN_ERROR
        
        # Determine if error is recoverable
        recoverable = error_type in [
            ErrorType.MCP_CONNECTION_FAILED,
            ErrorType.MCP_TOOL_EXECUTION_FAILED,
            ErrorType.MODEL_TIMEOUT,
            ErrorType.MODEL_RATE_LIMIT,
        ]
        
        return AgentError(
            error_type=error_type,
            message=error_message,
            recoverable=recoverable,
            context=context,
            original_exception=exception
        )
    
    def handle_error(self, exception: Exception, context: Dict[str, Any] = None) -> AIMessage:
        """Handle an error and attempt recovery"""
        error = self.classify_error(exception, context)
        
        # Add to error history
        self._add_to_history(error)
        
        # Try recovery strategies
        for strategy in self.strategies:
            if strategy.can_handle(error):
                try:
                    recovery_result = strategy.recover(error)
                    if recovery_result is not None:
                        logger.info(f"Error recovered using {strategy.__class__.__name__}")
                        return recovery_result
                except Exception as recovery_exception:
                    logger.error(f"Recovery strategy failed: {recovery_exception}")
        
        # Default fallback
        logger.error(f"No recovery strategy found for error: {error.error_type}")
        return self._create_fallback_message(error)
    
    def _add_to_history(self, error: AgentError) -> None:
        """Add error to history with size limit"""
        self.error_history.append(error)
        if len(self.error_history) > self.max_error_history:
            self.error_history.pop(0)
    
    def _create_fallback_message(self, error: AgentError) -> AIMessage:
        """Create a fallback error message"""
        if error.error_type == ErrorType.VALIDATION_ERROR:
            content = "입력된 데이터에 문제가 있습니다. 다시 확인해 주세요."
        elif error.error_type == ErrorType.MEMORY_ERROR:
            content = "메모리 부족으로 요청을 처리할 수 없습니다. 더 작은 단위로 나누어 시도해 주세요."
        else:
            content = f"처리 중 오류가 발생했습니다. 나중에 다시 시도해 주세요. (오류 유형: {error.error_type.value})"
        
        return AIMessage(content=content)
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        if not self.error_history:
            return {"total_errors": 0, "error_types": {}}
        
        error_types = {}
        for error in self.error_history:
            error_type = error.error_type.value
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        recent_errors = [e for e in self.error_history if time.time() - e.timestamp < 3600]  # Last hour
        
        return {
            "total_errors": len(self.error_history),
            "recent_errors": len(recent_errors),
            "error_types": error_types,
            "most_common_error": max(error_types, key=error_types.get) if error_types else None
        }


# Decorator for automatic error handling
def handle_errors(error_handler: ErrorHandler):
    """Decorator to automatically handle errors in methods"""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = {"function": func.__name__, "args": str(args)[:100], "kwargs": str(kwargs)[:100]}
                return error_handler.handle_error(e, context)
        return wrapper
    return decorator


# Global error handler instance
global_error_handler = ErrorHandler()
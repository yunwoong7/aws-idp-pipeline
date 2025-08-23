"""
Structured logging configuration for ReAct Agent
"""
import logging
import sys
import json
import time
import os
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from .config import config_manager


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Create structured log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, "thread_id"):
            log_entry["thread_id"] = record.thread_id
        if hasattr(record, "execution_time"):
            log_entry["execution_time"] = record.execution_time
        if hasattr(record, "error_type"):
            log_entry["error_type"] = record.error_type
        if hasattr(record, "context"):
            log_entry["context"] = record.context
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)


class PerformanceLogger:
    """Logger for performance metrics"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(f"performance.{name}")
        self.start_time = None
    
    def start(self, context: Dict[str, Any] = None):
        """Start timing"""
        self.start_time = time.time()
        self.context = context or {}
    
    def end(self, message: str = "Operation completed", extra_context: Dict[str, Any] = None):
        """End timing and log performance"""
        if self.start_time is None:
            return
        
        execution_time = time.time() - self.start_time
        context = {**self.context, **(extra_context or {})}
        
        self.logger.info(
            message,
            extra={
                "execution_time": execution_time,
                "context": context
            }
        )
        self.start_time = None


class AgentLogger:
    """Specialized logger for agent operations"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.performance = PerformanceLogger(name)
    
    def log_conversation_start(self, thread_id: str, message_count: int):
        """Log conversation start"""
        self.logger.info(
            "Conversation started",
            extra={
                "thread_id": thread_id,
                "context": {"message_count": message_count}
            }
        )
    
    def log_tool_execution(self, tool_name: str, thread_id: str, execution_time: float, success: bool):
        """Log tool execution"""
        level = logging.INFO if success else logging.WARNING
        self.logger.log(
            level,
            f"Tool execution {'succeeded' if success else 'failed'}: {tool_name}",
            extra={
                "thread_id": thread_id,
                "execution_time": execution_time,
                "context": {"tool_name": tool_name, "success": success}
            }
        )
    
    def log_model_call(self, thread_id: str, token_count: int, execution_time: float):
        """Log model API call"""
        self.logger.info(
            "Model call completed",
            extra={
                "thread_id": thread_id,
                "execution_time": execution_time,
                "context": {"token_count": token_count}
            }
        )
    
    def log_error(self, error: Exception, thread_id: str = None, context: Dict[str, Any] = None):
        """Log error with context"""
        self.logger.error(
            f"Error occurred: {str(error)}",
            extra={
                "thread_id": thread_id,
                "error_type": type(error).__name__,
                "context": context or {},
            },
            exc_info=True
        )
    
    def log_memory_usage(self, thread_count: int, total_messages: int, memory_percent: float):
        """Log memory usage statistics"""
        self.logger.info(
            "Memory usage update",
            extra={
                "context": {
                    "thread_count": thread_count,
                    "total_messages": total_messages,
                    "memory_percent": memory_percent
                }
            }
        )


class DevelopmentLogFilter(logging.Filter):
    """Filter to reduce log noise in development"""
    
    SUPPRESS_PATTERNS = [
        # Suppress noisy patterns
        "replace_tool_references",
        "_route_model_output: message",
        "_route_model_output: messages count",
        "Model ID not specified",
        "Configuration issue",
        "Configuration validation failed",
        "Found credentials in shared credentials file",
        "Processing request of type",
        "Client does not support MCP Roots",
        "Will watch for changes",
        "Started reloader process",
        "Started server process",
        "Waiting for application startup",
        "Application startup complete",
        "Using path resolver",
        "PHOENIX_API_KEY",
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        
        # Suppress patterns that are too noisy
        for pattern in self.SUPPRESS_PATTERNS:
            if pattern in message:
                return False
        
        # Suppress debug-level tool execution details
        if record.levelno == logging.DEBUG and any(x in message.lower() for x in ["tool_", "_call_", "graph_builder"]):
            return False
        
        # Suppress repetitive configuration messages
        if "configuration" in message.lower() and record.levelno <= logging.INFO:
            return False
            
        return True


class ColoredFormatter(logging.Formatter):
    """Colored formatter for better console readability"""
    
    # Color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m',     # Reset
    }
    
    def format(self, record: logging.LogRecord) -> str:
        # Get level color
        level_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # Shorten logger name
        logger_name = record.name
        if logger_name.startswith('src.'):
            logger_name = logger_name[4:]  # Remove 'src.' prefix
        if len(logger_name) > 25:
            logger_name = '...' + logger_name[-22:]
        
        # Format message
        message = record.getMessage()
        
        # Add context if available
        context_info = ""
        if hasattr(record, "thread_id"):
            context_info += f" [{record.thread_id}]"
        if hasattr(record, "execution_time"):
            context_info += f" ({record.execution_time:.3f}s)"
        
        # Create formatted message
        formatted = f"{level_color}{timestamp}{reset} {level_color}{record.levelname:<7}{reset} {logger_name:<25} {message}{context_info}"
        
        # Add exception if present
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        
        return formatted


def setup_logging() -> None:
    """Setup improved logging for the agent"""
    config = config_manager.config
    
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level.value))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler with colored format for development
    console_handler = logging.StreamHandler(sys.stdout)
    if config.debug_mode or os.getenv('ENVIRONMENT', 'local') == 'local':
        # Use colored format for better readability in development
        console_handler.setFormatter(ColoredFormatter())
    else:
        # Use structured format in production
        console_handler.setFormatter(StructuredFormatter())
    
    # Filter out noisy logs in development
    if config.debug_mode or os.getenv('ENVIRONMENT', 'local') == 'local':
        console_handler.addFilter(DevelopmentLogFilter())
    
    root_logger.addHandler(console_handler)
    
    # File handler for all logs
    file_handler = logging.FileHandler(log_dir / "agent.log")
    file_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(file_handler)
    
    # Separate file handler for errors
    error_handler = logging.FileHandler(log_dir / "errors.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(error_handler)
    
    # Performance log handler
    performance_logger = logging.getLogger("performance")
    performance_handler = logging.FileHandler(log_dir / "performance.log")
    performance_handler.setFormatter(StructuredFormatter())
    performance_logger.addHandler(performance_handler)
    performance_logger.propagate = False  # Don't propagate to root logger
    
    # Set specific logger levels to reduce noise
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    # Agent specific loggers - reduce verbosity
    logging.getLogger("src.agent.react_agent.state.model").setLevel(logging.WARNING)
    logging.getLogger("src.agent.react_agent.graph_builder").setLevel(logging.WARNING)
    
    if config.debug_mode or os.getenv('ENVIRONMENT', 'local') == 'local':
        logging.info("🚀 Development logging initialized with colors")
    else:
        logging.info("Structured logging initialized")


def get_agent_logger(name: str) -> AgentLogger:
    """Get a specialized agent logger"""
    return AgentLogger(name)


# Initialize logging on import
setup_logging()
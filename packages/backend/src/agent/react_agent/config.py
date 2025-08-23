"""
Configuration management for ReAct Agent
"""
import os
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from enum import Enum

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings

logger = logging.getLogger(__name__)


class LogLevel(str, Enum):
    """Log level options"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AgentConfig(BaseSettings):
    """Central configuration for ReAct Agent"""
    
    # Model Configuration
    model_id: str = Field(default="", description="Model ID to use for the agent")
    max_tokens: int = Field(default=4096, ge=100, le=32000, description="Maximum tokens for model responses")
    model_timeout: float = Field(default=60.0, ge=5.0, le=300.0, description="Model call timeout in seconds")
    max_retries: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts for model calls")
    
    # Memory Management
    summarization_threshold: int = Field(default=12, ge=6, le=50, description="Message count threshold for summarization")
    max_conversation_messages: int = Field(default=10, ge=4, le=100, description="Maximum messages in conversation history")
    max_threads: int = Field(default=100, ge=10, le=1000, description="Maximum number of threads to keep in memory")
    max_messages_per_thread: int = Field(default=50, ge=10, le=200, description="Maximum messages per thread")
    
    # MCP Configuration
    mcp_json_path: str = Field(default="", description="Path to MCP configuration JSON file")
    mcp_connection_timeout: float = Field(default=30.0, ge=5.0, le=120.0, description="MCP connection timeout")
    mcp_retry_attempts: int = Field(default=3, ge=1, le=5, description="MCP connection retry attempts")
    
    # Performance & Monitoring
    debug_mode: bool = Field(default=False, description="Enable debug mode")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    enable_metrics: bool = Field(default=True, description="Enable performance metrics collection")
    metrics_retention_hours: int = Field(default=24, ge=1, le=168, description="Hours to retain metrics")
    
    # Security & Limits
    max_attachment_size_mb: int = Field(default=50, ge=1, le=500, description="Maximum attachment size in MB")
    max_attachments_per_request: int = Field(default=10, ge=1, le=50, description="Maximum attachments per request")
    enable_content_filtering: bool = Field(default=True, description="Enable content filtering")
    
    # Cache Configuration
    prompt_cache_size: int = Field(default=100, ge=10, le=1000, description="Prompt cache size")
    prompt_cache_ttl: int = Field(default=3600, ge=300, le=86400, description="Prompt cache TTL in seconds")
    
    # Health Check Configuration
    health_check_interval: int = Field(default=60, ge=10, le=300, description="Health check interval in seconds")
    health_check_timeout: float = Field(default=10.0, ge=1.0, le=60.0, description="Health check timeout")
    
    model_config = {
        "env_prefix": "AGENT_",
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore"  # Ignore extra environment variables
    }
    
    @field_validator('model_id')
    @classmethod
    def validate_model_id(cls, v):
        if not v:
            logger.warning("Model ID not specified, using default")
        return v
    
    @field_validator('mcp_json_path')
    @classmethod
    def validate_mcp_path(cls, v):
        if v and not os.path.exists(v):
            logger.warning(f"MCP configuration file not found: {v}")
        return v
    
    @field_validator('max_attachment_size_mb')
    @classmethod
    def validate_attachment_size(cls, v):
        if v > 100:
            logger.warning(f"Large attachment size limit: {v}MB - consider reducing for better performance")
        return v
    
    def get_memory_limits(self) -> Dict[str, int]:
        """Get memory-related configuration"""
        return {
            "max_threads": self.max_threads,
            "max_messages_per_thread": self.max_messages_per_thread,
            "max_conversation_messages": self.max_conversation_messages,
            "summarization_threshold": self.summarization_threshold
        }
    
    def get_model_config(self) -> Dict[str, Any]:
        """Get model-related configuration"""
        return {
            "model_id": self.model_id,
            "max_tokens": self.max_tokens,
            "timeout": self.model_timeout,
            "max_retries": self.max_retries
        }
    
    def get_mcp_config(self) -> Dict[str, Any]:
        """Get MCP-related configuration"""
        return {
            "json_path": self.mcp_json_path,
            "connection_timeout": self.mcp_connection_timeout,
            "retry_attempts": self.mcp_retry_attempts
        }
    
    def update_from_dict(self, config_dict: Dict[str, Any]) -> None:
        """Update configuration from dictionary"""
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.info(f"Configuration updated: {key} = {value}")
            else:
                logger.warning(f"Unknown configuration key: {key}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return self.dict()
    
    def validate_configuration(self) -> bool:
        """Validate the current configuration"""
        issues = []
        
        # Check critical settings
        if not self.model_id:
            issues.append("Model ID is required")
        
        if self.mcp_json_path and not os.path.exists(self.mcp_json_path):
            issues.append(f"MCP configuration file not found: {self.mcp_json_path}")
        
        # Check memory settings
        if self.max_messages_per_thread > self.max_conversation_messages * 5:
            issues.append("max_messages_per_thread is too high compared to max_conversation_messages")
        
        # Check timeout settings
        if self.model_timeout < 10.0:
            issues.append("Model timeout is very low, may cause frequent timeouts")
        
        if issues:
            # Only log issues in debug mode to reduce noise
            if os.getenv('DEBUG_MODE', 'false').lower() == 'true':
                for issue in issues:
                    logger.debug(f"Configuration issue: {issue}")
            return False
        
        # Only log success in debug mode
        if os.getenv('DEBUG_MODE', 'false').lower() == 'true':
            logger.debug("Configuration validation passed")
        return True


class ConfigManager:
    """Configuration manager with hot-reload support"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self._config = AgentConfig()
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from file and environment"""
        try:
            # Load from environment variables
            self._config = AgentConfig()
            
            # If config file specified, load additional settings
            if self.config_file and os.path.exists(self.config_file):
                import json
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                self._config.update_from_dict(config_data)
            
            # Validate configuration
            if not self._config.validate_configuration():
                logger.warning("Configuration validation failed, using defaults")
                
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            self._config = AgentConfig()  # Fallback to defaults
    
    @property
    def config(self) -> AgentConfig:
        """Get current configuration"""
        return self._config
    
    def reload(self) -> bool:
        """Reload configuration from sources"""
        try:
            old_config = self._config.to_dict()
            self._load_config()
            new_config = self._config.to_dict()
            
            # Log changes only in debug mode
            for key, new_value in new_config.items():
                old_value = old_config.get(key)
                if old_value != new_value and os.getenv('DEBUG_MODE', 'false').lower() == 'true':
                    logger.debug(f"Configuration changed: {key} = {old_value} -> {new_value}")
            
            return True
        except Exception as e:
            logger.error(f"Error reloading configuration: {e}")
            return False
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """Update configuration with new values"""
        try:
            self._config.update_from_dict(updates)
            return True
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
            return False
    
    def save_config(self) -> bool:
        """Save current configuration to file"""
        if not self.config_file:
            logger.warning("No config file specified, cannot save")
            return False
        
        try:
            import json
            with open(self.config_file, 'w') as f:
                json.dump(self._config.to_dict(), f, indent=2, default=str)
            logger.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False


# Global configuration manager
config_manager = ConfigManager()
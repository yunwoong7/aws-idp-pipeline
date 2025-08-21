"""
Lambda environment Base Tool class
Optimized for Lambda environment based on backend tools/base.py
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel
from dataclasses import dataclass, asdict
import json

@dataclass
class ToolResult:
    """Tool execution result"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None
    execution_time: Optional[float] = None
    
    def dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    def json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.dict(), ensure_ascii=False, indent=2)

class BaseTool(ABC):
    """Lambda environment Base Tool class"""
    
    # Agent context support
    supports_agent_context: bool = False
    
    def __init__(self):
        """Basic initialization"""
        self.tool_name = self.__class__.__name__
    
    @abstractmethod
    def get_schema(self) -> type:
        """Return tool input schema"""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute tool"""
        pass
    
    def _get_agent_context(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Agent context"""
        return kwargs.get('_agent_context', {})
    
    def _create_result(self, success: bool, message: str, data: Optional[Dict[str, Any]] = None, 
                      execution_time: Optional[float] = None) -> ToolResult:
        """Create unified result object helper method"""
        return ToolResult(
            success=success,
            message=message,
            data=data or {},
            tool_name=self.tool_name,
            execution_time=execution_time
        )
    
    def _create_success_result(self, message: str, data: Dict[str, Any] = None, 
                              execution_time: Optional[float] = None) -> ToolResult:
        """Create success result"""
        return ToolResult(success=True, message=message, data=data, 
                         tool_name=self.tool_name, execution_time=execution_time)
    
    def _create_error_result(self, message: str, data: Dict[str, Any] = None,
                            execution_time: Optional[float] = None) -> ToolResult:
        """Create error result"""
        return ToolResult(success=False, message=message, data=data,
                         tool_name=self.tool_name, execution_time=execution_time) 
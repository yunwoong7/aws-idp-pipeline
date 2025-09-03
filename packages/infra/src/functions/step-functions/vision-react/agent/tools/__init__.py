"""
Tool registry for Vision Plan Execute agent - ref_chat_agent style
"""

import logging
from typing import Dict, Any, List, Optional, Type
from .base import BaseTool
from .image_analyzer import ImageAnalyzerTool
from .video_analyzer import VideoAnalyzerTool
from .image_rotator import ImageRotateTool

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Tool registry - manages all available tools"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
    
    def register_tool(self, name: str, tool: BaseTool):
        """Register a tool"""
        self.tools[name] = tool
        return self
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self.tools.get(name)
    
    def execute_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """Execute tool by name"""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        return tool.execute(**kwargs)
    
    def list_tools(self) -> List[str]:
        """Return all available tool names"""
        return list(self.tools.keys())
    
    def get_all_tool_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Return schemas for all tools"""
        return {name: tool.get_schema() for name, tool in self.tools.items()}
    
    def get_all_tools(self) -> List[BaseTool]:
        """Return all tool instances"""
        return list(self.tools.values())

# Singleton instance
registry = ToolRegistry()

# Register available tools
registry.register_tool("ImageAnalyzer", ImageAnalyzerTool())
registry.register_tool("VideoAnalyzer", VideoAnalyzerTool())
registry.register_tool("ImageRotate", ImageRotateTool())

# Legacy functions for backward compatibility
def get_tool_by_name(tool_name: str) -> Optional[BaseTool]:
    """Get tool instance by name"""
    return registry.get_tool(tool_name)

def get_all_tools() -> List[BaseTool]:
    """Get all available tool instances"""
    return registry.get_all_tools()

# Exports
__all__ = ['BaseTool', 'ToolRegistry', 'registry', 'get_tool_by_name', 'get_all_tools']
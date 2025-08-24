# src/agent/tools/__init__.py
from typing import Dict, Any, List, Optional, Type
from src.chat_agent.tools.base import BaseTool

class ToolRegistry:
    """도구 레지스트리 - 모든 사용 가능한 도구를 관리"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
    
    def register_tool(self, name: str, tool: BaseTool):
        """도구 등록"""
        self.tools[name] = tool
        return self
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """이름으로 도구 반환"""
        return self.tools.get(name)
    
    def execute_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """이름으로 도구 실행"""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        return tool.execute(**kwargs)
    
    def list_tools(self) -> List[str]:
        """사용 가능한 모든 도구 이름 반환"""
        return list(self.tools.keys())
    
    def get_all_tool_schemas(self) -> Dict[str, Dict[str, Any]]:
        """모든 도구의 스키마 반환"""
        return {name: tool.get_schema() for name, tool in self.tools.items()}
    
    def get_all_langchain_tools(self) -> List:
        """모든 LangChain 도구 반환"""
        from langchain_core.tools import StructuredTool
        
        langchain_tools = []
        for name, tool in self.tools.items():
            langchain_tools.append(
                StructuredTool.from_function(
                    func=tool.execute,
                    name=name,
                    description=tool.__doc__ or "",
                    args_schema=tool.get_schema(),
                    return_direct=True
                )
            )
        return langchain_tools

# 싱글톤 인스턴스 생성
registry = ToolRegistry()

# 내보내기
__all__ = ['BaseTool', 'ToolRegistry', 'registry']
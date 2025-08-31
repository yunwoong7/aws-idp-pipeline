"""
Base tool class and interfaces - ref_chat_agent style
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, TypedDict

logger = logging.getLogger(__name__)

class Reference(TypedDict, total=False):
    """Reference information structure"""
    id: str  # Unique ID for the reference
    type: str  # Reference type (url, image, file, etc.)
    value: str  # Reference value (URL, path, etc.)
    title: Optional[str]  # Reference title (optional)
    description: Optional[str]  # Reference description (optional)

class ToolResult(TypedDict):
    """Standard format for tool execution results"""
    success: bool  # Whether the execution was successful
    count: int  # Number of result items
    results: List[Dict[str, Any]]  # List of result items
    references: List[Reference]  # List of reference information
    llm_text: str  # LLM-friendly text
    error: Optional[str]  # Error message (if an error occurred)

class BaseTool(ABC):
    """Base class for all tools"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Tool execution logic"""
        pass
    
    @abstractmethod
    def get_schema(self) -> type:
        """Return the input schema for the tool"""
        pass
    
    def create_reference(self, 
                        ref_type: str,
                        value: str, 
                        title: Optional[str] = None,
                        description: Optional[str] = None) -> Reference:
        """
        Helper method to create reference information
        
        Args:
            ref_type: Reference type (url, image, file, etc.)
            value: Reference value (URL, path, etc.)
            title: Reference title (optional)
            description: Reference description (optional)
            
        Returns:
            Reference: The created reference information
        """
        return {
            "id": self._generate_id(value),
            "type": ref_type,
            "value": value,
            "title": title,
            "description": description,
        }
    
    def _generate_id(self, value: str) -> str:
        """Generate a unique ID (simple method)"""
        import hashlib
        return hashlib.md5(value.encode()).hexdigest()[:8]
    
    def _create_error_response(self, error_message: str) -> ToolResult:
        """
        Create a standardized error response
        
        Args:
            error_message: The error message
            
        Returns:
            ToolResult: Error response in the standard format
        """
        return {
            "success": False,
            "count": 0,
            "results": [],
            "references": [],
            "llm_text": f"Error: {error_message}",
            "error": error_message
        }
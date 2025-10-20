"""
Base classes for tools in the search agent
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, TypedDict
import hashlib


class Reference(TypedDict, total=False):
    """Reference information structure"""
    id: str  # Unique ID for the reference
    type: str  # Reference type (url, image, file, document, etc.)
    value: str  # Reference value (URL, path, etc.)
    title: Optional[str]  # Reference title (optional)
    description: Optional[str]  # Reference description (optional)
    # Additional fields for document references
    document_id: Optional[str]
    file_name: Optional[str]
    segment_index: Optional[int]
    page_index: Optional[int]
    score: Optional[float]


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
    async def execute(self, **kwargs) -> ToolResult:
        """
        Tool execution logic

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            ToolResult: Standardized result format
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """
        Return the name of the tool

        Returns:
            str: Tool name
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        Return the description of the tool

        Returns:
            str: Tool description
        """
        pass

    def create_reference(
        self,
        ref_type: str,
        value: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        **kwargs
    ) -> Reference:
        """
        Helper method to create reference information

        Args:
            ref_type: Reference type (url, image, file, document, etc.)
            value: Reference value (URL, path, etc.)
            title: Reference title (optional)
            description: Reference description (optional)
            **kwargs: Additional reference fields

        Returns:
            Reference: The created reference information
        """
        ref: Reference = {
            "id": self._generate_id(value),
            "type": ref_type,
            "value": value,
            "title": title,
            "description": description,
        }

        # Add any additional fields
        for key, val in kwargs.items():
            if val is not None:
                ref[key] = val  # type: ignore

        return ref

    def _generate_id(self, value: str) -> str:
        """
        Generate a unique ID for a reference

        Args:
            value: Value to generate ID from

        Returns:
            str: Generated ID (8-character hash)
        """
        return hashlib.md5(value.encode()).hexdigest()[:8]

    def create_error_result(self, error_message: str) -> ToolResult:
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

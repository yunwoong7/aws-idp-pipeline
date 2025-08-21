"""
Basic utility tools for MCP server - Refactored with API-First approach
"""
from typing import Dict, Any
from datetime import datetime
from .response_formatter import format_api_response


async def add(a: int = None, b: int = None):
    """
    Add two numbers for testing purposes.
    
    Args:
        a: First number
        b: Second number
        
    Returns:
        Formatted response with calculation result
    """
    
    if a is None or b is None:
        return {
            "success": False,
            "error": "Both a and b parameters are required",
            "data": None
        }
    
    print(f"🔢 Adding {a} and {b}")
    
    # Calculate the result
    result = a + b
    
    # Create API response format
    api_response = {
        "success": True,
        "result": result,
        "operation": "addition",
        "operands": {"a": a, "b": b},
        "timestamp": datetime.now().isoformat()
    }
    
    # Use response formatter to create standardized response
    return format_api_response(api_response, 'add')


async def echo(message: str = None):
    """
    Echo a message for testing purposes.
    
    Args:
        message: Message to echo
        
    Returns:
        Formatted response with echoed message
    """
    
    if not message:
        return {
            "success": False,
            "error": "message parameter is required",
            "data": None
        }
    
    print(f"🔊 Echoing message: {message}")
    
    # Create API response format
    api_response = {
        "success": True,
        "message": f"Echo: {message}",
        "original_message": message,
        "timestamp": datetime.now().isoformat()
    }
    
    # Use response formatter to create standardized response
    return format_api_response(api_response, 'echo')
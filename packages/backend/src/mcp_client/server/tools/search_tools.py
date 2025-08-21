"""
Search tools for MCP server - Refactored with API-First approach
"""
import requests
import uuid
from typing import Dict, Any
from config import get_app_config
from .response_formatter import format_api_response

# Get configuration
conf = get_app_config()
API_BASE_URL = conf['api_base_url']


async def hybrid_search_api(query: str, size: int = 10, session_id: str = None) -> Dict[str, Any]:
    """
    hybrid search API call
    """
    try:
        url = f"{API_BASE_URL}/api/opensearch/search/hybrid"
        
        payload = {
            "query": query,
            "size": size 
        }
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            # Return original API response (add session ID metadata)
            api_response = response.json()
            if session_id:
                api_response['_session_id'] = session_id
            return api_response
        else:
            return {
                'success': False,
                'error': f'Search failed: HTTP {response.status_code}',
                'data': None
            }
    
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'error': 'API call timeout (30 seconds)',
            'data': None
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Error occurred during search: {str(e)}',
            'data': None
        }


# ============================================================================
# MCP Tool Functions
# ============================================================================

async def hybrid_search(query: str, size: int = 3, session_id: str = None):
    """
    Perform hybrid search using semantic and keyword search to find relevant documents.
    This search combines vector similarity with keyword matching for better results.
    
    Args:
        query: Search query string
        size: Number of results to return (optional, default 3)
        session_id: Session ID for reference deduplication (optional, auto-generated if not provided)
    
    Returns:
        Formatted response with API data, references, and LLM guide
    """
    
    # Generate session_id if not provided for reference deduplication
    if not session_id:
        session_id = str(uuid.uuid4())
        print(f"🆔 [search_tools] Auto-generated session_id: {session_id}")
    
    print(f"� Performing hybrid search: query={query}, session_id={session_id}")

    # API call
    api_response = await hybrid_search_api(query, size, session_id)
    
    # Use response formatter to create standardized response
    return format_api_response(api_response, 'hybrid_search', session_id)
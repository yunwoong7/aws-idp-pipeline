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


async def hybrid_search_api(index_id: str, query: str, session_id: str = None) -> Dict[str, Any]:
    """
    hybrid search API call
    """
    try:
        url = f"{API_BASE_URL}/api/opensearch/search/hybrid"
        
        payload = {
            "index_id": index_id,
            "query": query,
            "size": 3 
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

async def hybrid_search(index_id: str, query: str, session_id: str = None):
    """
    Perform hybrid search using semantic and keyword search to find relevant documents.
    This search combines vector similarity with keyword matching for better results.
    
    Args:
        index_id: Index ID for access control (Have to be provided)
        query: Search query string
        session_id: Session ID for reference deduplication (optional, auto-generated if not provided)
    
    Returns:
        Formatted response with API data, references, and LLM guide
    """
    
    # Generate session_id if not provided for reference deduplication
    if not index_id:
        return {
            'success': False,
            'error': 'Index ID is required',
            'data': None
        }
    
    if not session_id:
        session_id = str(uuid.uuid4())
        print(f"🆔 [search_tools] Auto-generated session_id: {session_id}")
    
    print(f"� Performing hybrid search: query={query}, session_id={session_id}")

    # API call
    api_response = await hybrid_search_api(index_id, query, session_id)
    
    # Use response formatter to create standardized response
    return format_api_response(api_response, 'hybrid_search', session_id)
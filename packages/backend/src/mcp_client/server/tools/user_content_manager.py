"""
User Content Management Tools for MCP server
"""
import requests
from typing import Dict, Any
from config import get_app_config
from .response_formatter import format_api_response

# Get configuration
conf = get_app_config()
API_BASE_URL = conf['api_base_url']

async def add_user_content_to_page_api(
    project_id: str,
    document_id: str,
    page_index: int,
    content: str
) -> Dict[str, Any]:
    """
    Call user content addition API
    """
    try:
        endpoint = f"{API_BASE_URL.rstrip('/')}/api/opensearch/user-content/add"
        
        payload = {
            "project_id": project_id,
            "document_id": document_id,
            "page_index": page_index,
            "content": content
        }
        
        # Asynchronous processing: send request and return immediately
        import threading
        
        def async_api_call():
            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=120  # Set longer timeout
                )
                response.raise_for_status()
                print(f"✅ User content addition completed: {project_id}/{document_id}[{page_index}]")
            except Exception as e:
                print(f"❌ Background processing failed: {str(e)}")
        
        # Run in background
        thread = threading.Thread(target=async_api_call)
        thread.daemon = True
        thread.start()
        
        # Return immediately
        return {
            "success": True,
            "data": {
                "project_id": project_id,
                "document_id": document_id,
                "page_index": page_index,
                "content_length": len(content),
                "status": "processing",
                "message": "The user content addition request has been received. It is being processed in the background. Please check again later."
            }
        }
        
    except requests.exceptions.RequestException as e:
        print(f"📝 User content addition API call failed: {str(e)}")
        return {
            "success": False,
            "error": f"API call failed: {str(e)}",
            "data": None
        }
    except Exception as e:
        print(f"📝 Error occurred during user content addition API call: {str(e)}")
        return {
            "success": False,
            "error": f"Error occurred during API call: {str(e)}",
            "data": None
        }


async def remove_user_content_from_page_api(
    project_id: str,
    document_id: str,
    page_index: int,
    content_index: int
) -> Dict[str, Any]:
    """
    Call user content deletion API
    """
    try:
        endpoint = f"{API_BASE_URL.rstrip('/')}/api/opensearch/user-content/remove"
        
        payload = {
            "project_id": project_id,
            "document_id": document_id,
            "page_index": page_index,
            "content_index": content_index
        }
                
        response = requests.post(
            endpoint,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        response.raise_for_status()
        
        # Return original API response
        return response.json()
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": f"API call failed: {str(e)}",
            "data": None
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error occurred during API call: {str(e)}",
            "data": None
        }


# ============================================================================
# MCP Tool Functions
# ============================================================================

async def add_user_content_to_page(
    project_id: str = None,
    document_id: str = None,
    page_index: int = None,
    content: str = None
):
    """
    Update user content to the document.
    Determine the target page based on the current conversation content.
    You must pass the project_id, document_id, and page_index of the target page.
    If you do not have this information, ask the user which document it is.
    However, if you know the information, use it to proceed.
    If hybrid_search result is available, use it to proceed.
    
    Args:
        project_id: project id  
        document_id: document id
        page_index: page index
        content: user content
        
    Returns:
        Formatted response with API data, references, and LLM guide
    """
    
    if not all([project_id, document_id, page_index is not None, content]):
        return {
            "success": False,
            "error": "All parameters are required: project_id, document_id, page_index, content",
            "data": None
        }
        
    # API call
    api_response = await add_user_content_to_page_api(
        project_id, document_id, page_index, content
    )
    
    # Use response formatter to create standardized response
    return format_api_response(api_response, 'add_user_content_to_page')


async def remove_user_content_from_page(
    project_id: str = None,
    document_id: str = None,
    page_index: int = None,
    content_index: int = None
):
    """
    Remove user content from a specific page and update embeddings.
    
    Args:
        project_id: Project ID
        document_id: Document ID
        page_index: Page index
        content_index: Index of user content to delete
        
    Returns:
        Formatted response with API data, references, and LLM guide
    """
    
    if not all([project_id, document_id, page_index is not None, content_index is not None]):
        return {
            "success": False,
            "error": "All parameters are required: project_id, document_id, page_index, content_index",
            "data": None
        }
    
    print(f"📝 Removing user content from page: {project_id}/{document_id}[{page_index}], index: {content_index}")
    
    # API call
    api_response = await remove_user_content_from_page_api(project_id, document_id, page_index, content_index)
    
    # Use response formatter to create standardized response
    return format_api_response(api_response, 'remove_user_content_from_page')
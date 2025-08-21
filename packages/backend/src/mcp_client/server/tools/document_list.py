"""
Document list tools for MCP server - Refactored with API-First approach
"""
import requests
from typing import Dict, Any
from config import get_app_config
from .response_formatter import format_api_response

# Get configuration
conf = get_app_config()
API_BASE_URL = conf['api_base_url']


async def get_documents_list_api() -> Dict[str, Any]:
    """
    Call document list API - pure API call and return original response
    """
    try:
        docs_url = f"{API_BASE_URL.rstrip('/')}/api/documents?simple=true"
        
        print(f"📋 문서 목록 API 호출: {docs_url}")
        
        response = requests.get(docs_url, timeout=10)
        response.raise_for_status()
        
        # Return original API response as much as possible
        return response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"📋 Error in document list API call: {str(e)}")
        return {
            "success": False,
            "error": f"Error in document list API call: {str(e)}",
            "data": None
        }
    except Exception as e:
        print(f"📋 Error in document list API call: {str(e)}")
        return {
            "success": False,
            "error": f"Error in document list API call: {str(e)}",
            "data": None
        }


# ============================================================================
# MCP Tool Functions
# ============================================================================

async def get_documents_list():
    """
    Get a list of all documents in the specified project.
    Useful to see all available documents before starting analysis.
    This tool only provides a signal to open the document panel in the UI.

    Args:
        project_id: Project ID to get documents from (Ex. 123e4567-e89b-12d3-a456-426614174000)
    
    Returns:
        Simple response with show_document_panel signal and guidance
    """
    print(f"📄 Providing document list signal")
    
    # Create simple response with only signal and guidance
    return {
        "success": True,
        "data": {
            "message": "Document panel signal sent"
        },
        "error": None,
        "references": [
            {
                'type': 'show_document_panel',
                'title': 'Document List Panel',
                'display_name': 'Open Document List Panel',
                'value': 'show_document_panel',
                'metadata': {
                    'action': 'open_document_panel',
                    'description': 'Signal to open the document list panel in the UI'
                }
            }
        ],
        "llm_guide": "문서 조회가 완료되었습니다. 화면에서 문서 목록을 확인하세요. 특정 문서나 상세한 분석이 필요하면 이야기해 주세요."
    }
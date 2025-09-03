"""
Document analysis tools for MCP server - Refactored with API-First approach
"""
import requests  # type: ignore
import asyncio
from typing import Dict, Any, Optional
import base64
try:
    # Try absolute import first (for main app)
    from src.mcp_client.server.config import get_app_config
except ImportError:
    # Fallback to relative import (for MCP server)
    from config import get_app_config
from .response_formatter import format_api_response

# Get configuration dynamically
def get_api_base_url():
    """Get API base URL dynamically to ensure latest config"""
    conf = get_app_config()
    api_url = conf['api_base_url']
    
    # 디버깅을 위해 파일에 로그 기록
    try:
        with open('/tmp/mcp_debug.log', 'a') as f:
            f.write(f"[{__name__}] API URL: {api_url}\n")
    except:
        pass
    
    return api_url


def _sync_http_request(url: str, params: dict = None, timeout: int = 30) -> requests.Response:
    """Separate synchronous HTTP request function"""
    return requests.get(url, params=params, timeout=timeout)


async def get_document_info_api(index_id: str, document_id: str) -> Optional[Dict[str, Any]]:
    """
    Call document info API - pure API call and return original response
    """
    try:
        api_base = get_api_base_url()
        document_detail_url = f"{api_base}/api/documents/{document_id}"
        print(f"[DOCUMENT_ANALYZER] API base URL: {api_base}")
        print(f"[DOCUMENT_ANALYZER] Full API URL: {document_detail_url}")
        
        # Add query parameters
        params = {}
        if index_id:
            params['index_id'] = index_id
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            _sync_http_request,
            document_detail_url,
            params,
            30
        )
        
        if response.status_code == 404:
            return {
                'success': False,
                'error': f'Document ID {document_id} not found.',
                'data': None
            }
        
        if response.status_code != 200:
            return {
                'success': False,
                'error': f'Document info API call failed: {response.status_code}',
                'data': None
            }
        
        api_response = response.json()
        
        # Return original API response as much as possible
        if 'document_id' in api_response:
            # If it's direct document data, wrap it in standard format
            return {
                'success': True,
                'data': {
                    'document': api_response,
                    'total_count': 1
                }
            }
        else:
            # If it's already wrapped response, return it as is
            return api_response
        
    except Exception as e:
        print(f"Error in document info API call: {e}")
        return {
            'success': False,
            'error': f'Error in document info API call: {str(e)}',
            'data': None
        }


async def get_document_analysis_api(document_id: str, filter_final: bool = True, index_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Call document detail API and extract only summary for lightweight response.
    
    Args:   
        document_id: Document ID
        filter_final: Kept for backward compatibility (unused)
        index_id: Index ID for access control
    """
    try:
        # Use document detail API which contains document-level summary
        document_detail_url = f"{get_api_base_url()}/api/documents/{document_id}"

        params = {}
        if index_id:
            params['index_id'] = index_id

        response = requests.get(document_detail_url, params=params, timeout=30)

        if response.status_code == 404:
            return {
                'success': False,
                'error': f'Document ID {document_id} not found.',
                'data': None
            }

        if response.status_code != 200:
            return {
                'success': False,
                'error': f'Document detail API call failed: {response.status_code}',
                'data': None
            }

        api_response = response.json()

        # Normalize to document dict
        document = None
        if isinstance(api_response, dict):
            if 'document_id' in api_response:
                document = api_response
            else:
                data = api_response.get('data', api_response)
                if isinstance(data, dict):
                    document = data.get('document') or (data if 'document_id' in data else None)

        summary_text = ''
        if isinstance(document, dict):
            summary_text = document.get('summary') or ''

        return {
            'success': True,
            'data': {
                'document_id': document_id,
                'index_id': index_id,
                'summary': summary_text,
            }
        }

    except Exception as e:
        print(f"Error in document summary API call: {e}")
        return {
            'success': False,
            'error': f'Error in document summary API call: {str(e)}',
            'data': None
        }


async def get_page_analysis_details_api(index_id: str, document_id: str, segment_id: str, filter_final: bool = True) -> Optional[Dict[str, Any]]:
    """
    Call page analysis details API - pure API call and return original response
    
    Args:
        index_id: Index ID for access control
        document_id: Document ID
        segment_id: Segment ID
        filter_final: If True, only return final_ai_response (default: True for optimization)
        index_id: Index ID for access control
    """
    try:
        url = f"{get_api_base_url()}/api/opensearch/documents/{document_id}/segments/{segment_id}"
        
        print(f"Page analysis API call: {url}")
        
        # Add query parameters
        params = {}
        if filter_final:
            params['filter_final'] = 'true'
        if index_id:
            params['index_id'] = index_id
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            # Return original API response as much as possible
            return response.json()
        else:
            print(f"API call failed: {response.status_code}")
            # Fallback: Filter only the page from the document analysis
            fallback_result = await get_document_analysis_api(document_id, filter_final, index_id)
            if fallback_result and fallback_result.get('success'):
                # Add metadata to handle page filtering in response_formatter
                fallback_result['_fallback_segment_id'] = segment_id
                return fallback_result
            else:
                return {
                    'success': False,
                    'error': f'Segment analysis API call failed: {response.status_code}',
                    'data': None
                }
            
    except Exception as e:
        print(f"Error in segment analysis API call: {str(e)}")
        return {
            'success': False,
            'error': f'Error in segment analysis API call: {str(e)}',
            'data': None
        }


# ============================================================================
# MCP Tool Functions
# ============================================================================

async def get_document_info(index_id: str = None, document_id: str = None):
    """
    Get basic information about a specific document including metadata, file details, and summary.
    If you don't know the document_id, you can use the document_list tool to view the document list.
    
    Args:
        index_id: Index ID to retrieve (Ex. 3d8ab04c-af9c-4cde-b962-a4cd7f1104b7)
        document_id: Document ID to retrieve (Ex.3d8ab04c-af9c-4cde-b962-a4cd7f1104b7)
    
    Returns:
        Formatted response with API data, references, and LLM guide
    """
    if not index_id:
        return {
            "success": False,
            "error": "Index ID is required. Provide as parameter or set in LangGraph state.",
            "data": None
        }
    
    if not document_id:
        return {
            "success": False,
            "error": "Document ID is required. Provide as parameter or set in LangGraph state.",
            "data": None
        }
    
    print(f"Retrieving document info: index_id={index_id}, document_id={document_id}")
    
    # API call
    api_response = await get_document_info_api(index_id, document_id)
    
    # Useeresponsepformatterpto createastandardizederesponseto createastandardizederesponseto create standardized response
    return format_api_response(api_response, 'get_document_info')


async def get_document_analysis(index_id: str = None, document_id: str = None, filter_final: bool = True):
    """
    Get the comprehensive analysis result of a specific document including all pages and analysis data.
    Use this tool when you want to get the comprehensive analysis result of a specific document including all pages and analysis data.
    
    Args:
        index_id: Index ID for access control (Have to be provided)
        document_id: Document ID to retrieve (Ex.3d8ab04c-af9c-4cde-b962-a4cd7f1104b7)
        filter_final: If True, only return final_ai_response for optimization (default: True)
    
    Returns:
        Formatted response with API data, references, and LLM guide
    """
    if not index_id:
        return {
            "success": False,
            "error": "Index ID is required. Provide as parameter or set in LangGraph state.",
            "data": None
        }
    
    if not document_id:
        return {
            "success": False,
            "error": "Document ID is required. Provide as parameter or set in LangGraph state.",
            "data": None
        }
    
    print(f"Retrieving document analysis: index_id={index_id}, document_id={document_id}, filter_final={filter_final}")
    
    # API call
    api_response = await get_document_analysis_api(document_id, filter_final, index_id)
    
    # Useeresponsepformatter to createastandardizederesponseto createastandardizederesponseto create standardized response
    return format_api_response(api_response, 'get_document_analysis')


async def get_page_analysis_details(index_id: str = None, document_id: str = None, segment_id: str = None, filter_final: bool = True):
    """
    Get detailed analysis results for a specific page of a document.
    Use this tool when you want to get the detailed analysis result of a specific page of a document.
    
    Args:
        index_id: Index ID for access control
        document_id: Document ID to retrieve 
        segment_id: Segment ID to get analysis for. (Ex. 3d8ab04c-af9c-4cde-b962-a4cd7f1104b7)
        filter_final: If True, only return final_ai_response for optimization (default: True)
    
    Returns:
        Formatted response with API data, references, and LLM guide
    """
    if not index_id:
        return {
            "success": False,
            "error": "Index ID is required. Provide as parameter or set in LangGraph state.",
            "data": None
        }
    
    if not document_id:
        return {
            "success": False,
            "error": "Document ID is required. Provide as parameter or set in LangGraph state.",
            "data": None
        }
        
    if not segment_id:
        return {
            "success": False,
            "error": "Segment ID is required.",
            "data": None
        }
    
    print(f"Retrieving page analysis: index_id={index_id}, document_id={document_id}, segment_index={segment_index}, filter_final={filter_final}")
    
    # API call
    api_response = await get_page_analysis_details_api(index_id, document_id, segment_id, filter_final)
    
    # Useeresponsepformatter to createastandardizederesponseto createastandardizederesponseto create standardized response
    return format_api_response(api_response, 'get_page_analysis_details')


async def get_segment_image_attachment(index_id: str = None, document_id: str = None, segment_id: str = None):
    """
    Retrieve a segment image as base64 from API and return LLM-ready attachment.

    Args:
        index_id: Index ID for access control
        document_id: Document ID to retrieve
        segment_id: Segment ID to retrieve

    Returns:
        Formatted response with API data, references, and LLM guide
    """

    if not index_id:
        return {
            "success": False,
            "error": "Index ID is required.",
            "data": None
        }
    
    if not document_id:
        return {
            "success": False,
            "error": "Document ID is required.",
            "data": None
        }

    if not segment_id:
        return {
            "success": False,
            "error": "segment_id is required",
            "data": None
        }

    try:
        url = f"{get_api_base_url()}/api/segments/{segment_id}/image"
        params = {}
        if index_id:
            params['index_id'] = index_id
        if document_id:
            params['document_id'] = document_id

        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return {
                "success": False,
                "error": f"Segment image API call failed: {resp.status_code}",
                "data": None
            }

        payload = resp.json()
        data = payload.get('data') or payload

        # Do NOT include base64 attachments by default to avoid token overflow
        attachments = []

        # Build UI references using S3 URI so frontend can render securely without passing base64 to LLM
        references = []
        image_uri = data.get('image_uri')
        if image_uri:
            references.append({
                'type': 'image',
                'title': 'Segment Image',
                'display_name': 'Segment Image',
                'value': image_uri,
                'image_uri': image_uri,
                'document_id': data.get('document_id', ''),
                'metadata': {
                    'segment_id': data.get('segment_id', segment_id),
                }
            })

        # Standard formatted tool response
        tool_data = {
            "success": True,
            "data": data,
            "attachments": attachments,
            "references": references,
        }

        return format_api_response(tool_data, 'get_segment_image_attachment')

    except Exception as e:
        return {
            "success": False,
            "error": f"Error in segment image tool: {str(e)}",
            "data": None
        }
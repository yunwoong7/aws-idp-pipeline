"""
Analysis tools for Strands Agent
"""
import requests
import uuid
import sys
import os
import logging
from typing import Dict, Any, Optional
from strands import tool

logger = logging.getLogger(__name__)


# Add agent root directory to Python path
agent_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, agent_root)

from config import config

@tool
def hybrid_search(index_id: str, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Perform hybrid search using semantic and keyword search to find relevant documents.
    This search combines vector similarity with keyword matching for better results.
    
    Args:
        index_id: Index ID for access control (Have to be provided)
        query: Search query string
        session_id: Session ID for reference deduplication (optional, auto-generated if not provided)
    
    Returns:
        ToolResult with search results
    """
    
    # Generate session_id if not provided for reference deduplication
    if not index_id:
        return {
            "status": "error",
            "content": [{"text": "Index ID is required"}]
        }
    
    if not session_id:
        session_id = str(uuid.uuid4())

    # API call
    api_response = hybrid_search_api(index_id, query, session_id)
    
    # Convert to ToolResult format
    if api_response.get('success'):
        # Format search results for display
        data = api_response.get('data', {})
        results = data.get('results', [])
        
        if results:
            results_text = f"Found {len(results)} documents:\n"
            for i, result in enumerate(results[:3], 1):
                document_id = result.get('document_id', 'Unknown')
                segment_id = result.get('segment_id', 'Unknown')
                segment_index = result.get('segment_index', -1)
                file_name = result.get('file_name', 'Untitled')
                content_combined = result.get('content_combined', 'Unknown')[:200]
                results_text += f"{i}. {file_name} (ID: {document_id}, Segment ID: {segment_id}, Segment Index: {segment_index})\n"
        else:
            results_text = "No documents found matching the search query."
            
        return {
            "status": "success",
            "content": [
                {"text": results_text},
                {"json": api_response}
            ]
        }
    else:
        error_msg = api_response.get('error', 'Search failed')
        return {
            "status": "error",
            "content": [{"text": f"Search error: {error_msg}"}]
        }

def hybrid_search_api(index_id: str, query: str, session_id: str = None) -> Dict[str, Any]:
    """
    Hybrid search API call
    """
    try:
        api_base_url = config.api_base_url
        url = f"{api_base_url}/api/opensearch/search/hybrid"
        
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


@tool
def get_document_info(index_id: str, document_id: str) -> Dict[str, Any]:
    """
    Get basic information about a specific document including metadata, file details, and summary.
    If you don't know the document_id, you can use the document_list tool to view the document list.
    
    Args:
        index_id: Index ID to retrieve (Ex. 3d8ab04c-af9c-4cde-b962-a4cd7f1104b7)
        document_id: Document ID to retrieve (Ex.3d8ab04c-af9c-4cde-b962-a4cd7f1104b7)
    
    Returns:
        ToolResult with document information
    """
    if not index_id:
        return {
            "status": "error",
            "content": [{"text": "Index ID is required"}]
        }
    
    if not document_id:
        return {
            "status": "error",
            "content": [{"text": "Document ID is required"}]
        }
    
    
    # API call
    api_response = get_document_info_api(index_id, document_id)
    
    # Convert to ToolResult format
    if api_response.get('success'):
        data = api_response.get('data', {})
        document = data.get('document', {})
        
        if document:
            doc_info = f"Document Information:\n"
            doc_info += f"- ID: {document.get('document_id', 'N/A')}\n"
            doc_info += f"- Title: {document.get('title', 'N/A')}\n"
            doc_info += f"- File Name: {document.get('file_name', 'N/A')}\n"
            doc_info += f"- File Size: {document.get('file_size', 'N/A')}\n"
            doc_info += f"- Upload Date: {document.get('created_at', 'N/A')}\n"
            doc_info += f"- Status: {document.get('status', 'N/A')}\n"
            if document.get('summary'):
                doc_info += f"- Summary: {document['summary']}\n"
        else:
            doc_info = "No document information available."
            
        return {
            "status": "success",
            "content": [
                {"text": doc_info},
                {"json": api_response}
            ]
        }
    else:
        error_msg = api_response.get('error', 'Failed to retrieve document info')
        return {
            "status": "error",
            "content": [{"text": f"Error: {error_msg}"}]
        }


@tool
def get_page_analysis_details(index_id: str, document_id: str, segment_id: str, filter_final: bool = True) -> Dict[str, Any]:
    """
    Get detailed analysis results for a specific page of a document.
    Use this tool when you want to get the detailed analysis result of a specific page of a document.
    
    Args:
        index_id: Index ID for access control
        document_id: Document ID to retrieve 
        segment_id: Segment ID to get analysis for. (Ex. 3d8ab04c-af9c-4cde-b962-a4cd7f1104b7)
        filter_final: If True, only return final_ai_response for optimization (default: True)
    
    Returns:
        ToolResult with page analysis details
    """
    if not index_id:
        return {
            "status": "error",
            "content": [{"text": "Index ID is required"}]
        }
    
    if not document_id:
        return {
            "status": "error", 
            "content": [{"text": "Document ID is required"}]
        }
        
    if not segment_id:
        return {
            "status": "error",
            "content": [{"text": "Segment ID is required"}]
        }
    
    
    # API call
    api_response = get_page_analysis_details_api(index_id, document_id, segment_id, filter_final)
    
    # Convert to ToolResult format
    if api_response.get('success'):
        # Support both wrapped and direct payloads
        data = api_response.get('data') or api_response

        # Compose concise summary
        summary_lines = ["Page Analysis Summary:"]
        try:
            idx = data.get('index_id') or data.get('index') or ''
            doc = data.get('document_id') or ''
            seg = data.get('segment_id') or ''
            if idx:
                summary_lines.append(f"- Index: {idx}")
            if doc:
                summary_lines.append(f"- Document: {doc}")
            if seg:
                summary_lines.append(f"- Segment: {seg}")
            if 'page_number' in data:
                summary_lines.append(f"- Page: {data.get('page_number')}")

            # Prefer final summary if present
            final_resp = data.get('final_ai_response')
            if isinstance(final_resp, str) and final_resp.strip():
                trimmed = (final_resp[:400] + '…') if len(final_resp) > 400 else final_resp
                summary_lines.append("")
                summary_lines.append(trimmed)
            else:
                # Fallback: show up to 2 analysis_results entries (trimmed)
                results = data.get('analysis_results') or []
                if isinstance(results, list) and results:
                    max_show = min(2, len(results))
                    for i in range(max_show):
                        r = results[i] if isinstance(results[i], dict) else {}
                        tool_name = r.get('tool_name') or 'analysis'
                        content = r.get('content') or ''
                        content_trimmed = (content[:400] + '…') if isinstance(content, str) and len(content) > 400 else content
                        summary_lines.append("")
                        summary_lines.append(f"[{i+1}] {tool_name}")
                        if content_trimmed:
                            summary_lines.append(content_trimmed)
                else:
                    # Last resort: brief mention
                    summary_lines.append("(No detailed analysis content available)")

            # Optional: image presence hint
            if data.get('image_file_uri'):
                summary_lines.append("\n- Image included")

        except Exception:
            # In case of unexpected structure, keep very short
            summary_lines = ["Page Analysis Summary:", "(Unable to summarize content)"]

        analysis_text = "\n".join(summary_lines)

        return {
            "status": "success",
            "content": [
                {"text": analysis_text},
                {"json": api_response}
            ]
        }
    else:
        error_msg = api_response.get('error', 'Failed to retrieve page analysis')
        return {
            "status": "error",
            "content": [{"text": f"Error: {error_msg}"}]
        }


@tool
def get_segment_image_attachment(index_id: str, document_id: str, segment_id: str) -> Dict[str, Any]:
    """
    Retrieve segment image URL for agent to download and pass to LLM.
    Returns a signal with image URL for the agent to handle.

    Args:
        index_id: Index ID for access control
        document_id: Document ID to retrieve
        segment_id: Segment ID to retrieve

    Returns:
        Signal with image URL for agent to process
    """
    if not index_id:
        return {"status": "error", "content": [{"text": "Index ID is required"}]}
    
    if not document_id:
        return {"status": "error", "content": [{"text": "Document ID is required"}]}

    if not segment_id:
        return {"status": "error", "content": [{"text": "Segment ID is required"}]}

    try:
        api_base_url = config.api_base_url
        url = f"{api_base_url}/api/segments/{segment_id}/image"
        params = {}
        if index_id:
            params['index_id'] = index_id
        if document_id:
            params['document_id'] = document_id

        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return [{"text": f"Error: Segment image API call failed with status {resp.status_code}"}]

        payload = resp.json()
        data = payload.get('data') or payload
        
        # Extract image URL information
        image_uri = data.get('image_uri')
        image_presigned_url = data.get('image_presigned_url')
        mime_type = data.get('mime_type', 'image/png')
        
        if image_presigned_url:
            # Return only URL signal with agreed marker; agent will download/process
            return {
                "status": "success",
                "content": [
                    {"text": "[[SEGMENT_IMAGE_URL]]"},
                    {"json": {
                        "type": "segment_image_url",
                        "url": image_presigned_url,
                        "fallback_url": image_uri,
                        "mime_type": mime_type,
                        "segment_id": segment_id,
                        "document_id": document_id,
                        "index_id": index_id
                    }}
                ]
            }
        elif image_uri:
            # Fallback to non-presigned image URI
            return {
                "status": "success",
                "content": [
                    {"text": "[[SEGMENT_IMAGE_URL]]"},
                    {"json": {
                        "type": "segment_image_url",
                        "url": image_uri,
                        "mime_type": mime_type,
                        "segment_id": segment_id,
                        "document_id": document_id,
                        "index_id": index_id,
                        "note": "no_presigned_url"
                    }}
                ]
            }
        else:
            return {"status": "error", "content": [{"text": f"No image available for segment {segment_id}"}]}

    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error retrieving segment image: {str(e)}"}]}


# API helper functions
def get_document_info_api(index_id: str, document_id: str) -> Dict[str, Any]:
    """
    Call document info API - pure API call and return original response
    """
    try:
        api_base_url = config.api_base_url
        document_detail_url = f"{api_base_url}/api/documents/{document_id}"
        
        # Add query parameters
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


def get_page_analysis_details_api(index_id: str, document_id: str, segment_id: str, filter_final: bool = True) -> Dict[str, Any]:
    """
    Call page analysis details API - pure API call and return original response
    
    Args:
        index_id: Index ID for access control
        document_id: Document ID
        segment_id: Segment ID
        filter_final: If True, only return final_ai_response (default: True for optimization)
    """
    try:
        api_base_url = config.api_base_url
        # Align with working Postman endpoint
        url = f"{api_base_url}/api/documents/{document_id}/segments/{segment_id}"
        
        
        # Add query parameters
        params = {}
        if filter_final:
            params['filter_final'] = 'true'
        if index_id:
            params['index_id'] = index_id
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            # Normalize to standard success wrapper
            payload = response.json()
            return {
                'success': True,
                'data': payload
            }
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
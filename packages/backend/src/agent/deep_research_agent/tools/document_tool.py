"""
Document Analysis Tool - MCP wrapper for document_analyzer
"""
import asyncio
import aiohttp
import requests
import atexit
from typing import Dict, Any, Optional, List
try:
    from strands import tool
except ImportError:
    from ..mock_strands import tool
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from project root .env file
# Path structure: /aws-idp-pipeline/packages/backend/src/agent/deep_research_agent/tools/document_tool.py
# Go up 7 levels to reach /aws-idp-pipeline/.env
current_path = Path(__file__)
path_parts = current_path.parts
project_root_parts = path_parts[:-7]  # Remove the last 7 parts
project_root = Path(*project_root_parts)
env_path = project_root / '.env'
load_dotenv(env_path)
print(f"Loading .env from: {env_path}")
print(f"Exists: {env_path.exists()}")


# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Document info cache to avoid repeated API calls
_document_cache = {}

# Global aiohttp session for connection pooling
_aiohttp_session = None

async def get_aiohttp_session():
    """Get or create a global aiohttp session for connection pooling"""
    global _aiohttp_session
    if _aiohttp_session is None or _aiohttp_session.closed:
        connector = aiohttp.TCPConnector(
            limit=50,  # Reduced total connections
            limit_per_host=10,  # Reduced per-host connections
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True,
            ssl=False,  # Disable SSL for local development
            force_close=True,  # Force close connections after each request
            enable_cleanup_closed=True  # Enable cleanup of closed connections
        )
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        _aiohttp_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
    return _aiohttp_session


async def _cleanup_session():
    """Cleanup aiohttp session on shutdown"""
    global _aiohttp_session
    if _aiohttp_session and not _aiohttp_session.closed:
        await _aiohttp_session.close()


# Register cleanup function
def _sync_cleanup():
    """Synchronous cleanup wrapper"""
    try:
        asyncio.run(_cleanup_session())
    except:
        pass  # Ignore errors during shutdown

atexit.register(_sync_cleanup)


async def _get_document_info_api(index_id: str, document_id: str) -> Optional[Dict[str, Any]]:
    """Get document status from new status API endpoint"""
    try:
        # Use the new status endpoint
        document_status_url = f"{API_BASE_URL}/api/documents/{document_id}/status"
        print(f"DEBUG: Using API_BASE_URL: {API_BASE_URL}")
        print(f"DEBUG: Full URL: {document_status_url}")
        
        params = {}
        if index_id:
            params['index_id'] = index_id
        else:
            # index_id is required for document access
            raise ValueError("index_id is required for document access")
        
        # Use aiohttp for async HTTP request with retry on SSL errors
        session = await get_aiohttp_session()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.get(document_status_url, params=params) as response:
                    status_code = response.status
                    response_json = await response.json() if status_code == 200 else None
                break  # Success, exit retry loop
                
            except (aiohttp.ClientOSError, aiohttp.ServerDisconnectedError, asyncio.TimeoutError) as e:
                print(f"DEBUG: HTTP error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    # Last attempt failed, raise the error
                    raise e
                # Recreate session on SSL/connection errors
                if _aiohttp_session:
                    await _aiohttp_session.close()
                    _aiohttp_session = None
                session = await get_aiohttp_session()
                await asyncio.sleep(0.5)  # Brief wait before retry
        
        if status_code == 404:
            return {
                'success': False,
                'error': f'Document ID {document_id} not found.',
                'data': None
            }
        
        if status_code != 200:
            return {
                'success': False,
                'error': f'Document status API call failed: {status_code}',
                'data': None
            }
        
        api_response = response_json
        
        # Check if the response indicates success and document exists
        if api_response.get('exists', False):
            return {
                'success': True,
                'data': {
                    'document': {
                        'document_id': api_response['document_id'],
                        'status': api_response.get('status', 'unknown'),
                        'file_name': api_response.get('file_name', ''),
                        'total_pages': api_response.get('total_pages', 0),
                        'total_segments': api_response.get('total_segments', 0),
                        'segment_ids': api_response.get('segment_ids', []),
                        'media_type': api_response.get('media_type', ''),
                        'file_size': api_response.get('file_size', 0),
                        'created_at': api_response.get('created_at', ''),
                        'updated_at': api_response.get('updated_at', '')
                    },
                    'total_count': 1,
                    'total_pages': api_response.get('total_pages', 0),
                    'total_segments': api_response.get('total_segments', 0),
                    'segment_ids': api_response.get('segment_ids', [])
                }
            }
        else:
            return {
                'success': False,
                'error': f'Document ID {document_id} not found.',
                'data': None
            }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Error in document status API call: {str(e)}',
            'data': None
        }


async def _get_document_analysis_api(document_id: str, filter_final: bool = True, index_id: str = None) -> Optional[Dict[str, Any]]:
    """Get document analysis from API"""
    try:
        opensearch_url = f"{API_BASE_URL}/api/opensearch/documents/{document_id}"
        
        params = {}
        if filter_final:
            params['filter_final'] = 'true'
        if index_id:
            params['index_id'] = index_id
        
        # Use aiohttp for async HTTP request with retry on SSL errors
        session = await get_aiohttp_session()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.get(opensearch_url, params=params) as response:
                    status_code = response.status
                    response_json = await response.json() if status_code == 200 else None
                break  # Success, exit retry loop
                
            except (aiohttp.ClientOSError, aiohttp.ServerDisconnectedError, asyncio.TimeoutError) as e:
                print(f"DEBUG: HTTP error in document overview on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise e
                # Recreate session on errors
                global _aiohttp_session
                if _aiohttp_session:
                    await _aiohttp_session.close()
                    _aiohttp_session = None
                session = await get_aiohttp_session()
                await asyncio.sleep(0.5)
        
        if status_code != 200:
            return {
                'success': False,
                'error': f'Document analysis API call failed: {status_code}',
                'data': None
            }
        
        return response_json
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Error in document analysis API call: {str(e)}',
            'data': None
        }


def get_segment_detail_sync(
    document_id: str,
    segment_id: str,
    index_id: str
) -> Dict[str, Any]:
    """
    Purely synchronous version using requests library to avoid asyncio issues
    """
    try:
        # Use document info cache first
        cache_key = f"{document_id}_{index_id}"
        if cache_key not in _document_cache:
            # Get document info synchronously
            doc_info_result = _get_document_info_sync(document_id, index_id)
            if not doc_info_result.get("success"):
                return doc_info_result
            _document_cache[cache_key] = doc_info_result
        else:
            print(f"DEBUG: Using cached document info for {document_id}")
        
        # Now get segment detail synchronously
        segment_detail_url = f"{API_BASE_URL}/api/documents/{document_id}/segments/{segment_id}"
        params = {'index_id': index_id}
        
        # Use requests for synchronous HTTP call
        try:
            response = requests.get(segment_detail_url, params=params, timeout=30)
            status_code = response.status_code
            
            if status_code == 404:
                return {
                    "success": False,
                    "error": f"Segment {segment_id} not found in document {document_id}",
                    "segment_id": segment_id
                }
            
            if status_code != 200:
                return {
                    "success": False,
                    "error": f"API call failed with status {status_code}: {response.text}",
                    "segment_id": segment_id
                }
            
            response_json = response.json()
            
            # Extract analysis results from the API response
            analysis_results = response_json.get("analysis_results", [])
            
            # Combine all analysis content
            combined_content = []
            all_metadata = {}
            
            for result in analysis_results:
                tool_name = result.get("tool_name", "unknown")
                content = result.get("content", "")
                if content:
                    combined_content.append(f"=== {tool_name} 분석 ===\n{content}")
                
                # Merge metadata if available
                if "metadata" in result:
                    all_metadata[tool_name] = result["metadata"]
            
            full_content = "\n\n".join(combined_content)
            
            # Create comprehensive summary
            num_analyses = len(analysis_results)
            content_length = len(full_content)
            tools_used = [r.get("tool_name", "unknown") for r in analysis_results]
            
            analysis_summary = f"세그먼트 {segment_id}: {num_analyses}개 도구로 분석 완료 ({', '.join(tools_used)}). 총 내용 길이: {content_length} 문자"
            
            return {
                "success": True,
                "content": full_content,
                "metadata": all_metadata,
                "segment_id": segment_id,
                "analysis_summary": analysis_summary,
                "analysis_count": num_analyses,
                "tools_used": tools_used
            }
            
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"HTTP request failed: {str(e)}",
                "segment_id": segment_id
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Sync function error: {str(e)}",
            "segment_id": segment_id
        }


def _get_document_info_sync(document_id: str, index_id: str) -> Dict[str, Any]:
    """Synchronous version of document info retrieval"""
    try:
        document_status_url = f"{API_BASE_URL}/api/documents/{document_id}/status"
        params = {'index_id': index_id}
        
        response = requests.get(document_status_url, params=params, timeout=30)
        status_code = response.status_code
        
        if status_code == 404:
            return {
                'success': False,
                'error': f'Document ID {document_id} not found.'
            }
        
        if status_code != 200:
            return {
                'success': False,
                'error': f'API call failed with status {status_code}: {response.text}'
            }
        
        response_json = response.json()
        return {
            'success': True,
            'data': response_json
        }
        
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': f'HTTP request failed: {str(e)}'
        }


@tool
def get_segment_detail(
    document_id: str,
    segment_id: str,
    index_id: str
) -> Dict[str, Any]:
    """
    Get detailed information about a specific segment (synchronous version for Strands)
    
    Args:
        document_id: Document ID
        segment_id: Segment ID to analyze
        index_id: Index ID for access control (required)
    
    Returns:
        Segment detail including content and metadata
    """
    return get_segment_detail_sync(document_id, segment_id, index_id)


async def get_segment_detail_async(
    document_id: str,
    segment_id: str,
    index_id: str
) -> Dict[str, Any]:
    """
    Get detailed analysis for a specific segment of a document.
    
    Args:
        document_id: Document ID to analyze
        segment_id: Segment ID 
        index_id: Index ID for access control (required)
    
    Returns:
        Segment analysis with summary and evidence
    """
    try:
        # First, get document info using cached overview
        doc_overview = await get_document_overview_async(document_id, index_id)
        
        if not doc_overview or not doc_overview.get('success'):
            return {
                "success": False,
                "error": f"Failed to get document info: {doc_overview.get('error', 'Unknown error')}",
                "segment_id": segment_id
            }
        
        # Use the new segment detail API endpoint
        segment_detail_url = f"{API_BASE_URL}/api/documents/{document_id}/segments/{segment_id}"
        
        params = {'index_id': index_id}
        
        # Use shared aiohttp session for better performance with retry logic
        session = await get_aiohttp_session()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.get(segment_detail_url, params=params) as response:
                    status_code = response.status
                    response_json = await response.json() if status_code == 200 else None
                break  # Success, exit retry loop
                
            except (aiohttp.ClientOSError, aiohttp.ServerDisconnectedError, asyncio.TimeoutError) as e:
                print(f"DEBUG: HTTP error in segment detail on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise e
                # Recreate session on errors
                global _aiohttp_session
                if _aiohttp_session:
                    await _aiohttp_session.close()
                    _aiohttp_session = None
                session = await get_aiohttp_session()
                await asyncio.sleep(0.5)
        
        if status_code == 404:
            return {
                "success": False,
                "error": f"Segment {segment_id} not found for document {document_id}",
                "segment_id": segment_id
            }
        
        if status_code != 200:
            return {
                "success": False,
                "error": f"Segment detail API call failed: {status_code}",
                "segment_id": segment_id
            }
        
        api_response = response_json
        
        if not api_response.get('success', True):
            return {
                "success": False,
                "error": f"No analysis found for segment {segment_id}",
                "segment_id": segment_id
            }
        
        # Extract segment data from API response
        segment_data = api_response
        
        return {
            "success": True,
            "document_id": document_id,
            "segment_id": segment_id,
            "evidence": {
                "segment_data": segment_data,
                "analysis": segment_data.get('analysis', {}),
                "content": segment_data.get('content', ''),
                "metadata": segment_data.get('metadata', {})
            },
            "summary": segment_data.get('summary', f"Analysis for segment {segment_id}")
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Error analyzing segment: {str(e)}",
            "segment_id": segment_id
        }


@tool
def get_document_overview(
    document_id: str,
    index_id: str
) -> Dict[str, Any]:
    """
    Get overview information about a document (synchronous version for Strands).
    
    Args:
        document_id: Document ID to get overview for
        index_id: Index ID for access control (required)
    
    Returns:
        Document overview with metadata and segment list
    """
    import threading
    
    try:
        # Always use a new event loop in a separate thread for safety
        result = None
        exception = None
        
        def run_async():
            nonlocal result, exception
            try:
                # Create a new event loop for this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                
                # Run the async function
                result = new_loop.run_until_complete(
                    get_document_overview_async(document_id, index_id)
                )
                
                # Clean up
                new_loop.close()
                asyncio.set_event_loop(None)
                
            except Exception as e:
                exception = e
            finally:
                # Ensure cleanup
                try:
                    if 'new_loop' in locals() and new_loop and not new_loop.is_closed():
                        new_loop.close()
                except:
                    pass
        
        # Run in separate thread to avoid event loop conflicts
        thread = threading.Thread(target=run_async)
        thread.start()
        thread.join(timeout=60)  # 60 second timeout
        
        if thread.is_alive():
            return {
                "success": False,
                "error": "Tool call timed out after 60 seconds"
            }
        
        if exception:
            return {
                "success": False,
                "error": f"Async execution error: {str(exception)}"
            }
            
        return result if result is not None else {
            "success": False,
            "error": "No result returned from async function"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Sync wrapper error: {str(e)}"
        }


async def get_document_overview_async(
    document_id: str,
    index_id: str
) -> Dict[str, Any]:
    """
    Get overview information about a document.
    
    Args:
        document_id: Document ID
        index_id: Index ID for access control (required)
    
    Returns:
        Document overview with metadata including segment information
    """
    # Check cache first
    cache_key = f"{document_id}:{index_id}"
    if cache_key in _document_cache:
        print(f"DEBUG: Using cached document info for {document_id}")
        return _document_cache[cache_key]
    
    try:
        print(f"DEBUG: Fetching fresh document info for {document_id}")
        doc_info = await _get_document_info_api(
            index_id=index_id,
            document_id=document_id
        )
        
        if not doc_info or not doc_info.get('success'):
            return {
                "success": False,
                "error": doc_info.get('error', 'Failed to get document info')
            }
        
        doc_data = doc_info.get('data', {}).get('document', {})
        
        result = {
            "success": True,
            "document_id": document_id,
            "title": doc_data.get('file_name', 'Unknown'),
            "total_pages": doc_data.get('total_pages', 0),
            "total_segments": doc_data.get('total_segments', 0),
            "segment_ids": doc_data.get('segment_ids', []),
            "document_type": doc_data.get('media_type', 'Unknown'),
            "created_at": doc_data.get('created_at'),
            "metadata": {
                "file_size": doc_data.get('file_size'),
                "mime_type": doc_data.get('mime_type'),
                "status": doc_data.get('status')
            }
        }
        
        # Cache the result for future use
        _document_cache[cache_key] = result
        print(f"DEBUG: Cached document info for {document_id}")
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Error getting document overview: {str(e)}"
        }


def clear_document_cache(document_id: str = None):
    """
    Clear document cache for a specific document or all documents
    
    Args:
        document_id: If provided, clear only this document's cache. If None, clear all.
    """
    global _document_cache
    
    if document_id is None:
        _document_cache.clear()
        print("DEBUG: Cleared all document cache")
    else:
        # Clear all entries for this document_id
        keys_to_remove = [key for key in _document_cache.keys() if key.startswith(f"{document_id}:")]
        for key in keys_to_remove:
            del _document_cache[key]
        print(f"DEBUG: Cleared cache for document {document_id}")


def get_cache_info():
    """Get information about current cache state"""
    return {
        "cached_documents": len(_document_cache),
        "cache_keys": list(_document_cache.keys())
    }
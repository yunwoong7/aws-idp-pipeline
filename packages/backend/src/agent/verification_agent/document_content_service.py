"""
Document Content Service - Extract full document content from OpenSearch
"""
import requests
import asyncio
import logging
from typing import Dict, Any, Optional, List
import os

logger = logging.getLogger(__name__)

# Get API base URL from environment or default
def get_api_base_url():
    """Get API base URL with intelligent detection"""
    # Try different environment variables
    api_url = (
        os.getenv("API_BASE_URL") or 
        os.getenv("NEXT_PUBLIC_API_BASE_URL") or 
        os.getenv("NEXT_PUBLIC_ECS_BACKEND_URL") or
        "http://localhost:8000"
    )
    
    # Remove /api suffix if present
    if api_url.endswith("/api"):
        api_url = api_url[:-4]
    
    logger.debug(f"🔧 Using API base URL: {api_url}")
    return api_url

API_BASE_URL = get_api_base_url()

def _sync_http_request(url: str, params: dict = None, timeout: int = 30) -> requests.Response:
    """Synchronous HTTP request function"""
    return requests.get(url, params=params, timeout=timeout)

async def get_document_analysis_api(document_id: str, index_id: str = None, filter_final: bool = False) -> Optional[Dict[str, Any]]:
    """
    Call document analysis API to get all analysis data
    
    Args:
        document_id: Document ID
        index_id: Index ID for access control
        filter_final: If False, get all analysis data (not just final response)
    """
    try:
        opensearch_url = f"{API_BASE_URL}/api/opensearch/documents/{document_id}"
        
        # Add query parameters
        params = {}
        if not filter_final:  # Get ALL data, not just final responses
            params['filter_final'] = 'false'
        if index_id:
            params['index_id'] = index_id
        
        logger.info(f"📄 Calling analysis API: {opensearch_url} with params: {params}")
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            _sync_http_request,
            opensearch_url,
            params,
            30
        )
        
        if response.status_code != 200:
            logger.error(f"API call failed with status {response.status_code}: {response.text}")
            return {
                'success': False,
                'error': f'Document analysis API call failed: {response.status_code}',
                'data': None
            }
        
        return response.json()
        
    except Exception as e:
        logger.error(f"Error in document analysis API call: {e}")
        return {
            'success': False,
            'error': f'Error in document analysis API call: {str(e)}',
            'data': None
        }

async def extract_document_content(document_id: str, index_id: str = None) -> str:
    """
    Extract full document content from OpenSearch analysis data
    
    Args:
        document_id: Document ID
        index_id: Index ID for access control
        
    Returns:
        Full document content as string
    """
    try:
        logger.info(f"🔍 Extracting content for document {document_id}")
        
        # Get all analysis data
        api_response = await get_document_analysis_api(document_id, index_id, filter_final=False)
        
        if not api_response or not api_response.get('success', True):
            error_msg = api_response.get('error', 'Unknown error') if api_response else 'No response'
            logger.error(f"Failed to get analysis data: {error_msg}")
            return ""
        
        # Extract data - handle the new API response structure
        data = api_response.get('data', {})
        
        # Check if data has segments structure
        if 'segments' in data:
            logger.info(f"📊 Found segments structure with {data.get('total_segments', 0)} segments")
            all_segments = data['segments']
        elif isinstance(data, list):
            logger.info(f"📋 Found list structure with {len(data)} items")
            all_segments = data
        else:
            logger.info("📋 Found single document structure")
            all_segments = [data]
        
        content_parts = []
        
        # Process each segment
        for segment_idx, segment_data in enumerate(all_segments):
            if not isinstance(segment_data, dict):
                continue
            
            logger.debug(f"🔍 Processing segment {segment_idx}: {segment_data.get('segment_id', 'unknown')}")
            
            # Extract from tools_detail structure (new API format)
            tools_detail = segment_data.get('tools_detail', {})
            if tools_detail:
                logger.info(f"📊 Found tools_detail with keys: {list(tools_detail.keys())}")
                
                # Strategy 1a: Extract from bda_indexer
                bda_results = tools_detail.get('bda_indexer', [])
                if isinstance(bda_results, list) and bda_results:
                    for bda_item in bda_results:
                        if isinstance(bda_item, dict) and 'content' in bda_item:
                            content = bda_item['content']
                            if content and len(content.strip()) > 10:
                                segment_idx = segment_data.get('segment_index', segment_idx)
                                content_parts.append(f"[Segment {segment_idx + 1} - BDA]\\n{content.strip()}\\n")
                                logger.debug(f"✅ Extracted BDA content: {len(content)} chars")
                
                # Strategy 1b: Extract from pdf_text_extractor
                pdf_results = tools_detail.get('pdf_text_extractor', [])
                if isinstance(pdf_results, list) and pdf_results:
                    for pdf_item in pdf_results:
                        if isinstance(pdf_item, dict) and 'content' in pdf_item:
                            content = pdf_item['content']
                            if content and len(content.strip()) > 10:
                                segment_idx = segment_data.get('segment_index', segment_idx)
                                content_parts.append(f"[Segment {segment_idx + 1} - PDF Text]\\n{content.strip()}\\n")
                                logger.debug(f"✅ Extracted PDF text content: {len(content)} chars")
                
                # Strategy 1c: Extract from ai_analysis
                ai_results = tools_detail.get('ai_analysis', [])
                if isinstance(ai_results, list) and ai_results:
                    for ai_item in ai_results:
                        if isinstance(ai_item, dict) and 'content' in ai_item:
                            content = ai_item['content']
                            if content and len(content.strip()) > 10:
                                segment_idx = segment_data.get('segment_index', segment_idx)
                                content_parts.append(f"[Segment {segment_idx + 1} - AI Analysis]\\n{content.strip()}\\n")
                                logger.debug(f"✅ Extracted AI analysis content: {len(content)} chars")
        
            # Strategy 1b: Look for segment-level content in each segment
            # Look for text_content directly at segment level
            if 'text_content' in segment_data:
                text = segment_data['text_content']
                if text and len(text.strip()) > 10:
                    segment_idx = segment_data.get('segment_index', segment_data.get('page_index', '?'))
                    content_parts.append(f"[Segment {segment_idx + 1}]\n{text.strip()}\n")
                    logger.debug(f"✅ Found segment text_content: {len(text)} chars")
            
            # Look for content in segment
            if 'content' in segment_data:
                text = segment_data['content']
                if text and len(text.strip()) > 10:
                    segment_idx = segment_data.get('segment_index', segment_data.get('page_index', '?'))
                    content_parts.append(f"[Segment {segment_idx + 1}]\n{text.strip()}\n")
                    logger.debug(f"✅ Found segment content: {len(text)} chars")
            
            # Look for final_ai_response at segment level
            if 'final_ai_response' in segment_data:
                ai_response = segment_data['final_ai_response']
                if ai_response and len(str(ai_response).strip()) > 10:
                    segment_idx = segment_data.get('segment_index', segment_data.get('page_index', '?'))
                    content_parts.append(f"[Segment {segment_idx + 1} AI Analysis]\n{str(ai_response).strip()}\n")
                    logger.debug(f"✅ Found segment AI response: {len(str(ai_response))} chars")
        
        # Strategy 2: Look for document-level content from first segment
        if not content_parts and all_segments:
            logger.info("📋 No analysis results found, trying document-level content")
            first_segment = all_segments[0] if isinstance(all_segments[0], dict) else {}
            
            # Look for document summary or description
            doc_summary = first_segment.get('summary') or first_segment.get('description')
            if doc_summary and len(doc_summary.strip()) > 20:
                content_parts.append(f"[Document Summary]\n{doc_summary.strip()}\n")
                logger.debug(f"✅ Used document summary: {len(doc_summary)} chars")
            
            # Look for representation content
            representation = first_segment.get('representation', {})
            if isinstance(representation, dict):
                markdown_content = representation.get('markdown')
                if markdown_content and len(markdown_content.strip()) > 20:
                    content_parts.append(f"[Document Content]\n{markdown_content.strip()}\n")
                    logger.debug(f"✅ Used representation markdown: {len(markdown_content)} chars")
        
        # Strategy 3: Extract metadata as fallback
        if not content_parts and all_segments:
            logger.warning("⚠️ No textual content found, using metadata")
            first_segment = all_segments[0] if isinstance(all_segments[0], dict) else {}
            
            file_name = first_segment.get('file_name', 'Unknown Document')
            file_type = first_segment.get('file_type', 'unknown')
            created_at = first_segment.get('created_at', 'unknown')
            
            # Debug: Log what fields are available
            available_fields = list(first_segment.keys())[:20]  # First 20 fields
            logger.info(f"📋 Available fields in document: {available_fields}")
            
            metadata_content = f"""
            Document: {file_name}
            Type: {file_type}
            Created: {created_at}
            
            [Note: No extractable text content available for this document. The document may still be processing or may be an image/video file.]
            """
            content_parts.append(metadata_content.strip())
        
        # Combine all content parts
        full_content = "\n\n".join(content_parts).strip()
        
        if full_content:
            logger.info(f"✅ Extracted {len(full_content)} characters from document {document_id}")
        else:
            logger.warning(f"⚠️ No content extracted from document {document_id}")
        
        return full_content
        
    except Exception as e:
        logger.error(f"❌ Error extracting content from document {document_id}: {e}")
        return ""

async def get_document_content(document_id: str, index_id: str = None) -> str:
    """
    Public interface to get document content
    
    Args:
        document_id: Document ID
        index_id: Index ID for access control
        
    Returns:
        Full document content as string
    """
    return await extract_document_content(document_id, index_id)

# Batch processing for multiple documents
async def get_multiple_documents_content(document_ids: List[str], index_id: str = None) -> Dict[str, str]:
    """
    Get content for multiple documents
    
    Args:
        document_ids: List of document IDs
        index_id: Index ID for access control
        
    Returns:
        Dictionary mapping document_id to content
    """
    results = {}
    
    # Process documents concurrently
    tasks = [
        get_document_content(doc_id, index_id) 
        for doc_id in document_ids
    ]
    
    contents = await asyncio.gather(*tasks, return_exceptions=True)
    
    for doc_id, content in zip(document_ids, contents):
        if isinstance(content, Exception):
            logger.error(f"Failed to get content for {doc_id}: {content}")
            results[doc_id] = ""
        else:
            results[doc_id] = content
    
    return results
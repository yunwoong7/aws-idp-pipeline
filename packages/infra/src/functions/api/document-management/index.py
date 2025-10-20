"""
AWS IDP AI Analysis - Document Management Lambda Function

Document management endpoints:
1. POST /api/documents/upload - Direct file upload (small files)
2. POST /api/documents/upload-large - Generate pre-signed URL for large file upload
3. POST /api/documents/{document_id}/upload-complete - Complete large file upload
4. GET /api/documents - List documents
5. GET /api/documents/{document_id} - Get document details
6. DELETE /api/documents/{document_id} - Delete document
7. GET /api/documents/{document_id}/pages/{page_index} - Get page details (OpenSearch based)
8. POST /api/documents/presigned-url - Generate pre-signed URL for S3 URI

OpenSearch management endpoints:
9. GET /api/opensearch/status - Check OpenSearch cluster status (supports ?index_id=xxx parameter)
10. POST /api/opensearch/indices/{index_name}/create - Create index
11. DELETE /api/opensearch/indices/{index_name} - Delete index
12. POST /api/opensearch/indices/{index_name}/recreate - Recreate index
13. GET /api/opensearch/documents/{document_id} - Get document
14. GET /api/opensearch/documents/{document_id}/pages/{page_index} - Get document page (0-based)
15. POST /api/opensearch/search/hybrid - Hybrid search (keyword + vector)
16. POST /api/opensearch/search/vector - Vector search
17. POST /api/opensearch/search/keyword - Keyword search
18. POST /api/get-presigned-url - Generate pre-signed URL for S3 URI
"""

import os
import sys
import json
from typing import Dict, Any
from datetime import datetime, timezone

# Add current directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from handlers.document_handlers import (
    handle_upload_document,
    handle_get_documents,
    handle_get_document_detail,
    handle_get_document_status,
    handle_delete_document,
    handle_generate_presigned_url,
    handle_generate_presigned_url_standalone,
    handle_generate_upload_presigned_url,
    handle_upload_complete
)
from handlers.segment_handlers import (
    handle_get_segment_detail,
    handle_get_segment_image
)
from handlers.opensearch_handlers import (
    handle_opensearch_status,
    handle_create_index,
    handle_delete_index,
    handle_recreate_index,
    handle_get_opensearch_documents,
    handle_get_opensearch_document_segment,
    handle_opensearch_hybrid_search,
    handle_opensearch_vector_search,
    handle_opensearch_keyword_search,
    handle_opensearch_sample_data,
    handle_add_user_content,
    handle_remove_user_content
)
from utils.response import (
    create_cors_response,
    create_not_found_response,
    create_internal_error_response,
    create_validation_error_response
)

import logging

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler function (modularized)
    Handles API Gateway HTTP API events.
    """
    start_time = datetime.now(timezone.utc)
    
    try:
        # Lambda handler start logging
        logger.info(f"Document management service started")
        logger.info(f"Received event: {json.dumps(event, ensure_ascii=False, indent=2)}")
        
        # Extract request info
        http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
        path = event.get('path') or event.get('rawPath', '')
        path_parameters = event.get('pathParameters') or {}
        body = event.get('body')
        
        # Debug logs
        logger.info(f">> Document management request: {http_method} {path}")
        logger.info(f">> Path parameters: {path_parameters}")
        logger.info(f">> Full event: {event}")
        
        # Handle OPTIONS request (CORS)
        if http_method == 'OPTIONS':
            return create_cors_response()
        
        # Parse path
        path_parts = [part for part in path.split('/') if part]
        
        # Routing logic
        response = None

        # Generate pre-signed URL (project independent) - handle first
        if http_method == 'POST' and '/api/get-presigned-url' in path:
            response = handle_generate_presigned_url_standalone(event)
        
        # OpenSearch APIs
        elif '/api/opensearch/' in path:
            # OpenSearch 상태 확인
            if http_method == 'GET' and path.endswith('/api/opensearch/status'):
                response = handle_opensearch_status(event)
            # Index management
            elif http_method == 'POST' and '/api/opensearch/indices/' in path and '/create' in path:
                response = handle_create_index(event)
            elif http_method == 'DELETE' and '/api/opensearch/indices/' in path:
                response = handle_delete_index(event)
            elif http_method == 'POST' and '/api/opensearch/indices/' in path and '/recreate' in path:
                response = handle_recreate_index(event)
            # OpenSearch document retrieval
            elif http_method == 'GET' and '/api/opensearch/documents/' in path:
                if '/segments/' in path:
                    response = handle_get_opensearch_document_segment(event)
                else:
                    response = handle_get_opensearch_documents(event)
            # OpenSearch search features
            elif http_method == 'POST' and '/api/opensearch/search/hybrid' in path:
                response = handle_opensearch_hybrid_search(event)
            elif http_method == 'POST' and '/api/opensearch/search/vector' in path:
                response = handle_opensearch_vector_search(event)
            elif http_method == 'POST' and '/api/opensearch/search/keyword' in path:
                response = handle_opensearch_keyword_search(event)
            # OpenSearch sample data
            elif http_method == 'GET' and '/api/opensearch/data/sample' in path:
                response = handle_opensearch_sample_data(event)
            # User content management
            elif http_method == 'POST' and '/api/opensearch/user-content/add' in path:
                response = handle_add_user_content(event)
            elif http_method == 'POST' and '/api/opensearch/user-content/remove' in path:
                response = handle_remove_user_content(event)
        
        # If pre-signed URL standalone handled, return response immediately
        if response is not None:
            return response
        
        # Document management APIs (project-independent)
        if response is None:
            # Document management endpoints (no project_id required)
            # GET /api/segments/{segment_id}/image - Return base64 image by segment_id
            if http_method == 'GET' and '/api/segments/' in path and path.endswith('/image'):
                response = handle_get_segment_image(event)
            
            if http_method == 'POST' and '/upload-large' in path:
                # POST /api/documents/upload-large - 대용량 파일 업로드 Pre-signed URL 생성
                response = handle_generate_upload_presigned_url(event)
                
            elif http_method == 'POST' and '/upload-complete' in path:
                # POST /api/documents/{document_id}/upload-complete - 대용량 파일 업로드 완료 처리
                response = handle_upload_complete(event)
                
            elif http_method == 'POST' and '/upload' in path and '/upload-large' not in path and '/upload-complete' not in path:
                # POST /api/documents/upload - 직접 파일 업로드 (소용량)
                response = handle_upload_document(event)
                
            elif http_method == 'POST' and '/presigned-url' in path:
                # POST /api/documents/presigned-url - S3 URI로 Pre-signed URL 생성
                response = handle_generate_presigned_url(event)
                
            elif http_method == 'GET' and '/documents' in path:
                if '/segments/' in path:
                    # GET /api/documents/{doc_id}/segments/{segment_index}
                    response = handle_get_segment_detail(event)
                elif '/status' in path and path_parameters.get('document_id'):
                    # GET /api/documents/{document_id}/status
                    response = handle_get_document_status(event)
                elif path_parameters.get('document_id'):
                    # GET /api/documents/{document_id}
                    response = handle_get_document_detail(event)
                else:
                    # GET /api/documents
                    response = handle_get_documents(event)
                    
            elif http_method == 'DELETE' and '/documents/' in path:
                # DELETE /api/documents/{document_id}
                response = handle_delete_document(event)
                
        if response is None:
            response = create_not_found_response("Unsupported endpoint.")
        
        return response
            
    except Exception as e:
        # Log all errors
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        logger.error("=" * 80)
        logger.error("DOCUMENT MANAGEMENT SERVICE LAMBDA HANDLER ERROR")
        logger.error("=" * 80)
        logger.error(f"Error occurred at: {end_time.isoformat()}")
        logger.error(f"Processing time before error: {duration:.3f}s")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Request ID: {context.aws_request_id}")
        
        # Log stack trace
        import traceback
        logger.error("Stack trace:")
        logger.error(traceback.format_exc())
        
        logger.error("=" * 80)
        
        return create_internal_error_response(f"Document management service processing failed: {str(e)}")
    
    finally:
        # Lambda handler completion logging
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        logger.info("=" * 80)
        logger.info("DOCUMENT MANAGEMENT SERVICE LAMBDA HANDLER COMPLETE")
        logger.info("=" * 80)
        logger.info(f"End time: {end_time.isoformat()}")
        logger.info(f"Total processing time: {duration:.3f}s")
        logger.info("=" * 80)
"""
OpenSearch-based page detail lookup API processing function
"""

import os
import sys
import json
from typing import Dict, Any, List
import logging

# Lambda Layer imports
from common import OpenSearchService, S3Service, create_success_response, handle_lambda_error
import boto3
import mimetypes

# Add parent directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.response import (
    create_validation_error_response,
    create_not_found_response,
    create_internal_error_response
)
from utils.environment import (
    get_opensearch_endpoint,
    get_opensearch_index_name,
    get_opensearch_region,
    get_documents_table_name,
    get_documents_bucket_name
)
from utils.helpers import generate_presigned_url

# Service initialization functions
def _get_opensearch_service():
    """Get OpenSearch service"""
    return OpenSearchService()

def _get_s3_service():
    """Get S3 service"""
    return boto3.client('s3')

logger = logging.getLogger()


def handle_get_segment_detail(event: Dict[str, Any]) -> Dict[str, Any]:
    """Get detailed information for a specific page (OpenSearch-based)"""
    try:
        path_parameters = event.get('pathParameters', {})
        query_params = event.get('queryStringParameters') or {}
        index_id = query_params.get('index_id')
        document_id = path_parameters.get('document_id')
        segment_id = path_parameters.get('segment_id')
        
        if not index_id or not document_id or segment_id is None:
            return create_validation_error_response("index_id, document_id, segment_id is required")
        
        logger.info(f"Page detail lookup request: index_id={index_id}, document_id={document_id}, segment_id={segment_id}")
        
        # OpenSearch environment settings
        OPENSEARCH_ENDPOINT = get_opensearch_endpoint()
        DOCUMENTS_BUCKET_NAME = get_documents_bucket_name()
        
        if not OPENSEARCH_ENDPOINT:
            return create_internal_error_response("OpenSearch endpoint is not set")
        
        # Get OpenSearch service (segment-based structure)
        try:
            opensearch = _get_opensearch_service()
            s3 = _get_s3_service()
            
            # Query for specific segment (previously page)
            search_body = {
                "size": 1,
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"document_id": document_id}},
                            {"term": {"segment_id": segment_id}}
                        ]
                    }
                }
            }
            
            logger.info(f"OpenSearch search query: {search_body}")
            
            # Execute OpenSearch search (align with opensearch_handlers usage)
            response = opensearch.client.search(
                index=index_id,
                body=search_body
            )
            
            # Parse results
            hits = response.get('hits', {}).get('hits', [])
            
            if not hits:
                return create_not_found_response(f"Segment not found: index_id={index_id}, document_id={document_id}, segment_id={segment_id}")
            
            hit = hits[0]
            source = hit['_source']
            
            # Create Pre-signed URL (handle both image_uri and file_uri)
            page_uri = source.get('image_uri', '')
            file_uri = source.get('file_uri', '')   
            
            # Extract analysis results by tool
            tools = source.get('tools', {})
            analysis_results = []
            
            # BDA Indexer results
            for tool in tools.get('bda_indexer', []):
                analysis_results.append({
                    "content": tool.get('content', ''),
                    "tool_name": "bda_indexer",
                    "analysis_query": tool.get('analysis_query', ''),
                    "created_at": tool.get('created_at', ''),
                    "seq": 0,
                    "execution_time": None,
                    "vector_dimensions": None,
                    "data_structure": "bda_analysis"
                })
            
            # PDF Text Extractor results
            for tool in tools.get('pdf_text_extractor', []):
                analysis_results.append({
                    "content": tool.get('content', ''),
                    "tool_name": "pdf_text_extractor",
                    "analysis_query": tool.get('analysis_query', ''),
                    "created_at": tool.get('created_at', ''),
                    "seq": 0,
                    "execution_time": None,
                    "vector_dimensions": None,
                    "data_structure": "text_extraction"
                })
            
            # AI Analysis results (images, videos, etc.)
            for tool in tools.get('ai_analysis', []):
                analysis_results.append({
                    "content": tool.get('content', ''),
                    "tool_name": "ai_analysis",
                    "analysis_query": tool.get('analysis_query', ''),
                    "created_at": tool.get('created_at', ''),
                    "seq": 0,
                    "execution_time": None,
                    "vector_dimensions": None,
                    "data_structure": "ai_analysis",
                    "metadata": tool.get('metadata', {})
                })
            
            logger.info(f"Found {len(analysis_results)} analysis results in OpenSearch")
            
        except Exception as e:
            logger.error(f"OpenSearch lookup failed: {str(e)}")
            return create_internal_error_response(f"OpenSearch lookup failed: {str(e)}")
        
        # Construct response data
        response_data = {
            "index_id": index_id,
            "document_id": document_id,
            "segment_id": segment_id,
            "total_analysis_results": len(analysis_results),
            "analysis_results": analysis_results,
            "file_uri": file_uri,
            "image_file_uri": page_uri
        }
        
        logger.info(f"Segment detail lookup complete: {len(analysis_results)} analysis results")
        
        return create_success_response(response_data)
        
    except Exception as e:
        logger.error(f"Segment detail lookup error: {str(e)}")
        return handle_lambda_error(e)


def handle_get_segment_image(event: Dict[str, Any]) -> Dict[str, Any]:
    """Get segment image as base64 by segment_id from DynamoDB Segments table
    
    Path: GET /api/segments/{segment_id}/image
    Query: index_id (optional), document_id (optional)
    Returns: { success, data: { image_data, mime_type, image_uri, document_id, segment_id } }
    """
    try:
        from common.dynamodb_service import DynamoDBService  # Provided via Lambda layer
        s3 = _get_s3_service()

        path_parameters = event.get('pathParameters') or {}
        query_params = event.get('queryStringParameters') or {}

        segment_id = path_parameters.get('segment_id')
        if not segment_id:
            return create_validation_error_response("segment_id is required")

        # Fetch segment from DynamoDB
        db = DynamoDBService()
        segment_item = db.get_item('segments', { 'segment_id': segment_id })
        if not segment_item:
            return create_not_found_response(f"Segment not found: segment_id={segment_id}")

        image_uri = segment_item.get('image_uri', '') or ''
        document_id = segment_item.get('document_id', '')

        if not image_uri:
            return create_not_found_response(f"image_uri not found for segment_id={segment_id}")

        # Resolve bucket/key from S3 URI or direct key
        bucket_name_env = os.environ.get('DOCUMENTS_BUCKET_NAME')
        s3_bucket = None
        s3_key = None
        if image_uri.startswith('s3://'):
            parts = image_uri.replace('s3://', '').split('/', 1)
            if len(parts) == 2:
                s3_bucket, s3_key = parts[0], parts[1]
        else:
            # Fallback to environment bucket when only key is stored
            s3_bucket = bucket_name_env
            s3_key = image_uri

        if not s3_bucket or not s3_key:
            return create_internal_error_response("Failed to resolve S3 bucket/key from image_uri")

        # Create presigned URL instead of returning base64 payload
        try:
            image_presigned_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': s3_bucket, 'Key': s3_key},
                ExpiresIn=600
            )
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: s3://{s3_bucket}/{s3_key} - {str(e)}")
            image_presigned_url = None

        # Guess MIME type from key
        mime_type, _ = mimetypes.guess_type(s3_key)
        mime_type = mime_type or 'image/png'

        response_data = {
            'segment_id': segment_id,
            'document_id': document_id,
            'image_uri': image_uri,
            'mime_type': mime_type,
            'image_presigned_url': image_presigned_url,
        }

        return create_success_response(response_data)

    except Exception as e:
        logger.error(f"Segment image retrieval error: {str(e)}")
        return handle_lambda_error(e)
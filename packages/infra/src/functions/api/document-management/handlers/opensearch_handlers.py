"""
OpenSearch Management Handler Module
Functions for managing OpenSearch index and search APIs
"""

import os
import sys
import json
import logging
import boto3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Lambda Layer imports
from common import (
    OpenSearchService,
    S3Service,
    get_current_timestamp,
)
from common.aws_clients import AWSClientFactory

# Add parent directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.response import (
    create_success_response as create_response_success,
    create_validation_error_response,
    create_not_found_response,
    create_internal_error_response,
    create_bad_request_response
)

logger = logging.getLogger(__name__)

# Environment variables
OPENSEARCH_ENDPOINT = os.environ.get('OPENSEARCH_ENDPOINT')
OPENSEARCH_INDEX_NAME = os.environ.get('OPENSEARCH_INDEX_NAME', 'aws-idp-ai-analysis')
DOCUMENTS_BUCKET_NAME = os.environ.get('DOCUMENTS_BUCKET_NAME')
SEGMENTS_TABLE_NAME = os.environ.get('SEGMENTS_TABLE_NAME')

# Search related environment variables (performance optimization)
HYBRID_SEARCH_SIZE = int(os.environ.get('HYBRID_SEARCH_SIZE', '15'))  # Decreased from 25 to 15
RERANK_TOP_N = int(os.environ.get('RERANK_TOP_N', '5'))  # Increased from 3 to 5
MAX_SEARCH_SIZE = int(os.environ.get('MAX_SEARCH_SIZE', '50'))  # Decreased from 100 to 50
RERANK_MODEL_ID = os.environ.get('RERANK_MODEL_ID', 'cohere.rerank-v3-5:0')
RERANK_SCORE_THRESHOLD = float(os.environ.get('RERANK_SCORE_THRESHOLD', '0.05'))  # Decreased from 0.07 to 0.05

# Common service initialization
opensearch_service = None
s3_service = None

def _get_opensearch_service():
    """Initialize OpenSearch service as singleton pattern"""
    global opensearch_service
    if opensearch_service is None:
        if not OPENSEARCH_ENDPOINT:
            raise ValueError("OPENSEARCH_ENDPOINT environment variable is not set")
        opensearch_service = OpenSearchService(
            endpoint=OPENSEARCH_ENDPOINT,
            index_name=OPENSEARCH_INDEX_NAME
        )
    return opensearch_service

def _get_s3_service():
    """Initialize S3 service as singleton pattern"""
    global s3_service
    if s3_service is None:
        s3_service = S3Service()
    return s3_service

def _get_segment_info_from_dynamodb(segment_id: str) -> Dict[str, Optional[str]]:
    """Get segment info including timecodes and status from DynamoDB segments table. Return empty strings if not found."""
    try:
        # Resolve table name via factory (consistent with s3_service usage)
        try:
            table_name = AWSClientFactory.get_table_name('segments')
        except Exception as e:
            logger.warning(f"Failed to resolve segments table via factory: {str(e)}; falling back to env")
            table_name = SEGMENTS_TABLE_NAME

        if not table_name:
            logger.warning("Segments table name not configured")
            return {"start_timecode_smpte": "", "end_timecode_smpte": "", "status": ""}

        dynamodb = AWSClientFactory.get_dynamodb_resource()
        table = dynamodb.Table(table_name)
        response = table.get_item(Key={'segment_id': segment_id})
        item = response.get('Item', {})
        return {
            "start_timecode_smpte": item.get('start_timecode_smpte', ""),
            "end_timecode_smpte": item.get('end_timecode_smpte', ""),
            "status": item.get('status', ""),
        }
    except Exception as e:
        logger.error(f"Failed to get segment info from DynamoDB for segment_id={segment_id}: {str(e)}")
        return {"start_timecode_smpte": "", "end_timecode_smpte": "", "status": ""}

def _get_index_info_from_dynamodb(index_id: str) -> Optional[Dict[str, Any]]:
    """Get index information from DynamoDB indices table"""
    try:
        indices_table_name = os.environ.get('INDICES_TABLE_NAME')
        if not indices_table_name:
            logger.warning("INDICES_TABLE_NAME environment variable not set")
            return None
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(indices_table_name)
        
        # Get item from DynamoDB
        response = table.get_item(
            Key={'index_id': index_id}
        )
        
        if 'Item' in response:
            return response['Item']
        else:
            logger.warning(f"Index not found in DynamoDB: {index_id}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to get index info from DynamoDB: {str(e)}")
        return None

def _get_document_file_name_from_dynamodb(document_id: str) -> Optional[str]:
    """Get document file_name from DynamoDB documents table"""
    try:
        table_name = AWSClientFactory.get_table_name('documents')
        dynamodb = AWSClientFactory.get_dynamodb_resource()
        table = dynamodb.Table(table_name)
        response = table.get_item(Key={'document_id': document_id})
        item = response.get('Item', {})
        return item.get('file_name') if item else None
    except Exception as e:
        logger.warning(f"Failed to get file_name from DynamoDB for document_id={document_id}: {str(e)}")
        return None

def handle_opensearch_status(event: Dict[str, Any]) -> Dict[str, Any]:
    """Check OpenSearch cluster status and specific index status - GET /api/opensearch/status
    
    Query Parameters:
    - index_id: Specific index ID to check (optional)
    """
    try:
        # Get query parameters
        query_params = event.get('queryStringParameters') or {}
        index_id = query_params.get('index_id')
        
        logger.info(f"🔍 Checking OpenSearch status (index_id={index_id})")
        
        opensearch = _get_opensearch_service()
        
        # Check cluster status
        health = opensearch.client.cluster.health()
        stats = opensearch.client.cluster.stats()
        
        status_data = {
            "cluster_name": health.get('cluster_name'),
            "status": health.get('status'),
            "number_of_nodes": health.get('number_of_nodes'),
            "number_of_data_nodes": health.get('number_of_data_nodes'),
            "active_primary_shards": health.get('active_primary_shards'),
            "active_shards": health.get('active_shards'),
            "relocating_shards": health.get('relocating_shards'),
            "initializing_shards": health.get('initializing_shards'),
            "unassigned_shards": health.get('unassigned_shards'),
            "number_of_pending_tasks": health.get('number_of_pending_tasks'),
            "timestamp": get_current_timestamp()
        }
        
        # If index_id is provided, get specific index information
        if index_id:
            # Get index information from DynamoDB indices table
            index_info = _get_index_info_from_dynamodb(index_id)
            if not index_info:
                return create_not_found_response(f"Index ID '{index_id}' not found in indices table")
            
            index_name = index_info.get('index_name')
            if not index_name:
                return create_validation_error_response(f"Index name not found for index_id: {index_id}")
            
            # Check if the specific index exists in OpenSearch
            index_exists = opensearch.client.indices.exists(index=index_name)
            
            # Get document count for the specific index
            total_documents = 0
            if index_exists:
                try:
                    count_response = opensearch.client.count(index=index_name)
                    total_documents = count_response.get('count', 0)
                except Exception as count_error:
                    logger.warning(f"Failed to get document count for index {index_name}: {count_error}")
            
            # Add index-specific information
            status_data.update({
                "index_id": index_id,
                "index_name": index_name,
                "index_exists": index_exists,
                "total_documents": total_documents,
                "index_metadata": {
                    "created_at": index_info.get('created_at'),
                    "project_id": index_info.get('project_id'),
                    "description": index_info.get('description'),
                    "status": index_info.get('status')
                }
            })
        else:
            # Default behavior - check default index
            index_exists = opensearch.client.indices.exists(index=OPENSEARCH_INDEX_NAME)
            status_data.update({
                "default_index_name": OPENSEARCH_INDEX_NAME,
                "default_index_exists": index_exists,
                "default_total_documents": opensearch.get_document_count() if index_exists else 0
            })
        
        logger.info(f"✅ OpenSearch status check complete: {health.get('status')}")
        return create_response_success(status_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to check OpenSearch status: {str(e)}")
        return create_internal_error_response(f"Failed to check OpenSearch status: {str(e)}")

def handle_create_index(event: Dict[str, Any]) -> Dict[str, Any]:
    """Create index - POST /api/opensearch/indices/{index_name}/create"""
    try:
        path_params = event.get('pathParameters', {})
        index_name = path_params.get('index_name')
        
        if not index_name:
            return create_validation_error_response("index_name is required")
        
        logger.info(f"🔨 Starting index creation: {index_name}")
        
        opensearch = _get_opensearch_service()
        
        # Check if index already exists
        if opensearch.client.indices.exists(index=index_name):
            return create_bad_request_response(f"Index '{index_name}' already exists")
        
        # Create index (with correct mapping)
        opensearch._create_index()
        
        result_data = {
            "index_name": index_name,
            "created": True,
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ Index creation complete: {index_name}")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to create index: {str(e)}")
        return create_internal_error_response(f"Failed to create index: {str(e)}")

def handle_delete_index(event: Dict[str, Any]) -> Dict[str, Any]:
    """Delete index - DELETE /api/opensearch/indices/{index_name}"""
    try:
        path_params = event.get('pathParameters', {})
        index_name = path_params.get('index_name')
        
        if not index_name:
            return create_validation_error_response("index_name is required")
        
        logger.info(f"🗑️ Starting index deletion: {index_name}")
        
        opensearch = _get_opensearch_service()
        
        # Check if index exists
        if not opensearch.client.indices.exists(index=index_name):
            return create_not_found_response(f"Index '{index_name}' not found")
        
        # Delete index
        opensearch.client.indices.delete(index=index_name)
        
        result_data = {
            "index_name": index_name,
            "deleted": True,
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ Index deletion complete: {index_name}")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to delete index: {str(e)}")
        return create_internal_error_response(f"Failed to delete index: {str(e)}")

def handle_recreate_index(event: Dict[str, Any]) -> Dict[str, Any]:
    """Recreate index - POST /api/opensearch/indices/recreate?index_id=my-index"""
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        index_id = query_params.get('index_id')
        
        if not index_id:  
            return create_validation_error_response("index_id is required")
        
        logger.info(f"🔄 Starting index recreation: {index_id}")
        
        opensearch = _get_opensearch_service()
        
        # Delete existing index (if it exists)
        if opensearch.client.indices.exists(index=index_id):
            opensearch.client.indices.delete(index=index_id)
            logger.info(f"Deleted existing index: {index_id}")
        
        # Create new index (with correct mapping)
        opensearch._create_index(index_id)
        
        result_data = {
            "index_id": index_id,
            "recreated": True,
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ Index recreation complete: {index_id}")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to recreate index: {str(e)}")
        return create_internal_error_response(f"Failed to recreate index: {str(e)}")

def handle_get_opensearch_documents(event: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve OpenSearch documents by document ID - GET /api/opensearch/documents/{document_id}

    Query Parameters:
    - size: Page size (default: 5000 for metadata_only, 100 for full data, max: 5000 for metadata_only, 1000 for full data)
    - filter_final: 'true' to filter only final_ai_response (default: 'false')
    - metadata_only: 'true' to return only metadata without content (default: 'false')
    """
    try:
        path_params = event.get('pathParameters', {})
        query_params = event.get('queryStringParameters') or {}
        
        # Accept index_id from either path or query string for compatibility
        index_id = path_params.get('index_id') or query_params.get('index_id')
        document_id = path_params.get('document_id') or query_params.get('document_id')
        
        if not index_id:
            return create_validation_error_response("index_id is required")
        
        if not document_id:
            return create_validation_error_response("document_id is required")
        
        # Check filtering options
        filter_final_only = query_params.get('filter_final', 'false').lower() == 'true'
        metadata_only = query_params.get('metadata_only', 'false').lower() == 'true'

        logger.info(f"🔍 Starting OpenSearch document retrieval: document_id={document_id}, filter_final={filter_final_only}, metadata_only={metadata_only}")
        
        opensearch = _get_opensearch_service()
        s3 = _get_s3_service()
        
        # Set page size - increase default and limit for metadata-only requests
        default_size = 5000 if metadata_only else 100
        max_size = 5000 if metadata_only else 1000
        size = min(int(query_params.get('size', default_size)), max_size)
        
        # Construct direct search query (ensure filters are applied correctly)
        search_body = {
            "size": size,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"document_id": document_id}}
                    ]
                }
            },
            "sort": [{"segment_index": {"order": "asc"}}]
        }

        # For metadata-only requests, exclude heavy content fields
        if metadata_only:
            search_body["_source"] = {
                "excludes": [
                    "tools.bda_indexer.content",
                    "tools.pdf_text_extractor.content",
                    "tools.ai_analysis.content",
                    "tools.user_content.content",
                    "content_combined",
                    "vector_content"
                ]
            }
        
        logger.info(f"🔍 Search query: {search_body}")
        
        # Execute direct OpenSearch search
        response = opensearch.client.search(
            index=index_id,
            body=search_body
        )
        
        # Parse results (new page-unit structure)
        segments = []
        hits = response.get('hits', {}).get('hits', [])
        
        for hit in hits:
            source = hit['_source']
            
            # Return pure S3 URIs (remove Pre-signed URL generation)
            image_uri = source.get('image_uri', '')
            file_uri = source.get('file_uri', '')
            
            logger.info(f"Returning S3 URIs: image_uri={image_uri}, file_uri={file_uri}")
            
            # Process content by tool type (based on filtering option)
            tools = source.get('tools', {})

            # If metadata_only is requested, return minimal tool information
            if metadata_only:
                tools_detail = {
                    "bda_indexer": [{"analysis_query": tool.get('analysis_query', ''), "created_at": tool.get('created_at', '')} for tool in tools.get('bda_indexer', [])],
                    "pdf_text_extractor": [{"analysis_query": tool.get('analysis_query', ''), "created_at": tool.get('created_at', '')} for tool in tools.get('pdf_text_extractor', [])],
                    "ai_analysis": [{"analysis_query": tool.get('analysis_query', ''), "metadata": tool.get('metadata', {}), "created_at": tool.get('created_at', '')} for tool in tools.get('ai_analysis', [])],
                    "user_content": [{"analysis_query": tool.get('analysis_query', ''), "created_at": tool.get('created_at', '')} for tool in tools.get('user_content', [])]
                }
            elif filter_final_only:
                # Filter and return only final_ai_response (optimized data size)
                final_ai_responses = [
                    {
                        "content": tool.get('content', ''),
                        "analysis_query": tool.get('analysis_query', ''),
                        "metadata": tool.get('metadata', {}),
                        "created_at": tool.get('created_at', '')
                    } for tool in tools.get('ai_analysis', [])
                    if tool.get('metadata', {}).get('analysis_steps') == 'final_ai_response'
                ]
                
                tools_detail = {
                    "final_ai_response": final_ai_responses,
                    # Set other tools to empty arrays for optimized size
                    "bda_indexer": [],
                    "pdf_text_extractor": [],
                    "ai_analysis": [],
                    "user_content": []
                }
            else:
                # Return all tool data (existing method)
                tools_detail = {
                    "bda_indexer": [
                        {
                            "content": tool.get('content', ''),
                            "analysis_query": tool.get('analysis_query', ''),
                            "created_at": tool.get('created_at', '')
                        } for tool in tools.get('bda_indexer', [])
                    ],
                    "pdf_text_extractor": [
                        {
                            "content": tool.get('content', ''),
                            "analysis_query": tool.get('analysis_query', ''),
                            "created_at": tool.get('created_at', '')
                        } for tool in tools.get('pdf_text_extractor', [])
                    ],
                    "ai_analysis": [
                        {
                            "content": tool.get('content', ''),
                            "analysis_query": tool.get('analysis_query', ''),
                            "metadata": tool.get('metadata', {}),
                            "created_at": tool.get('created_at', '')
                        } for tool in tools.get('ai_analysis', [])
                    ],
                    "user_content": [
                        {
                            "content": tool.get('content', ''),
                            "analysis_query": tool.get('analysis_query', ''),
                            "created_at": tool.get('created_at', '')
                        } for tool in tools.get('user_content', [])
                    ]
                }
            
            # Fetch segment info (timecodes and status) from DynamoDB
            segment_id_val = source.get('segment_id', '')
            segment_info = _get_segment_info_from_dynamodb(segment_id_val) if segment_id_val else {"start_timecode_smpte": "", "end_timecode_smpte": "", "status": ""}

            segment_item = {
                "segment_id": source.get('segment_id', ''),
                "segment_index": source.get('segment_index', 0),
                "index_id": index_id,
                "document_id": source.get('document_id', ''),
                "image_uri": image_uri,
                "file_uri": file_uri,
                "start_timecode_smpte": segment_info.get('start_timecode_smpte', ""),
                "end_timecode_smpte": segment_info.get('end_timecode_smpte', ""),
                "status": segment_info.get('status', ""),
                "vector_content_available": bool(source.get('vector_content')),
                "tools_detail": tools_detail,
                "tools_count": {
                    "final_ai_response": len(tools_detail.get('final_ai_response', [])) if filter_final_only else 0,
                    "bda_indexer": len(tools_detail['bda_indexer']),
                    "pdf_text_extractor": len(tools_detail['pdf_text_extractor']),
                    "ai_analysis": len(tools_detail['ai_analysis']),
                    "user_content": len(tools_detail['user_content'])
                },
                "created_at": source.get('created_at', ''),
                "updated_at": source.get('updated_at', ''),
            }
            
            segments.append(segment_item)
        
        # Construct result data
        total_hits = response.get('hits', {}).get('total', {})
        if isinstance(total_hits, dict):
            total_count = total_hits.get('value', 0)
        else:
            total_count = total_hits
        
        result_data = {
            "document_id": document_id,
            "total_segments": total_count,
            "returned_segments": len(segments),
            "segments": segments,
            "query_params": {
                "size": size
            },
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ OpenSearch segment retrieval complete: {document_id} ({len(segments)} segments)")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to retrieve OpenSearch documents: {str(e)}")
        return create_internal_error_response(f"Failed to retrieve OpenSearch documents: {str(e)}")

def handle_get_opensearch_document_segment(event: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve a specific OpenSearch segment by project, document ID, and segment index - GET /api/opensearch/projects/{project_id}/documents/{document_id}/segments/{segment_index}
    
    Query Parameters:
    - filter_final: 'true' to filter only final_ai_response (default: 'false')
    """
    try:
        path_params = event.get('pathParameters', {})
        query_params = event.get('queryStringParameters') or {}
        
        index_id = path_params.get('index_id')
        document_id = path_params.get('document_id')
        segment_id = path_params.get('segment_id')
        
        if not index_id:
            return create_validation_error_response("index_id is required")
        if not document_id:
            return create_validation_error_response("document_id is required")
        if segment_id is None:
            return create_validation_error_response("segment_id is required")
        
        # Convert segment_index to integer
        try:
            segment_id = int(segment_id)
            if segment_id < 0:
                return create_validation_error_response("segment_id must be non-negative")
        except ValueError:
            return create_validation_error_response("segment_id must be a valid string")
        
        # Check filtering options
        filter_final_only = query_params.get('filter_final', 'false').lower() == 'true'
        
        logger.info(f"🔍 Starting specific OpenSearch segment retrieval: index_id={index_id}, document_id={document_id}, segment_id={segment_id}, filter_final={filter_final_only}")
        
        opensearch = _get_opensearch_service()
        s3 = _get_s3_service()
        
        # Construct query to search for a specific page
        search_body = {
            "size": 1,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"index_id": index_id}},
                        {"term": {"document_id": document_id}},
                        {"term": {"segment_id": segment_id}}
                    ]
                }
            }
        }
        
        logger.info(f"🔍 Search query: {search_body}")
        
        # Execute direct OpenSearch search
        response = opensearch.client.search(
            index=index_id,
            body=search_body
        )
        
        # Parse results
        hits = response.get('hits', {}).get('hits', [])
        
        if not hits:
            return create_not_found_response(f"Segment not found: index_id={index_id}, document_id={document_id}, segment_index={segment_index}")
        
        hit = hits[0]
        source = hit['_source']
        
        # Generate presigned URLs for image_uri and file_uri (following handle_opensearch_hybrid_search pattern)
        image_uri = source.get('image_uri', '')
        file_uri = source.get('file_uri', '')
        
        # Return pure S3 URIs (remove Pre-signed URL generation)
        logger.info(f"Returning specific segment S3 URIs: image_uri={image_uri}, file_uri={file_uri}")
        
        # Process content by tool type (based on filtering option)
        tools = source.get('tools', {})
        
        if filter_final_only:
            # Filter and return only final_ai_response (optimized data size)
            final_ai_responses = [
                {
                    "content": tool.get('content', ''),
                    "analysis_query": tool.get('analysis_query', ''),
                    "metadata": tool.get('metadata', {}),
                    "created_at": tool.get('created_at', '')
                } for tool in tools.get('ai_analysis', [])
                if tool.get('metadata', {}).get('analysis_steps') == 'final_ai_response'
            ]
            
            tools_detail = {
                "final_ai_response": final_ai_responses,
                # Set other tools to empty arrays for optimized size
                "bda_indexer": [],
                "pdf_text_extractor": [],
                "ai_analysis": [],
                "user_content": []
            }
        else:
            # Return all tool data (existing method)
            tools_detail = {
                "bda_indexer": [
                    {
                        "content": tool.get('content', ''),
                        "analysis_query": tool.get('analysis_query', ''),
                        "created_at": tool.get('created_at', '')
                    } for tool in tools.get('bda_indexer', [])
                ],
                "pdf_text_extractor": [
                    {
                        "content": tool.get('content', ''),
                        "analysis_query": tool.get('analysis_query', ''),
                        "created_at": tool.get('created_at', '')
                    } for tool in tools.get('pdf_text_extractor', [])
                ],
                "ai_analysis": [
                    {
                        "content": tool.get('content', ''),
                        "analysis_query": tool.get('analysis_query', ''),
                        "metadata": tool.get('metadata', {}),
                        "created_at": tool.get('created_at', '')
                    } for tool in tools.get('ai_analysis', [])
                ],
                "user_content": [
                    {
                        "content": tool.get('content', ''),
                        "analysis_query": tool.get('analysis_query', ''),
                        "created_at": tool.get('created_at', '')
                    } for tool in tools.get('user_content', [])
                ]
            }
        
        segment_data = {
            "segment_id": source.get('segment_id', ''),
            "segment_index": source.get('segment_index', 0),
            "index_id": source.get('index_id', ''),
            "document_id": source.get('document_id', ''),
            "image_uri": image_uri,
            "file_uri": file_uri,
            "vector_content_available": bool(source.get('vector_content')),
            "tools_detail": tools_detail,
            "tools_count": {
                "final_ai_response": len(tools_detail.get('final_ai_response', [])) if filter_final_only else 0,
                "bda_indexer": len(tools_detail['bda_indexer']),
                "pdf_text_extractor": len(tools_detail['pdf_text_extractor']),
                "ai_analysis": len(tools_detail['ai_analysis']),
                "user_content": len(tools_detail['user_content'])
            },
            "created_at": source.get('created_at', ''),
            "updated_at": source.get('updated_at', ''),
        }
        
        # Construct result data
        result_data = {
            "index_id": index_id,
            "document_id": document_id,
            "segment_id": segment_id,
            "segment": segment_data,
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ Specific OpenSearch segment retrieval complete: {index_id}/{document_id}/segment-{segment_index}")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to retrieve specific OpenSearch segment: {str(e)}")
        return create_internal_error_response(f"Failed to retrieve specific OpenSearch segment: {str(e)}")

def handle_opensearch_hybrid_search(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hybrid search with Cohere Rerank - POST /api/opensearch/search/hybrid
    
    After executing OpenSearch hybrid search, reorder the results using Cohere Rerank.
    Search parameters are loaded from TOML settings and environment variables.
    
    Environment Variables:
    - HYBRID_SEARCH_SIZE: Initial number of candidates to fetch from OpenSearch (default: 25)
    - RERANK_TOP_N: Final number of results to return after reranking (default: 3)
    - MAX_SEARCH_SIZE: Maximum number of searchable documents (default: 100)
    - RERANK_MODEL_ID: Cohere Rerank model ID (default: cohere.rerank-v3-5:0)
    """
    try:
        body = event.get('body')
        if not body:
            return create_validation_error_response("Request body is missing")
        
        if isinstance(body, str):
            data = json.loads(body)
        else:
            data = body
        
        query = data.get('query')
        if not query:
            return create_validation_error_response("Query (query) is required")
        
        # Search size: use value from environment variables, with max value limit
        size = min(data.get('size', HYBRID_SEARCH_SIZE), MAX_SEARCH_SIZE)
        text_weight = data.get('text_weight', 0.4)
        vector_weight = data.get('vector_weight', 0.6)
        index_id = data.get('index_id')
        document_id = data.get('document_id')
        
        logger.info(f"🔍 Starting hybrid search: query={query[:50]}... (index_id={index_id}, document_id={document_id})")
        
        opensearch = _get_opensearch_service()
        
        # Set filters
        filters = {}
        if document_id:
            filters['document_id'] = document_id
        
        # Execute hybrid search
        response = opensearch.hybrid_search(
            index_id=index_id,
            query=query,
            size=size,
            text_weight=text_weight,
            vector_weight=vector_weight,
            filters=filters
        )
        
        # Parse results
        search_results = []
        hits = response.get('hits', {}).get('hits', [])
        
        for hit in hits:
            source = hit['_source']
            
            # Extract highlight information (trust OpenSearch results)
            highlight_info = hit.get('highlight', {})
            tools = source.get('tools', {})
            
            # Trust OpenSearch's relevance determination and include all tool information
            # Do not re-filter by simple keyword matching (prevents performance degradation)
            matched_tools = []
            for tool_type in ['bda_indexer', 'pdf_text_extractor', 'ai_analysis']:
                tool_items = tools.get(tool_type, [])
                for i, tool_item in enumerate(tool_items):
                    content = tool_item.get('content', '')
                    if content:  # Include if content exists (no keyword matching condition)
                        matched_tools.append({
                            "tool_type": tool_type,
                            "tool_index": i,
                            "content_preview": content[:300] + "..." if len(content) > 300 else content,
                            "analysis_query": tool_item.get('analysis_query', ''),
                            "metadata": tool_item.get('metadata', {}),
                            "created_at": tool_item.get('created_at', '')
                        })
            
            image_uri = source.get('image_uri', '')
            file_uri = source.get('file_uri', '')
            
            logger.info(f"Returning hybrid search S3 URIs: image_uri={image_uri}, file_uri={file_uri}")

            # Fetch file_name from documents table
            doc_id_for_name = source.get('document_id', '')
            file_name = _get_document_file_name_from_dynamodb(doc_id_for_name) if doc_id_for_name else None

            result_item = {
                "segment_id": source.get('segment_id', ''),
                "segment_index": source.get('segment_index', 0),
                "document_id": source.get('document_id', ''),
                "image_uri": image_uri,
                "file_uri": file_uri,
                "file_name": file_name,
                "content_combined": source.get('content_combined', ''),
                "matched_tools": matched_tools,
                "tools_count": {
                    "bda_indexer": len(tools.get('bda_indexer', [])),
                    "pdf_text_extractor": len(tools.get('pdf_text_extractor', [])),
                    "ai_analysis": len(tools.get('ai_analysis', [])),
                    "user_content": len(tools.get('user_content', []))
                },
                "created_at": source.get('created_at', ''),
                "updated_at": source.get('updated_at', ''),
                "_score": hit['_score'],
                "_id": hit['_id']
            }
            
            # Add highlight
            if highlight_info:
                result_item['highlight'] = highlight_info
            
            search_results.append(result_item)
        
        # Apply Cohere Rerank (only if more than 1 result to filter out useless results)
        if search_results and len(search_results) >= 1:
            try:
                logger.info(f"🔄 Starting Cohere Rerank: {len(search_results)} documents → reranking to {RERANK_TOP_N} results")
                
                # Initialize Bedrock Runtime client
                bedrock_runtime = boto3.client('bedrock-runtime')
                
                # Extract document text for reranking (improved approach)
                documents = []
                for i, result in enumerate(search_results):
                    # Use the content_combined field that OpenSearch determined as most relevant
                    document_text = result.get('content_combined', '').strip()
                    
                    # Apply fallback logic only if content_combined is empty
                    if not document_text:
                        # Combine content from tools to generate fallback text
                        content_parts = []
                        for tool in result.get('matched_tools', []):
                            content_preview = tool.get('content_preview', '').strip()
                            if content_preview:
                                content_parts.append(content_preview)
                        
                        if content_parts:
                            document_text = ' '.join(content_parts)
                        else:
                            document_text = f"Segment {result.get('segment_index', 0)} - No content"
                    
                    # Use the full content_combined field as is (user requirement)
                    # Perform accurate reranking with the full document content
                    final_text = document_text
                    documents.append(final_text)
                    
                    # Add log for debugging (confirming full content_combined usage)
                    logger.info(f"�� Rerank document {i+1}: content_combined length={len(result.get('content_combined', '')),}, full text sent length={len(final_text)} (no truncation)")
                    logger.debug(f"📄 Rerank document {i+1} content preview: {final_text[:100]}...")
                
                logger.info(f"🔄 Cohere Rerank request - Question: '{query[:100]}...', Number of documents: {len(documents)}")
                
                # Construct Cohere Rerank request payload
                rerank_payload = {
                    "api_version": 2,
                    "query": query,
                    "documents": documents,
                    "top_n": min(RERANK_TOP_N, len(documents))
                }
                
                # Call Cohere Rerank via Bedrock
                response_rerank = bedrock_runtime.invoke_model(
                    modelId=RERANK_MODEL_ID,
                    body=json.dumps(rerank_payload),
                    contentType='application/json'
                )
                
                # Parse reranking results
                rerank_result = json.loads(response_rerank['body'].read().decode('utf-8'))
                results_ranked = rerank_result.get('results', [])
                
                # Reorder search results based on reranking (including score filtering)
                reranked_search_results = []
                filtered_count = 0
                
                for rank_item in results_ranked:
                    original_index = rank_item.get('index')
                    relevance_score = rank_item.get('relevance_score', 0.0)
                    
                    # Filter by score threshold (include only those above the threshold)
                    if relevance_score < RERANK_SCORE_THRESHOLD:
                        filtered_count += 1
                        continue
                    
                    if 0 <= original_index < len(search_results):
                        result_item = search_results[original_index].copy()
                        result_item['_rerank_score'] = relevance_score
                        result_item['_rerank_position'] = len(reranked_search_results) + 1
                        reranked_search_results.append(result_item)
                
                # Replace with reranked results
                search_results = reranked_search_results
                logger.info(f"✅ Cohere Rerank complete: reordered {len(search_results)} results (filtered {filtered_count} excluded)")
                
            except Exception as e:
                logger.warning(f"⚠️ Cohere Rerank failed, using original results: {str(e)}")
                # If reranking fails, keep original results and continue
        
        # Construct result data
        total_hits = response.get('hits', {}).get('total', {})
        if isinstance(total_hits, dict):
            total_count = total_hits.get('value', 0)
        else:
            total_count = total_hits
        
        result_data = {
            "query": query,
            "search_type": "hybrid_with_rerank",
            "total_results": total_count,
            "returned_results": len(search_results),
            "text_weight": text_weight,
            "vector_weight": vector_weight,
            "rerank_model": RERANK_MODEL_ID,
            "rerank_top_n": RERANK_TOP_N,
            "rerank_score_threshold": RERANK_SCORE_THRESHOLD,
            "results": search_results,
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ Hybrid search + reranking complete: {len(search_results)} results")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to execute hybrid search: {str(e)}")
        return create_internal_error_response(f"Failed to execute hybrid search: {str(e)}")

def handle_opensearch_vector_search(event: Dict[str, Any]) -> Dict[str, Any]:
    """Vector search - POST /api/opensearch/search/vector"""
    try:
        body = event.get('body')
        if not body:
            return create_validation_error_response("Request body is missing")
        
        if isinstance(body, str):
            data = json.loads(body)
        else:
            data = body
        
        query = data.get('query')
        if not query:
            return create_validation_error_response("Query (query) is required")
        
        size = min(data.get('size', 10), 100)
        project_id = data.get('project_id')
        document_id = data.get('document_id')
        
        logger.info(f"🔍 Starting vector search: query={query[:50]}... (project_id={project_id}, document_id={document_id})")
        
        opensearch = _get_opensearch_service()
        
        # Set filters
        filters = {}
        if project_id:
            filters['project_id'] = project_id
        if document_id:
            filters['document_id'] = document_id
        
        # Execute vector search
        response = opensearch.search_vector(
            query_text=query,
            size=size,
            filters=filters
        )
        
        # Parse results (new page-unit structure - for vector search)
        search_results = []
        hits = response.get('hits', {}).get('hits', [])
        
        for hit in hits:
            source = hit['_source']
            tools = source.get('tools', {})
            
            # Vector search is primarily based on content_combined, so provide full page info
            result_item = {
                "segment_id": source.get('segment_id', ''),
                "segment_index": source.get('segment_index', 0),
                "document_id": source.get('document_id', ''),
                "image_uri": source.get('image_uri', ''),
                "file_uri": source.get('file_uri', ''),
                "content_combined": source.get('content_combined', ''),
                "vector_score": hit['_score'],  # Vector similarity score
                "has_embeddings": bool(source.get('vector_content')),
                "tools_detail": {
                    "bda_indexer": [
                        {
                            "content": tool.get('content', ''),
                            "analysis_query": tool.get('analysis_query', ''),
                            "created_at": tool.get('created_at', '')
                        } for tool in tools.get('bda_indexer', [])
                    ],
                    "pdf_text_extractor": [
                        {
                            "content": tool.get('content', ''),
                            "analysis_query": tool.get('analysis_query', ''),
                            "created_at": tool.get('created_at', '')
                        } for tool in tools.get('pdf_text_extractor', [])
                    ],
                    "ai_analysis": [
                        {
                            "content": tool.get('content', ''),
                            "analysis_query": tool.get('analysis_query', ''),
                            "metadata": tool.get('metadata', {}),
                            "created_at": tool.get('created_at', '')
                        } for tool in tools.get('ai_analysis', [])
                    ],
                    "user_content": [
                        {
                            "content": tool.get('content', ''),
                            "analysis_query": tool.get('analysis_query', ''),
                            "created_at": tool.get('created_at', '')
                        } for tool in tools.get('user_content', [])
                    ]
                },
                "created_at": source.get('created_at', ''),
                "updated_at": source.get('updated_at', ''),
                "_score": hit['_score'],
                "_id": hit['_id']
            }
            search_results.append(result_item)
        
        # Construct result data
        total_hits = response.get('hits', {}).get('total', {})
        if isinstance(total_hits, dict):
            total_count = total_hits.get('value', 0)
        else:
            total_count = total_hits
        
        result_data = {
            "query": query,
            "search_type": "vector",
            "total_results": total_count,
            "returned_results": len(search_results),
            "results": search_results,
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ Vector search complete: {len(search_results)} results")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to execute vector search: {str(e)}")
        return create_internal_error_response(f"Failed to execute vector search: {str(e)}")

def handle_opensearch_keyword_search(event: Dict[str, Any]) -> Dict[str, Any]:
    """Keyword search - POST /api/opensearch/search/keyword"""
    try:
        body = event.get('body')
        if not body:
            return create_validation_error_response("Request body is missing")
        
        if isinstance(body, str):
            data = json.loads(body)
        else:
            data = body
        
        query = data.get('query')
        if not query:
            return create_validation_error_response("Query (query) is required")
        
        size = min(data.get('size', 10), 100)
        project_id = data.get('project_id')
        document_id = data.get('document_id')
        
        logger.info(f"🔍 Starting keyword search: query={query[:50]}... (project_id={project_id}, document_id={document_id})")
        
        opensearch = _get_opensearch_service()
        
        # Set filters
        filters = {}
        if project_id:
            filters['project_id'] = project_id
        if document_id:
            filters['document_id'] = document_id
        
        # Execute text search
        response = opensearch.search_text(
            query=query,
            size=size,
            filters=filters
        )
        
        # Parse results (new page-unit structure - for keyword search)
        search_results = []
        hits = response.get('hits', {}).get('hits', [])
        
        for hit in hits:
            source = hit['_source']
            
            # Find matching content by tool type (keyword search)
            highlight_info = hit.get('highlight', {})
            matched_tools = []
            tools = source.get('tools', {})
            
            # Find content that matches keywords in each tool
            for tool_type in ['bda_indexer', 'pdf_text_extractor', 'ai_analysis']:
                tool_items = tools.get(tool_type, [])
                for i, tool_item in enumerate(tool_items):
                    content = tool_item.get('content', '')
                    analysis_query = tool_item.get('analysis_query', '')
                    
                    # For keyword search, ensure exact match
                    if content and any(term.lower() in content.lower() for term in query.split()):
                        matched_tools.append({
                            "tool_type": tool_type,
                            "tool_index": i,
                            "content_preview": content[:300] + "..." if len(content) > 300 else content,
                            "analysis_query": analysis_query,
                            "metadata": tool_item.get('metadata', {}),
                            "created_at": tool_item.get('created_at', ''),
                            "match_score": len([term for term in query.split() if term.lower() in content.lower()])
                        })
            
            # Sort by match score
            matched_tools.sort(key=lambda x: x.get('match_score', 0), reverse=True)
            
            result_item = {
                "segment_id": source.get('segment_id', ''),
                "segment_index": source.get('segment_index', 0),
                "document_id": source.get('document_id', ''),
                "image_uri": source.get('image_uri', ''),
                "file_uri": source.get('file_uri', ''),
                "content_combined": source.get('content_combined', ''),
                "matched_tools": matched_tools[:5],  # Top 5 only
                "total_matches": len(matched_tools),
                "tools_count": {
                    "bda_indexer": len(tools.get('bda_indexer', [])),
                    "pdf_text_extractor": len(tools.get('pdf_text_extractor', [])),
                    "ai_analysis": len(tools.get('ai_analysis', [])),
                    "user_content": len(tools.get('user_content', []))
                },
                "created_at": source.get('created_at', ''),
                "updated_at": source.get('updated_at', ''),
                "_score": hit['_score'],
                "_id": hit['_id']
            }
            
            # Add highlight
            if highlight_info:
                result_item['highlight'] = highlight_info
            
            search_results.append(result_item)
        
        # Construct result data
        total_hits = response.get('hits', {}).get('total', {})
        if isinstance(total_hits, dict):
            total_count = total_hits.get('value', 0)
        else:
            total_count = total_hits
        
        result_data = {
            "query": query,
            "search_type": "keyword",
            "total_results": total_count,
            "returned_results": len(search_results),
            "results": search_results,
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ Keyword search complete: {len(search_results)} results")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to execute keyword search: {str(e)}")
        return create_internal_error_response(f"Failed to execute keyword search: {str(e)}")

def handle_opensearch_sample_data(event: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve sample OpenSearch data for testing - GET /api/opensearch/data/sample

    Query params:
    - index_id or index: 대상 OpenSearch 인덱스 이름 (미제공 시 기본값 사용)
    """
    try:
        logger.info("🔍 Starting OpenSearch sample data retrieval")
        
        opensearch = _get_opensearch_service()
        qs = event.get('queryStringParameters') or {}
        target_index = qs.get('index_id') or qs.get('index')
        if not target_index:
            return create_bad_request_response("Missing required query parameter: 'index_id'")
        
        # Check if index exists
        if not opensearch.client.indices.exists(index=target_index):
            return create_not_found_response(f"Index '{target_index}' does not exist")
        
        # Retrieve latest 5 documents (handle empty index)
        search_body = {
            "size": 5,
            "query": {"match_all": {}},
            "_source": {
                "includes": ["*"],  # Include all fields
                "excludes": []  # No fields to exclude
            }
        }
        
        # First search without sort to check if documents exist
        try:
            response = opensearch.client.search(index=target_index, body=search_body)
            total_docs = response.get('hits', {}).get('total', {})
            if isinstance(total_docs, dict):
                total_count = total_docs.get('value', 0)
            else:
                total_count = total_docs
            
            # If documents exist, try to sort by created_at field
            if total_count > 0:
                search_body_with_sort = search_body.copy()
                search_body_with_sort["sort"] = [{"created_at": {"order": "desc", "missing": "_last"}}]
                try:
                    response = opensearch.client.search(index=target_index, body=search_body_with_sort)
                except Exception as sort_error:
                    logger.warning(f"Failed to sort by created_at, using default response: {str(sort_error)}")
                    # If sorting fails, use default response
                    pass
        except Exception as search_error:
            logger.warning(f"Error during OpenSearch search: {str(search_error)}")
            response = {"hits": {"hits": [], "total": {"value": 0}}}
        
        # Parse results
        hits = response.get('hits', {}).get('hits', [])
        
        # Analyze structure and data of each document
        sample_data = []
        for hit in hits:
            source = hit.get('_source', {})
            
            doc = {
                "opensearch_doc_id": hit.get('_id'),
                "source": source,
                "index": hit.get('_index'),
                "field_analysis": {
                    "total_fields": len(source.keys()),
                    "field_names": list(source.keys()),
                    "has_content": "content" in source,
                    "has_content_combined": "content_combined" in source,  # New structure
                    "has_tools": "tools" in source,  # New structure
                    "has_analysis_query": "analysis_query" in source,
                    "has_vector_content": "vector_content" in source,
                    "content_length": len(source.get('content', '')) if 'content' in source else 0,
                    "content_combined_length": len(source.get('content_combined', '')) if 'content_combined' in source else 0,
                    "analysis_query_length": len(source.get('analysis_query', '')) if 'analysis_query' in source else 0,
                    "vector_dimensions": len(source.get('vector_content', [])) if isinstance(source.get('vector_content'), list) else 0,
                    "tool_name": source.get('tool_name', 'N/A'),
                    "document_id": source.get('document_id', 'N/A'),
                    "segment_id": source.get('segment_id', 'N/A'),
                    "segment_index": source.get('segment_index', 'N/A'),
                    # New structure analysis
                    "tools_structure": _analyze_tools_structure(source.get('tools', {})) if 'tools' in source else None
                }
            }
            
            sample_data.append(doc)
        
        # Overall statistics
        total_docs = response.get('hits', {}).get('total', {})
        if isinstance(total_docs, dict):
            total_count = total_docs.get('value', 0)
        else:
            total_count = total_docs
        
        # Handle empty index
        if total_count == 0:
            result_data = {
                "index_name": target_index,
                "total_documents": 0,
                "sample_count": 0,
                "sample_documents": [],
                "message": "Index is empty. Please add documents and try again.",
                "query_info": {
                    "query_type": "match_all",
                    "sort_by": "none (empty index)",
                    "max_results": 5
                },
                "timestamp": get_current_timestamp()
            }
        else:
            result_data = {
                "index_name": target_index,
                "total_documents": total_count,
                "sample_count": len(sample_data),
                "sample_documents": sample_data,
                "query_info": {
                    "query_type": "match_all with conditional sort",
                    "sort_by": "created_at desc (if available)",
                    "max_results": 5
                },
                "timestamp": get_current_timestamp()
            }
        
        logger.info(f"✅ Sample data retrieval complete: {len(sample_data)} documents")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to retrieve sample data: {str(e)}")
        return create_internal_error_response(f"Failed to retrieve sample data: {str(e)}")

def handle_add_user_content(event: Dict[str, Any]) -> Dict[str, Any]:
    """Incrementally add user content - POST /api/opensearch/user-content/add
    
    Combine existing content_combined with user input via LLM to generate incremental content,
    and update the embedding with the combined content.
    """
    try:
        body = event.get('body')
        if not body:
            return create_validation_error_response("Request body is missing")
        
        if isinstance(body, str):
            data = json.loads(body)
        else:
            data = body
        
        # Validate required parameters
        required_fields = ['index_id', 'document_id', 'content']
        for field in required_fields:
            if not data.get(field):
                return create_validation_error_response(f"{field} is required")
        
        # segment_index can be 0, so validate separately
        if 'segment_index' not in data or data['segment_index'] is None:
            return create_validation_error_response("segment_index is required")
        
        index_id = data['index_id'] 
        document_id = data['document_id']
        user_content = data['content']
        
        # Safely convert segment_index to integer
        try:
            segment_index = int(data['segment_index'])
        except (ValueError, TypeError):
            return create_validation_error_response("segment_index must be a valid integer")
        
        # Get page_id from segment_index
        segment_id = _get_segment_id_from_index(index_id, document_id, segment_index)
        if not segment_id:
            return create_not_found_response(f"Page not found: index_id={index_id}, document_id={document_id}, segment_index={segment_index}")
        
        logger.info(f"📝 Starting incremental user content addition: segment_id={segment_id} (from segment_index={segment_index}), content_length={len(user_content)}")
        
        # 1. Retrieve existing page information
        existing_page = _get_existing_segment_content(index_id, segment_id)
        if not existing_page:
            return create_not_found_response(f"Page not found: {segment_id}")
        
        existing_content = existing_page.get('content_combined', '')
        
        logger.info(f"Existing content_combined length: {len(existing_content)}")
        
        # 2. Generate incremental content via LLM
        incremental_content = _generate_incremental_content(existing_content, user_content)
        if not incremental_content:
            return create_internal_error_response("Failed to generate incremental content")
        
        logger.info(f"Generated incremental content length: {len(incremental_content)}")
        
        # 3. Add user_content to tools structure
        update_success = _add_user_content_to_tools(index_id, segment_id, user_content, incremental_content)
        if not update_success:
            return create_internal_error_response("Failed to add user content")
        
        # 4. Re-retrieve updated page information to generate new content_combined
        updated_page = _get_existing_segment_content(index_id, segment_id)
        if not updated_page:
            return create_internal_error_response("Failed to retrieve updated page information")
        
        # 5. Combine all content from tools to generate new content_combined
        new_content_combined = _generate_content_combined_from_tools(updated_page.get('tools', {}))
        
        logger.info(f"New content_combined length: {len(new_content_combined)}")
        
        # 6. Update content_combined
        content_update_success = _update_segment_content_combined(index_id, segment_id, new_content_combined)
        if not content_update_success:
            return create_internal_error_response("Failed to update content_combined")
        
        # 7. Regenerate embeddings with new content_combined
        embed_success = _generate_and_update_embeddings(index_id, segment_id, new_content_combined)
        if not embed_success:
            logger.warning(f"Failed to update embeddings: {segment_id}")
        
        result_data = {
            "segment_id": segment_id,
            "index_id": index_id,
            "document_id": document_id,
            "segment_index": segment_index,
            "user_input": user_content,
            "user_input_length": len(user_content),
            "generated_content_length": len(incremental_content),
            "existing_content_length": len(existing_content),
            "new_content_combined_length": len(new_content_combined),
            "user_content_added_to_tools": True,
            "content_combined_updated": True,
            "embeddings_updated": embed_success,
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ Incremental user content addition complete: segment_id={segment_id}")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to add incremental user content: {str(e)}")
        return create_internal_error_response(f"Failed to add incremental user content: {str(e)}")

def handle_remove_user_content(event: Dict[str, Any]) -> Dict[str, Any]:
    """Remove user content - POST /api/opensearch/user-content/remove"""
    try:
        body = event.get('body')
        if not body:
            return create_validation_error_response("Request body is missing")
        
        if isinstance(body, str):
            data = json.loads(body)
        else:
            data = body
        
        # Validate required parameters
        required_fields = ['project_id', 'document_id', 'content_index']
        for field in required_fields:
            if field not in data or data[field] is None:
                return create_validation_error_response(f"{field} is required")
        
        # page_index can be 0, so validate separately
        if 'page_index' not in data or data['page_index'] is None:
            return create_validation_error_response("page_index is required")
        
        project_id = data['project_id']
        document_id = data['document_id']
        content_index = data['content_index']
        
        try:
            page_index = int(data['page_index'])
            content_index = int(content_index)
        except (ValueError, TypeError):
            return create_validation_error_response("page_index and content_index must be integers")
        
        # Get page_id from page_index
        page_id = _get_segment_id_from_index(project_id, document_id, page_index)
        if not page_id:
            return create_not_found_response(f"Page not found: project_id={project_id}, document_id={document_id}, page_index={page_index}")
        
        logger.info(f"🗑️ Starting user content removal: page_id={page_id} (from page_index={page_index}), content_index={content_index}")
        
        opensearch = _get_opensearch_service()
        
        # Delete user content
        success = opensearch.remove_user_content(
            page_id=page_id,
            content_index=content_index
        )
        
        if not success:
            return create_internal_error_response("Failed to remove user content")
        
        # Update content_combined and regenerate embeddings
        updated_content = opensearch.get_page_tools_content(page_id)
        if updated_content:
            embed_success = opensearch.update_page_embeddings(page_id, updated_content)
            if not embed_success:
                logger.warning(f"Failed to update embeddings: {page_id}")
        
        result_data = {
            "page_id": page_id,
            "content_index": content_index,
            "content_removed": True,
            "embeddings_updated": bool(updated_content),
            "timestamp": get_current_timestamp()
        }
        
        logger.info(f"✅ User content removal complete: page_id={page_id}")
        return create_response_success(result_data)
        
    except Exception as e:
        logger.error(f"❌ Failed to remove user content: {str(e)}")
        return create_internal_error_response(f"Failed to remove user content: {str(e)}")

def _get_segment_id_from_index(index_id: str, document_id: str, segment_index: int) -> Optional[str]:
    """
    Retrieve segment_id from index_id, document_id, and segment_index
    """
    try:
        opensearch = _get_opensearch_service()
        
        # Search for the specific page in OpenSearch
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"document_id": document_id}},
                        {"term": {"segment_index": segment_index}}
                    ]
                }
            },
            "size": 1
        }
        
        response = opensearch.client.search(
            index=index_id,
            body=query
        )
        
        hits = response.get('hits', {}).get('hits', [])
        if hits:
            return hits[0]['_id']
        else:
            logger.warning(f"Page not found: index_id={index_id}, document_id={document_id}, segment_index={segment_index}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to retrieve page_id: {str(e)}")
        return None


def _analyze_tools_structure(tools: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze the tools field of the new page-unit structure"""
    analysis = {
        "bda_indexer_count": len(tools.get('bda_indexer', [])),
        "pdf_text_extractor_count": len(tools.get('pdf_text_extractor', [])),
        "ai_analysis_count": len(tools.get('ai_analysis', [])),
        "user_content_count": len(tools.get('user_content', [])),
        "total_tool_executions": 0
    }
    
    # Calculate total number of tool executions
    analysis["total_tool_executions"] = (
        analysis["bda_indexer_count"] + 
        analysis["pdf_text_extractor_count"] + 
        analysis["ai_analysis_count"] +
        analysis["user_content_count"]
    )
    
    # Detailed information for each tool type
    if analysis["bda_indexer_count"] > 0:
        bda_tools = tools.get('bda_indexer', [])
        analysis["bda_indexer_details"] = [
            {
                "content_length": len(tool.get('content', '')),
                "analysis_query": tool.get('analysis_query', 'N/A'),
                "created_at": tool.get('created_at', 'N/A')
            } for tool in bda_tools[:2]  # Max 2 only
        ]
    
    if analysis["pdf_text_extractor_count"] > 0:
        pdf_tools = tools.get('pdf_text_extractor', [])
        analysis["pdf_text_extractor_details"] = [
            {
                "content_length": len(tool.get('content', '')),
                "analysis_query": tool.get('analysis_query', 'N/A'),
                "created_at": tool.get('created_at', 'N/A')
            } for tool in pdf_tools[:2]  # Max 2 only
        ]
    
    if analysis["ai_analysis_count"] > 0:
        img_tools = tools.get('ai_analysis', [])
        analysis["ai_analysis_details"] = [
            {
                "content_length": len(tool.get('content', '')),
                "analysis_query": tool.get('analysis_query', 'N/A'),
                "metadata": tool.get('metadata', {}),
                "created_at": tool.get('created_at', 'N/A')
            } for tool in img_tools[:2]  # Max 2 only
        ]
    
    if analysis["user_content_count"] > 0:
        user_tools = tools.get('user_content', [])
        analysis["user_content_details"] = [
            {
                "content_length": len(tool.get('content', '')),
                "analysis_query": tool.get('analysis_query', 'N/A'),
                "created_at": tool.get('created_at', 'N/A')
            } for tool in user_tools[:2]  # Max 2 only
        ]
    
    return analysis


def _get_existing_segment_content(index_id: str, segment_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve existing segment content"""
    try:
        opensearch_service = _get_opensearch_service()

        search_body = {
            "size": 1,
            "query": {
                "term": {"segment_id": segment_id}
            }
        }
        
        response = opensearch_service.client.search(
            index=index_id,
            body=search_body
        )
        
        hits = response.get('hits', {}).get('hits', [])
        if hits:
            return hits[0]['_source']
        return None
        
    except Exception as e:
        logger.error(f"Failed to retrieve existing segment content: {str(e)}")
        return None


def _generate_incremental_content(existing_content: str, user_content: str) -> Optional[str]:
    """Generate incremental content via LLM"""
    try:
        # Get Bedrock settings from environment variables
        model_id = os.environ.get('BEDROCK_AGENT_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
        max_tokens = int(os.environ.get('BEDROCK_AGENT_MAX_TOKENS', '8192'))
        
        logger.info(f"Using LLM model: {model_id}, Max tokens: {max_tokens}")
        
        # Initialize Bedrock Runtime client
        bedrock_runtime = boto3.client('bedrock-runtime')
        
        # Construct prompt
        prompt = f"""You are a technical document analysis expert. Based on the existing document content and the user's additional content, please generate new incremental content.

Existing document content:
{existing_content[:5000]}  # Truncate overly long content for processing

User additional content:
{user_content}

Requirements:
1. Analyze the user's content based on the existing content and provide a supplement.
2. Extend the user's content more concretely and technically.
3. Write in a comprehensive and integrated perspective, considering the existing content.
4. Avoid duplicate content and provide new insights.
5. Write in Korean.

Incremental content:"""

        # Call Claude model
        message = {
            "role": "user",
            "content": prompt
        }
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [message],
            "max_tokens": max_tokens,
            "temperature": 0.7
        }
        
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType='application/json'
        )
        
        response_body = json.loads(response['body'].read().decode('utf-8'))
        
        # Extract content from Claude response
        if 'content' in response_body and len(response_body['content']) > 0:
            generated_content = response_body['content'][0]['text']
            logger.info(f"LLM incremental content generation successful: {len(generated_content)} characters")
            return generated_content.strip()
        else:
            logger.error("Content not found in LLM response")
            return None
        
    except Exception as e:
        logger.error(f"LLM incremental content generation failed: {str(e)}")
        return None


def _add_user_content_to_tools(index_id: str, segment_id: str, user_input: str, generated_content: str) -> bool:
    """Add user_content to tools structure"""
    try:
        opensearch_service = _get_opensearch_service()

        # Generate current timestamp
        current_timestamp = get_current_timestamp()
        
        # Create new user_content item
        new_user_content = {
            "content": generated_content,
            "analysis_query": user_input,
            "created_at": current_timestamp
        }
        
        # Retrieve existing document in OpenSearch
        existing_page = _get_existing_segment_content(index_id, segment_id)
        if not existing_page:
            logger.error(f"Page not found: {segment_id}")
            return False
        
        # Get existing tools structure
        existing_tools = existing_page.get('tools', {})
        
        # Create user_content array if it doesn't exist
        if 'user_content' not in existing_tools:
            existing_tools['user_content'] = []
        
        # Add new user_content
        existing_tools['user_content'].append(new_user_content)
        
        # Update document in OpenSearch
        update_body = {
            "doc": {
                "tools": existing_tools,
                "updated_at": current_timestamp
            }
        }
        
        response = opensearch_service.client.update(
            index=index_id,
            id=segment_id,
            body=update_body
        )
        
        logger.info(f"User content added to tools: {segment_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to add user content to tools: {str(e)}")
        return False


def _generate_content_combined_from_tools(tools: Dict[str, Any]) -> str:
    """Combine all content from tools to generate content_combined"""
    try:
        content_parts = []
        
        # Collect content by tool type
        tool_types = ['bda_indexer', 'pdf_text_extractor', 'ai_analysis', 'user_content']
        
        for tool_type in tool_types:
            if tool_type in tools and tools[tool_type]:
                tool_contents = []
                for tool_item in tools[tool_type]:
                    content = tool_item.get('content', '').strip()
                    if content:
                        tool_contents.append(content)
                
                if tool_contents:
                    # Add separated by tool type
                    if tool_type == 'bda_indexer':
                        content_parts.append(f"=== BDA Analysis Results ===\n" + "\n\n".join(tool_contents))
                    elif tool_type == 'pdf_text_extractor':
                        content_parts.append(f"=== PDF Text Extraction Results ===\n" + "\n\n".join(tool_contents))
                    elif tool_type == 'ai_analysis':
                        content_parts.append(f"=== AI Analysis Results ===\n" + "\n\n".join(tool_contents))
                    elif tool_type == 'user_content':
                        content_parts.append(f"=== User Added Analysis ===\n" + "\n\n".join(tool_contents))
        
        # Combine all content
        if content_parts:
            return "\n\n".join(content_parts)
        else:
            return ""
            
    except Exception as e:
        logger.error(f"Failed to generate content_combined from tools: {str(e)}")
        return ""


def _update_segment_content_combined(index_id: str, segment_id: str, new_content_combined: str) -> bool:
    """Update the content_combined field of a segment"""
    try:
        opensearch_service = _get_opensearch_service()
        
        update_body = {
            "doc": {
                "content_combined": new_content_combined,
                "updated_at": get_current_timestamp()
            }
        }
        
        response = opensearch_service.client.update(
            index=index_id,
            id=segment_id,
            body=update_body
        )
        
        logger.info(f"Page content update successful: {segment_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update page content: {str(e)}")
        return False


def _generate_and_update_embeddings(index_id: str, segment_id: str, content: str) -> bool:
    """Generate embeddings and update them"""
    try:
        opensearch_service = _get_opensearch_service()
        
        # Get embedding settings from environment variables
        embeddings_model_id = os.environ.get('EMBEDDINGS_MODEL_ID', 'amazon.titan-embed-text-v2:0')
        
        logger.info(f"Using embedding model: {embeddings_model_id}")
        
        # Initialize Bedrock Runtime client
        bedrock_runtime = boto3.client('bedrock-runtime')
        
        # Request embedding generation
        body = {
            "inputText": content[:8000],  # Titan model's max input length limit
            "dimensions": int(os.environ.get('EMBEDDINGS_DIMENSIONS', '1024')),
            "normalize": True
        }
        
        response = bedrock_runtime.invoke_model(
            modelId=embeddings_model_id,
            body=json.dumps(body),
            contentType='application/json'
        )
        
        response_body = json.loads(response['body'].read().decode('utf-8'))
        
        # Extract embedding vector
        if 'embedding' in response_body:
            embedding_vector = response_body['embedding']
            
            # Update document in OpenSearch
            update_body = {
                "doc": {
                    "vector_content": embedding_vector,
                    "updated_at": get_current_timestamp()
                }
            }
            
            opensearch_service.client.update(
                index=index_id,
                id=segment_id,
                body=update_body
            )
            
            logger.info(f"Embedding update successful: {segment_id}")
            return True
        else:
            logger.error("Embedding not found in response")
            return False
        
    except Exception as e:
        logger.error(f"Failed to generate and update embeddings: {str(e)}")
        return False
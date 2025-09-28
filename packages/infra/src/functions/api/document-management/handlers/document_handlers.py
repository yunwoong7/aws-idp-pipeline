"""
Document Management Handler Module
Functions for handling document upload, retrieval, and deletion APIs
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any
import urllib.parse
from botocore.config import Config

# Lambda Layer imports
from common import (
    DynamoDBService, 
    S3Service, 
    AWSClientFactory,
    create_success_response, 
    handle_lambda_error,
    get_current_timestamp,
    generate_uuid,
    setup_logging,
    extract_path_parameter,
    extract_query_parameter,
    validate_uuid,
    sanitize_filename
)

# Add parent directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.response import (
    create_created_response,
    create_validation_error_response,
    create_not_found_response,
    create_internal_error_response,
    create_cors_response
)
from utils.environment import (
    get_documents_table_name,
    get_document_processing_queue_url,
    get_workflow_state_machine_arn,
    get_opensearch_endpoint,
    get_opensearch_index_name,
    get_opensearch_region,
    get_aws_region,
    get_stage,
    get_documents_bucket_name
)
from utils.helpers import (
    decode_base64_file,
    get_pdf_page_count,
    generate_s3_key,
    generate_presigned_url,
    validate_file_extension
)
from services.document_services import (
    delete_documents_from_opensearch,
    send_document_processing_message
)
# Removed: from services.activity_service import record_document_activity, ActivityType
# Now using common ActivityRecorder

# Lambda Layer 서비스 초기화
db_service = DynamoDBService()
s3_service = S3Service()

aws_clients = AWSClientFactory()

# AWS 서비스 클라이언트 초기화
sqs_client = aws_clients.get_sqs_client()
stepfunctions_client = aws_clients.get_stepfunctions_client()

logger = setup_logging()


def handle_upload_document(event: Dict[str, Any]) -> Dict[str, Any]:
    """Generate S3 Presigned URL for file upload (integrated upload method)"""
    try:
        # New: use index_id (required)
        
        # Request body parsing (JSON format supported)
        body = event.get('body')
        if not body:
            return create_validation_error_response("Request body is required")
        
        try:
            if isinstance(body, str):
                data = json.loads(body)
            else:
                data = body
        except json.JSONDecodeError:
            return create_validation_error_response("Invalid JSON format")
        
        # Required parameter validation
        index_id = None
        file_name = data.get('file_name')
        file_size = data.get('file_size')
        file_type = data.get('file_type')
        description = data.get('description', '')
        # Accept index_id (required)
        index_id = data.get('index_id') or data.get('workspace_id')
        
        if not index_id:
            return create_validation_error_response("index_id is required")
        if not file_name:
            return create_validation_error_response("file_name is required")
        if not file_size or not isinstance(file_size, (int, float)):
            return create_validation_error_response("file_size(bytes) is required")
        
        # File size limit (unified to 500MB)
        MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
        if file_size > MAX_FILE_SIZE:
            file_size_mb = round(file_size / 1024 / 1024, 2)
            return create_validation_error_response(
                f"File size is too large ({file_size_mb}MB). You can upload up to 500MB."
            )
        
        # File extension validation - expanded to support more media types
        supported_extensions = [
            # Documents
            '.pdf', '.dwg', '.dxf', '.txt', '.doc', '.docx', '.rtf', '.odt',
            # Images  
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp',
            # Videos
            '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.3gp',
            # Audio
            '.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.aiff'
        ]
        if not validate_file_extension(file_name, supported_extensions):
            return create_validation_error_response("Unsupported file type")
        
        # Auto-detect file type
        if not file_type:
            file_extension = file_name.lower().split('.')[-1] if '.' in file_name else ''
            file_type_map = {
                # Documents
                'pdf': 'application/pdf',
                'dwg': 'application/dwg', 
                'dxf': 'application/dxf',
                'txt': 'text/plain',
                'doc': 'application/msword',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'rtf': 'application/rtf',
                'odt': 'application/vnd.oasis.opendocument.text',
                # Images
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'bmp': 'image/bmp',
                'tiff': 'image/tiff',
                'tif': 'image/tiff',
                'webp': 'image/webp',
                # Videos
                'mp4': 'video/mp4',
                'avi': 'video/x-msvideo',
                'mov': 'video/quicktime',
                'wmv': 'video/x-ms-wmv',
                'flv': 'video/x-flv',
                'mkv': 'video/x-matroska',
                'webm': 'video/webm',
                '3gp': 'video/3gpp',
                # Audio
                'mp3': 'audio/mpeg',
                'wav': 'audio/wav',
                'flac': 'audio/flac',
                'm4a': 'audio/mp4',
                'aac': 'audio/aac',
                'ogg': 'audio/ogg',
                'wma': 'audio/x-ms-wma',
                'aiff': 'audio/aiff'
            }
            file_type = file_type_map.get(file_extension, 'application/octet-stream')
        
        # Note: BDA primarily supports documents and some images, but we allow all media types
        # Video/Audio files will be processed for basic metadata only via the workflow pipeline
        bda_supported_types = ['application/pdf', 'application/dwg', 'application/dxf', 'image/jpeg', 'image/png']
        logger.info(f"File type: {file_type} - BDA supported: {file_type in bda_supported_types}")
        
        # Generate unique document ID
        document_id = generate_uuid()
        current_time = get_current_timestamp()
        
        # Generate S3 key (indexes path) - BDA requires strict naming
        safe_name = sanitize_filename(file_name)
        logger.info(f"File name sanitized: '{file_name}' -> '{safe_name}'")
        s3_key = f"indexes/{index_id}/documents/{document_id}/{safe_name}"
        bucket_name = get_documents_bucket_name()
        file_uri = f"s3://{bucket_name}/{s3_key}"
        
        # Determine media_type for downstream pipeline branching
        media_type = DynamoDBService.infer_media_type(file_type, file_name)

        # Register metadata in advance (status: pending_upload)
        try:
            document_item = {
                'document_id': document_id,
                'index_id': index_id,
                'file_name': file_name,  # Original filename
                'safe_file_name': safe_name,  # BDA-compatible filename
                'file_type': file_type,
                'media_type': media_type,
                'file_size': int(file_size),
                'file_uri': file_uri,
                'total_pages': 1,  # Default value, updated after BDA completion
                'status': 'pending_upload',  # Waiting for upload
                'description': description,
                'summary': '',
                'statistics': {}
            }
            
            db_service.create_item('documents', document_item)
            logger.info(f"Pre-upload metadata registration completed: {document_id}")
            
        except Exception as e:
            logger.error(f"Failed to register metadata: {str(e)}")
            return handle_lambda_error(e)
        
        # Generate S3 Pre-signed URL (PUT method, valid for 24 hours)
        try:
            import boto3
            # 강제로 Signature V4 사용 (일부 환경에서 V2 서명으로 생성되어 불일치 발생하는 문제 방지)
            s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
            
            # Generate pre-signed URL for PUT
            # Remove ContentType to avoid CORS preflight issues
            params = {
                'Bucket': bucket_name,
                'Key': s3_key
            }
            
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params=params,
                ExpiresIn=86400  # 24 hours
            )
            
            if not presigned_url:
                return create_internal_error_response("Failed to generate pre-signed URL")
            
            logger.info(f"Pre-signed URL for upload generated: {document_id}")
            
        except Exception as e:
            # Rollback metadata
            try:
                db_service.delete_item('documents', {'document_id': document_id})
            except:
                pass
            logger.error(f"Failed to generate pre-signed URL: {str(e)}")
            return handle_lambda_error(e)
        
        # Response data
        response_data = {
            "document_id": document_id,
            "index_id": index_id,
            "file_name": file_name,
            "file_type": file_type,
            "file_size": file_size,
            "upload_url": presigned_url,
            "upload_method": "PUT",
            "content_type": file_type,
            "expiration_hours": 24,
            "file_uri": file_uri,
            "completion_callback_url": f"/api/indices/{index_id}/documents/{document_id}/upload-complete",
            "instructions": {
                "method": "PUT",
                "headers": {
                    "Content-Type": file_type
                },
                "body": "Raw file bytes"
            }
        }
        
        # Include success message in response data
        response_data["message"] = "Upload URL has been generated"
        return create_success_response(response_data)
        
    except Exception as e:
        logger.error(f"Error generating upload URL: {str(e)}")
        return handle_lambda_error(e)

def handle_get_documents(event: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve document list (index-independent)"""
    try:
        # Use required index_id (workspace)
        index_id = extract_query_parameter(event, 'index_id')
        simple_param = extract_query_parameter(event, 'simple')
        segments_param = extract_query_parameter(event, 'segments')
        
        # Check if simple mode parameter (simple=true)
        simple_mode = simple_param == 'true'
        # Check if segment information is included (segments=true)
        include_segments = segments_param == 'true'
        
        # index_id is required
        if not index_id:
            return create_validation_error_response("index_id query parameter is required")
            
        # Retrieve documents for the specific index_id from DynamoDB
        try:
            documents = db_service.get_documents(index_id)
            
            # Sort by latest document
            documents.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
        except Exception as e:
            logger.error(f"Failed to retrieve documents from Documents table: {str(e)}")
            return handle_lambda_error(e)
        
        # Handle simple mode
        if simple_mode:
            # Return only specific fields in simple mode
            filtered_documents = []
            allowed_fields = {
                "summary", "created_at", "status", "file_type", "file_size", 
                "file_uri", "document_id", "index_id", "file_name", 
                "description", "total_pages"
            }
            
            for doc in documents:
                filtered_doc = {}
                for field in allowed_fields:
                    if field in doc:
                        filtered_doc[field] = doc[field]
                    else:
                        # Set default values
                        if field == "summary":
                            filtered_doc[field] = ""
                        elif field == "description":
                            filtered_doc[field] = ""
                        elif field == "status":
                            filtered_doc[field] = "uploaded"
                        elif field == "total_pages":
                            filtered_doc[field] = 0
                
                # Check if page information is included
                if include_segments:
                    try:
                        segments = db_service.get_document_segments(doc['document_id'])
                        # Sort pages by segment_index
                        segments.sort(key=lambda x: x.get('segment_index', 0))
                        
                        # Extract only necessary fields from page info
                        filtered_segments = []
                        for segment in segments:
                            filtered_segment = {
                                'segment_id': segment.get('segment_id', ''),
                                'segment_index': segment.get('segment_index', 0),
                                'document_id': segment.get('document_id', ''),
                                'index_id': segment.get('index_id', ''),
                                'image_uri': segment.get('image_uri', ''),
                                'file_uri': segment.get('file_uri', ''),
                                'created_at': segment.get('created_at', '')
                            }
                            filtered_segments.append(filtered_segment)
                        
                        filtered_doc['segments'] = filtered_segments
                    except Exception as e:
                        logger.warning(f"Failed to retrieve page information for document {doc['document_id']}: {str(e)}")
                        filtered_doc['pages'] = []
                
                filtered_documents.append(filtered_doc)
            
            response_data = {
                "index_id": index_id,
                "documents": filtered_documents,
                "total_count": len(filtered_documents)
            }
        else:
            # In normal mode, generate additional info for each document
            bucket_name = get_documents_bucket_name()
            for doc in documents:
                _enrich_document_info(doc, index_id, bucket_name)
            
            response_data = {
                "index_id": index_id,
                "documents": documents,
                "total_count": len(documents)
            }
        
        return create_success_response(response_data)
        
    except Exception as e:
        logger.error(f"Error retrieving document list: {str(e)}")
        return handle_lambda_error(e)


def handle_get_document_detail(event: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve detailed information for a specific document"""
    try:
        # Use default index_id for backward compatibility
        index_id = extract_query_parameter(event, 'index_id')
        document_id = extract_path_parameter(event, 'document_id')
        
        if not document_id:
            return create_validation_error_response("document_id is required")
        
        if not validate_uuid(document_id):
            return create_validation_error_response("Invalid document_id format")
        
        # Retrieve document from DynamoDB
        try:
            document = db_service.get_item('documents', {'document_id': document_id})
            
            if not document:
                return create_not_found_response("Document not found")
            
        except Exception as e:
            logger.error(f"Failed to retrieve document from Documents table: {str(e)}")
            return handle_lambda_error(e)
        
        # Retrieve pages for the document (with pagination to get all segments)
        try:
            from boto3.dynamodb.conditions import Key
            segments = []
            last_evaluated_key = None

            while True:
                segments_response = db_service.query_items(
                    table_name='segments',
                    key_condition_expression=Key('document_id').eq(document_id),
                    index_name='DocumentIdIndex',
                    exclusive_start_key=last_evaluated_key
                )

                page_segments = segments_response.get('Items', [])
                segments.extend(page_segments)

                last_evaluated_key = segments_response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break

            segments.sort(key=lambda x: x.get('segment_index', 0))
            logger.info(f"Retrieved {len(segments)} segments for document {document_id}")

        except Exception as e:
            logger.error(f"Failed to retrieve segments from Segments table: {str(e)}")
            segments = []
        
        # Process segments to include segment_id and status
        processed_segments = []
        for segment in segments:
            processed_segment = {
                'segment_id': segment.get('segment_id'),
                'segment_index': segment.get('segment_index', 0),
                'status': segment.get('status', 'pending'),
                'document_id': segment.get('document_id'),
                'index_id': segment.get('index_id'),
                'image_uri': segment.get('image_uri', ''),
                'file_uri': segment.get('file_uri', ''),
                'created_at': segment.get('created_at', ''),
                'updated_at': segment.get('updated_at', '')
            }
            processed_segments.append(processed_segment)

        # Construct response data
        response_document = {
            'document_id': document.get('document_id'),
            'index_id': document.get('index_id'),
            'file_name': document.get('file_name'),
            'file_type': document.get('file_type'),
            'file_size': document.get('file_size'),
            'file_uri': document.get('file_uri'),
            'total_pages': document.get('total_pages'),
            'status': document.get('status'),
            'description': document.get('description', ''),
            'summary': document.get('summary', ''),
            'created_at': document.get('created_at'),
            'updated_at': document.get('updated_at'),
            'file_presigned_url': s3_service.generate_presigned_url(document['file_uri']),
            'segments': processed_segments,
            'total_segments': len(processed_segments)
        }
        
        return create_success_response(response_document)
        
    except Exception as e:
        logger.error(f"Error retrieving document detail: {str(e)}")
        return handle_lambda_error(e)


def handle_delete_document(event: Dict[str, Any]) -> Dict[str, Any]:
    """Delete document (S3 files and DynamoDB record, related pages)"""
    try:
        # Use default project_id for backward compatibility
        index_id = extract_query_parameter(event, 'index_id')
        document_id = extract_path_parameter(event, 'document_id')
        
        if not document_id:
            return create_validation_error_response("document_id is required")
        
        if not validate_uuid(document_id):
            return create_validation_error_response("Invalid document_id format")
        
        # Retrieve document information
        try:
            document = db_service.get_item('documents', {'document_id': document_id})
            
            if not document:
                return create_not_found_response("Document not found")
            
        except Exception as e:
            logger.error(f"Failed to retrieve document from Documents table: {str(e)}")
            return handle_lambda_error(e)
        
        # Get index_id from document if not provided in query parameter
        actual_index_id = index_id or document.get('index_id')
        if not actual_index_id:
            logger.error(f"No index_id found for document: {document_id}")
            return create_validation_error_response("index_id is required")
        
        # Retrieve related pages and delete
        segments_to_delete = _get_document_segments(actual_index_id, document_id, document.get('total_pages', 0))
        
        # Delete files from S3
        bucket_name = get_documents_bucket_name()
        _delete_s3_files(bucket_name, document, segments_to_delete, actual_index_id, document_id)
        
        # Delete related pages from Pages table
        _delete_document_segments(segments_to_delete)
        
        # Delete document from Documents table
        try:
            db_service.delete_item('documents', {'document_id': document_id})
            logger.info(f"Document {document_id} deleted from Documents table")
        except Exception as e:
            logger.error(f"Failed to delete document from Documents table: {str(e)}")
            return handle_lambda_error(e)
        
        # Delete related documents from OpenSearch
        try:
            delete_documents_from_opensearch(actual_index_id, document_id)
        except Exception as e:
            logger.error(f"Failed to delete document from OpenSearch: {str(e)}")
        
        # Construct success response data
        response_data = {
            "index_id": actual_index_id,
            "document_id": document_id,
            "file_name": document.get('file_name', ''),
            "deleted_segments": len(segments_to_delete),
            "status": "deleted"
        }
        
        return create_success_response(response_data)
        
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        return handle_lambda_error(e)


# Private helper functions
def _start_workflow_execution(index_id: str, document_id: str, file_name: str, 
                             file_type: str, current_time: str) -> None:
    """Start execution of Step Function workflow"""
    state_machine_arn = get_workflow_state_machine_arn()
    if not state_machine_arn:
        logger.warning("⚠️ Step Function ARN is not set")
        return
    
    input_data = {
        'index_id': index_id,
        'document_id': document_id,
        'file_name': file_name,
        'file_type': file_type,
        'timestamp': current_time
    }
    
    execution_name = f"doc-{document_id}-{int(datetime.now(timezone.utc).timestamp())}"
    
    stepfunctions_client.start_execution(
        stateMachineArn=state_machine_arn,
        name=execution_name,
        input=json.dumps(input_data)
    )
    
    logger.info(f"Step Function workflow started: {execution_name}")


def _enrich_document_info(doc: Dict[str, Any], index_id: str, bucket_name: str) -> None:
    """Enhance document info with additional data (return S3 URI, remove Pre-signed URL)"""
    # Remove download_url field - change to dynamic Pre-signed URL generation for security
    if 'download_url' in doc:
        del doc['download_url']
    
    # Keep file_uri as pure S3 URI (remove Pre-signed URL generation)
    if doc.get('file_uri'):
        logger.info(f"Keeping file_uri as S3 URI: {doc['file_uri']}")
        # file_uri is already in S3 URI format, so keep it
    
    # Generate page image URLs and analysis status
    try:
        document_id = doc.get('document_id', '')
        
        if document_id:
            from boto3.dynamodb.conditions import Key
            segments_response = db_service.query_items(
                table_name='segments',
                key_condition_expression=Key('document_id').eq(document_id),
                index_name='DocumentIdIndex'
            )
            segments = segments_response.get('Items', [])
            segments.sort(key=lambda x: x.get('segment_index', 0))
            
            # Calculate analysis status statistics
            analysis_stats = _calculate_analysis_stats(segments)
            doc['analysis_stats'] = analysis_stats
            doc['analysis_status'] = _determine_analysis_status(analysis_stats)
            
            # Generate page image URLs
            segment_image_urls = []
            for segment in segments:
                segment_info = _create_segment_info(segment, bucket_name)
                segment_image_urls.append(segment_info)  
            
            doc['segment_images'] = segment_image_urls
        else:
            doc['analysis_status'] = 'no_document_id'
            doc['analysis_stats'] = _create_empty_analysis_stats()
            doc['segment_images'] = []
        
    except Exception as e:
        logger.error(f"Failed to generate page info: {str(e)}")
        doc['segment_images'] = []
        doc['analysis_status'] = 'unknown'
        doc['analysis_stats'] = _create_empty_analysis_stats()


def _calculate_analysis_stats(segments: list) -> Dict[str, int]:
    """Calculate analysis status statistics"""
    stats = {
        'total_segments': len(segments),
        'completed_segments': 0,
        'processing_segments': 0,
        'error_segments': 0,
        'pending_segments': 0
    }
    
    for segment in segments:
        status = segment.get('status', 'pending')
        if status == 'completed':
            stats['completed_segments'] += 1
        elif status == 'processing':
            stats['processing_segments'] += 1
        elif status == 'error':
            stats['error_segments'] += 1
        else:
            stats['pending_segments'] += 1
    
    return stats


def _determine_analysis_status(stats: Dict[str, int]) -> str:
    """Determine analysis status"""
    if stats['total_segments'] == 0:
        return 'no_segments'
    elif stats['error_segments'] > 0:
        return 'error'
    elif stats['processing_segments'] > 0:
        return 'processing'
    elif stats['completed_segments'] == stats['total_segments']:
        return 'completed'
    elif stats['completed_segments'] > 0:
        return 'partial'
    else:
        return 'pending'


def _create_empty_analysis_stats() -> Dict[str, int]:
    """Create empty analysis statistics"""
    return {
        'total_pages': 0,
        'completed_pages': 0,
        'processing_pages': 0,
        'error_pages': 0,
        'pending_pages': 0
    }


def _create_segment_info(segment: Dict[str, Any], bucket_name: str) -> Dict[str, Any]:
    """Generate segment info (return S3 URI, remove Pre-signed URL)"""
    image_uri = segment.get('image_uri')
    segment_index = segment.get('segment_index', 0)
    status = segment.get('status', 'pending')
    file_uri = segment.get('file_uri')
    start_timecode_smpte = segment.get('start_timecode_smpte')
    end_timecode_smpte = segment.get('end_timecode_smpte')
    
    # Generate Pre-signed URL instead of returning
    logger.info(f"Returning S3 URI for segment {segment_index + 1}: image_uri={image_uri}, file_uri={file_uri}")
    
    return {
        'segment_number': segment_index + 1,  # Convert 0-based to 1-based for display
        'segment_index': segment_index,
        'image_uri': image_uri,  # Return pure S3 URI (matching frontend expectation)
        'image_url': image_uri,  # Backward compatibility
        'file_uri': file_uri,    # Return pure S3 URI
        'start_timecode_smpte': start_timecode_smpte,
        'end_timecode_smpte': end_timecode_smpte,
        'status': status
    }


def _get_document_segments(index_id: str, document_id: str, total_segments: int) -> list:
    """Retrieve all segments for a document using GSI only.
    Segment IDs are UUIDs; do not synthesize IDs from index/document/segment_index.
    """
    try:
        from boto3.dynamodb.conditions import Key
        response = db_service.query_items(
            table_name='segments',
            key_condition_expression=Key('document_id').eq(document_id),
            index_name='DocumentIdIndex'
        )
        items = response.get('Items', [])
        logger.info(f"Number of segments found via GSI: {len(items)}")
        return items
    except Exception as e:
        logger.error(f"Failed to retrieve segments: {str(e)}")
        return []


def _delete_s3_files(bucket_name: str, document: Dict[str, Any], segments_to_delete: list, 
                    index_id: str, document_id: str) -> None:
    """Delete document related files from S3"""
    # Delete original document file
    try:
        file_uri = document['file_uri']
        s3_service.delete_object(file_uri, bucket_name)
        logger.info(f"S3 original file deleted: {file_uri}")
    except Exception as e:
        logger.error(f"Failed to delete S3 original file: {str(e)}")
    
    # Delete page images
    for segment in segments_to_delete:
        try:
            image_uri = segment.get('image_uri')
            if image_uri:
                s3_service.delete_object(image_uri, bucket_name)
                logger.info(f"S3 page image deleted: {image_uri}")
        except Exception as e:
            logger.error(f"Failed to delete S3 page image: {str(e)}")
    
    # Delete entire document folder
    try:
        document_folder_prefix = f"indexes/{index_id}/documents/{document_id}/"
        
        # Use S3 service's prefix-based deletion functionality
        result = s3_service.delete_objects_with_prefix(document_folder_prefix, bucket_name)
        deleted_count = result.get('deleted_count', 0)
        errors = result.get('errors', [])
        
        if errors:
            logger.warning(f"S3 document folder deletion completed with {len(errors)} errors: {document_folder_prefix}")
            for error in errors[:3]:  # Log first 3 errors
                logger.warning(f"S3 deletion error: {error}")
        else:
            logger.info(f"S3 document folder deleted successfully: {document_folder_prefix} ({deleted_count} objects)")
    except Exception as e:
        logger.error(f"Failed to delete S3 document folder: {str(e)}")


def _delete_document_segments(segments_to_delete: list) -> int:
    """Delete all segments for a document"""
    deleted_count = 0
    failed_count = 0
    
    if len(segments_to_delete) > 0:
        logger.info(f"Starting deletion of {len(segments_to_delete)} segments from Segments table...")
        
        for i, segment in enumerate(segments_to_delete, 1):
            try:
                segment_id = segment['segment_id']
                logger.info(f"[{i}/{len(segments_to_delete)}] Attempting to delete segment: {segment_id}")
                
                deleted_item = db_service.delete_item(
                    table_name='segments',
                    key={'segment_id': segment_id}
                )
                
                if deleted_item:
                    deleted_count += 1
                    logger.info(f"✅ Segment deleted successfully: {segment_id}")
                else:
                    logger.warning(f"⚠️ Segment already does not exist: {segment_id}")
                    deleted_count += 1
                
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Failed to delete segment: {str(e)}")
        
        logger.info(f"Segments table deletion completed: Success {deleted_count} items, Failed {failed_count} items")
    else:
        logger.warning("No segments to delete found")
    
    return deleted_count


def handle_generate_presigned_url(event: Dict[str, Any]) -> Dict[str, Any]:
    """Generate pre-signed URL for S3 object using common S3Service"""
    return s3_service.handle_generate_presigned_url_request(event)


def handle_generate_upload_presigned_url(event: Dict[str, Any]) -> Dict[str, Any]:
    """Generate S3 Pre-signed URL for large file upload"""
    try:
        # Parse request body
        body = event.get('body')
        if not body:
            return create_validation_error_response("Request body is required")
        
        try:
            if isinstance(body, str):
                data = json.loads(body)
            else:
                data = body
        except json.JSONDecodeError:
            return create_validation_error_response("Invalid JSON format")
        
        # Required parameter validation
        index_id = data.get('index_id')
        file_name = data.get('file_name')
        file_size = data.get('file_size')
        file_type = data.get('file_type')
        description = data.get('description', '')
        
        if not index_id:
            return create_validation_error_response("index_id is required")
        
        if not file_name:
            return create_validation_error_response("file_name is required")
        if not file_size or not isinstance(file_size, (int, float)):
            return create_validation_error_response("file_size(bytes) is required")
        
        # File size limit (500MB)
        MAX_LARGE_FILE_SIZE = 500 * 1024 * 1024  # 500MB
        if file_size > MAX_LARGE_FILE_SIZE:
            file_size_mb = round(file_size / 1024 / 1024, 2)
            return create_validation_error_response(
                f"File size is too large ({file_size_mb}MB). You can upload up to 500MB."
            )
        
        # File extension validation - expanded to support more media types
        supported_extensions = [
            # Documents
            '.pdf', '.dwg', '.dxf', '.txt', '.doc', '.docx', '.rtf', '.odt',
            # Images  
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp',
            # Videos
            '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.webm', '.3gp',
            # Audio
            '.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.aiff'
        ]
        if not validate_file_extension(file_name, supported_extensions):
            return create_validation_error_response("Unsupported file type")
        
        # Auto-detect file type
        if not file_type:
            file_extension = file_name.lower().split('.')[-1] if '.' in file_name else ''
            file_type_map = {
                # Documents
                'pdf': 'application/pdf',
                'dwg': 'application/dwg', 
                'dxf': 'application/dxf',
                'txt': 'text/plain',
                'doc': 'application/msword',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'rtf': 'application/rtf',
                'odt': 'application/vnd.oasis.opendocument.text',
                # Images
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'bmp': 'image/bmp',
                'tiff': 'image/tiff',
                'tif': 'image/tiff',
                'webp': 'image/webp',
                # Videos
                'mp4': 'video/mp4',
                'avi': 'video/x-msvideo',
                'mov': 'video/quicktime',
                'wmv': 'video/x-ms-wmv',
                'flv': 'video/x-flv',
                'mkv': 'video/x-matroska',
                'webm': 'video/webm',
                '3gp': 'video/3gpp',
                # Audio
                'mp3': 'audio/mpeg',
                'wav': 'audio/wav',
                'flac': 'audio/flac',
                'm4a': 'audio/mp4',
                'aac': 'audio/aac',
                'ogg': 'audio/ogg',
                'wma': 'audio/x-ms-wma',
                'aiff': 'audio/aiff'
            }
            file_type = file_type_map.get(file_extension, 'application/octet-stream')
        
        # Note: BDA primarily supports documents and some images, but we allow all media types
        # Video/Audio files will be processed for basic metadata only via the workflow pipeline
        bda_supported_types = [
            # Documents
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',  # .docx
            'application/msword',  # .doc
            'text/plain',  # .txt
            'application/rtf',  # .rtf
            'application/vnd.oasis.opendocument.text',  # .odt
            'application/dwg', 
            'application/dxf',
            # Images
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/bmp',
            'image/tiff',  # .tiff, .tif
            'image/webp',
            # Videos (MP4, MOV with H.264, H.265, VP8, VP9 codecs)
            'video/mp4',
            'video/quicktime',  # MOV files
            'video/x-msvideo',  # .avi
            'video/x-ms-wmv',  # .wmv
            'video/x-flv',  # .flv
            'video/x-matroska',  # .mkv
            'video/webm',
            'video/3gpp',
            # Audio (FLAC, M4A, MP3, Ogg, WAV)
            'audio/mp4',  # M4A
            'audio/mpeg',  # MP3
            'audio/flac',
            'audio/ogg',
            'audio/wav',
            'audio/x-wav',
            'audio/aac',
            'audio/x-ms-wma',
            'audio/aiff'
        ]
        logger.info(f"File type: {file_type} - BDA supported: {file_type in bda_supported_types}")
        
        # Generate unique document ID
        document_id = generate_uuid()
        current_time = get_current_timestamp()
        
        # Determine media_type for downstream pipeline branching
        media_type = DynamoDBService.infer_media_type(file_type, file_name)

        # Generate S3 key (indexes path) - BDA requires strict naming
        safe_name = sanitize_filename(file_name)
        logger.info(f"File name sanitized: '{file_name}' -> '{safe_name}'")
        s3_key = generate_s3_key(index_id, document_id, safe_name)
        bucket_name = get_documents_bucket_name()
        file_uri = f"s3://{bucket_name}/{s3_key}"
        
        # Estimate page count for PDF files (actual value will be calculated after upload)
        if file_type == 'application/pdf' or file_name.lower().endswith('.pdf'):
            # Rough estimate: 10 pages per MB (actual value will be updated after upload)
            estimated_pages = max(1, int(file_size / (1024 * 1024)) * 10)
            estimated_pages = min(estimated_pages, 1000)  # Limit to max 1000 pages
        else:
            estimated_pages = 1
        
        # Register metadata in advance (status: pending_upload)
        try:
            document_item = {
                'document_id': document_id,
                'index_id': index_id,
                'file_name': file_name,  # Original filename
                'safe_file_name': safe_name,  # BDA-compatible filename
                'file_type': file_type,
                'media_type': media_type,
                'file_size': int(file_size),
                'file_uri': file_uri,
                'total_pages': estimated_pages,
                'status': 'pending_upload',  # Waiting for upload
                'description': description,
                'summary': '',
                'statistics': {}
            }
            
            db_service.create_item('documents', document_item)
            logger.info(f"Pre-upload metadata registration completed: {document_id}")
            
        except Exception as e:
            logger.error(f"Failed to register metadata: {str(e)}")
            return handle_lambda_error(e)
        
        # Generate S3 Pre-signed URL (PUT method, valid for 24 hours)
        try:
            # Direct boto3 S3 client usage
            import boto3
            # 강제로 Signature V4 사용 (일부 환경에서 V2 서명으로 생성되어 불일치 발생하는 문제 방지)
            s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))
            
            # Generate pre-signed URL for PUT
            # Remove ContentType to avoid CORS preflight issues
            params = {
                'Bucket': bucket_name,
                'Key': s3_key
            }
            
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params=params,
                ExpiresIn=86400  # 24 hours
            )
            
            if not presigned_url:
                return create_internal_error_response("Failed to generate pre-signed URL")
            
            logger.info(f"Pre-signed URL for large upload generated: {document_id}")
            
        except Exception as e:
            # Rollback metadata
            try:
                db_service.delete_item('documents', {'document_id': document_id})
            except:
                pass
            logger.error(f"Failed to generate pre-signed URL: {str(e)}")
            return handle_lambda_error(e)
        
        # Response data
        response_data = {
            "document_id": document_id,
            "index_id": index_id,
            "file_name": file_name,
            "file_type": file_type,
            "file_size": file_size,
            "estimated_pages": estimated_pages,
            "upload_url": presigned_url,
            "upload_method": "PUT",
            "content_type": file_type,
            "expiration_hours": 24,
            "file_uri": file_uri,
            "completion_callback_url": f"/api/indices/{index_id}/documents/{document_id}/upload-complete",
            "instructions": {
                "method": "PUT",
                "headers": {
                    "Content-Type": file_type
                },
                "body": "Raw file bytes"
            }
        }
        
        return create_success_response(response_data)
        
    except Exception as e:
        logger.error(f"Error generating large upload Pre-signed URL: {str(e)}")
        return handle_lambda_error(e)


def handle_upload_complete(event: Dict[str, Any]) -> Dict[str, Any]:
    """Process completion of large file upload"""
    try:
        # index_id will be loaded from document item
        document_id = extract_path_parameter(event, 'document_id')
        
        if not document_id:
            return create_validation_error_response("document_id is required")
        
        if not validate_uuid(document_id):
            return create_validation_error_response("Invalid document_id format")
        
        # Retrieve document metadata
        try:
            document = db_service.get_item('documents', {'document_id': document_id})
            
            if not document:
                return create_not_found_response("Document not found")
            
            if document.get('status') != 'pending_upload':
                return create_validation_error_response("Document is not in pending upload status")
                
        except Exception as e:
            logger.error(f"Failed to retrieve document: {str(e)}")
            return handle_lambda_error(e)
        
        # Verify actual file in S3
        try:
            file_uri = document['file_uri']
            s3_key = file_uri.replace(f"s3://{get_documents_bucket_name()}/", "")
            bucket_name = get_documents_bucket_name()
            
            logger.info(f"Attempting to verify file - file_uri: {file_uri}")
            logger.info(f"Attempting to verify file - s3_key: {s3_key}")
            logger.info(f"Attempting to verify file - bucket_name: {bucket_name}")
            
            # Check S3 object metadata
            s3_object_info = s3_service.get_object_metadata(s3_key, bucket_name)
            if not s3_object_info:
                # Try with URL-encoded filename if original doesn't work
                from urllib.parse import quote
                parts = s3_key.split('/')
                if len(parts) >= 4:
                    # Encode only the filename part (last element)
                    parts[-1] = quote(parts[-1])
                    encoded_s3_key = '/'.join(parts)
                    logger.info(f"Retry file verification (URL-encoded) - encoded_s3_key: {encoded_s3_key}")
                    s3_object_info = s3_service.get_object_metadata(encoded_s3_key, bucket_name)
                    if s3_object_info:
                        # Update the stored file_uri with the correct encoded version
                        encoded_file_uri = f"s3://{bucket_name}/{encoded_s3_key}"
                        logger.info(f"URL-encoded filename found. Updating file_uri: {encoded_file_uri}")
                        # Update the document record with correct file_uri
                        try:
                            update_data = {'file_uri': encoded_file_uri}
                            db_service.update_item('documents', {'document_id': document_id}, updates=update_data)
                        except Exception as update_e:
                            logger.warning(f"Failed to update file_uri: {str(update_e)}")
                
                if not s3_object_info:
                    return create_validation_error_response("File uploaded to S3 not found")
            
            actual_file_size = int(s3_object_info.get('ContentLength', 0))
            logger.info(f"S3 upload verification completed: {s3_key}, actual size: {actual_file_size} bytes")
            
        except Exception as e:
            logger.error(f"Failed to verify S3 file: {str(e)}")
            return create_validation_error_response("Uploaded file could not be verified")
        
        # Page count will be handled by document-indexer after BDA completion
        # Current default value
        current_time = get_current_timestamp()
        actual_pages = 1  # Default value, will be updated to accurate value after BDA completion
        
        # Update document status
        try:
            update_data = {
                'status': 'uploaded',
                'file_size': actual_file_size,
                'total_pages': actual_pages
            }
            
            db_service.update_item('documents', {'document_id': document_id}, updates=update_data)
            logger.info(f"Large upload completion processing: {document_id}")
            
        except Exception as e:
            logger.error(f"Failed to update document status: {str(e)}")
            return handle_lambda_error(e)
        
        # Page metadata will be generated by document-indexer after BDA completion
        # Current omission
        
        # Send document processing message to SQS
        try:
            index_id = document.get('index_id')
            send_document_processing_message(
                index_id, document_id, document['file_name'], document['file_type'],
                actual_file_size, file_uri, actual_pages, current_time
            )
        except Exception as e:
            logger.error(f"Failed to send message to SQS: {str(e)}")
        
        # Start Step Function workflow
        try:
            _start_workflow_execution(index_id, document_id, document['file_name'], 
                                    document['file_type'], current_time)
        except Exception as e:
            logger.error(f"Failed to start Step Function workflow: {str(e)}")
        
        response_data = {
            "document_id": document_id,
            "index_id": index_id,
            "file_name": document['file_name'],
            "file_type": document['file_type'],
            "file_size": actual_file_size,
            "total_pages": actual_pages,
            "status": "uploaded",
            "file_uri": file_uri
        }
        
        # Include success message in response data
        response_data["message"] = "Large file upload completed"
        return create_success_response(response_data)
        
    except Exception as e:
        logger.error(f"Error processing large upload completion: {str(e)}")
        return handle_lambda_error(e)


def handle_generate_presigned_url_standalone(event: Dict[str, Any]) -> Dict[str, Any]:
    """Generate pre-signed URL for S3 object without requiring project_id"""
    import json
    from datetime import datetime, timezone
    
    try:
        # Get request body
        body = event.get('body')
        if not body:
            return create_validation_error_response("Request body is required")
        
        # Parse JSON body
        try:
            if isinstance(body, str):
                data = json.loads(body)
            else:
                data = body
        except json.JSONDecodeError:
            return create_validation_error_response("Invalid JSON format")
        
        # Get required parameters from request body
        index_id = data.get('index_id')
        s3_uri = data.get('s3_uri')
        
        if not s3_uri:
            return create_validation_error_response("s3_uri parameter is required")
        
        if not index_id:
            return create_validation_error_response("index_id parameter is required")
        
        # Validate S3 URI format
        if not s3_uri.startswith('s3://'):
            return create_validation_error_response("Invalid S3 URI format (s3://bucket/key)")
        
        # Security validation: Check if user has access to this S3 object
        try:
            # Extract bucket and key from S3 URI
            s3_parts = s3_uri.replace('s3://', '').split('/', 1)
            if len(s3_parts) != 2:
                return create_validation_error_response("Invalid S3 URI format")
            
            bucket_name, object_key = s3_parts
            
            # Security check: Verify the S3 object path contains the provided project_id
            if f"indexes/{index_id}/" not in object_key:
                logger.warning(f"Security check failed: index_id {index_id} not in S3 path: {object_key}")
                return create_validation_error_response("You do not have permission to access this resource")
            
            logger.info(f"Security check passed: index_id {index_id}, S3 URI: {s3_uri}")
            
        except Exception as e:
            logger.error(f"Failed to parse S3 URI or security check: {str(e)}")
            return create_validation_error_response("Failed to verify S3 URI")
        
        logger.info(f"Target for Pre-signed URL generation: {s3_uri} (index_id: {index_id})")
        
        # Get expiration time (default: 1 hour, max: 24 hours)
        expiration = data.get('expiration', 3600)
        if expiration > 86400:  # Max 24 hours
            expiration = 86400
        
        # Generate pre-signed URL using S3Service
        try:
            presigned_url = s3_service.generate_presigned_url(s3_uri, expiration=expiration)
            
            if not presigned_url:
                return create_internal_error_response("Failed to generate pre-signed URL")
            
            logger.info(f"Standalone Pre-signed URL generation successful: {presigned_url[:50]}...")
            
            # Prepare response data
            response_data = {
                "s3_uri": s3_uri,
                "presigned_url": presigned_url,
                "expiration_seconds": expiration,
                "expires_at": datetime.now(timezone.utc).timestamp() + expiration,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"✅ Standalone Pre-signed URL generation completed: {s3_uri}")
            return create_success_response(response_data)
            
        except Exception as e:
            logger.error(f"Failed to generate standalone Pre-signed URL: {str(e)}")
            return handle_lambda_error(e)
        
    except Exception as e:
        logger.error(f"Error handling standalone Pre-signed URL request: {str(e)}")
        return handle_lambda_error(e)


def handle_get_document_status(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle GET /api/documents/{document_id}/status request
    Returns document status including existence and total pages
    """
    logger = logging.getLogger()
    
    try:
        logger.info("🔍 Starting document status check")
        
        # Extract document ID from path parameters
        document_id = extract_path_parameter(event, 'document_id')
        if not document_id:
            logger.warning("Document ID not provided in path parameters")
            return create_validation_error_response("Document ID is required")
        
        # Validate document ID format
        if not validate_uuid(document_id):
            logger.warning(f"Invalid document ID format: {document_id}")
            return create_validation_error_response("Invalid document ID format")
        
        logger.info(f"📄 Checking status for document: {document_id}")
        
        # Check if document exists in DynamoDB using existing db_service
        try:
            logger.info(f"Querying DynamoDB documents table")
            document = db_service.get_item('documents', {'document_id': document_id})
            
            if not document:
                logger.info(f"Document {document_id} not found in DynamoDB")
                return create_not_found_response("Document not found")
            
            logger.info(f"Found document in DynamoDB: {document.get('file_name', 'unknown')}")
                
        except Exception as e:
            logger.error(f"Error checking document in DynamoDB: {str(e)}")
            return create_internal_error_response("Error checking document status")
        
        # Get data from DynamoDB document record
        total_pages = document.get('total_pages', 0)
        processing_status = document.get('status', 'unknown')
        
        # Get segment information from segments table
        segment_ids = []
        try:
            from boto3.dynamodb.conditions import Key
            segments_response = db_service.query_items(
                table_name='segments',
                key_condition_expression=Key('document_id').eq(document_id),
                index_name='DocumentIdIndex',
                scan_index_forward=True  # Sort ascending
            )
            
            if segments_response and segments_response.get('Items'):
                segment_ids = [item['segment_id'] for item in segments_response['Items']]
                logger.info(f"Found {len(segment_ids)} segments for document {document_id}")
            else:
                logger.warning(f"No segments found for document {document_id}")
                
        except Exception as e:
            logger.warning(f"Error getting segment IDs: {str(e)}")
            # Continue without segment data
        
        # Prepare status response
        status_data = {
            'document_id': document_id,
            'exists': True,
            'status': processing_status,
            'total_pages': total_pages,
            'segment_ids': segment_ids,
            'total_segments': len(segment_ids),
            'file_name': document.get('file_name', ''),
            'file_size': document.get('file_size', 0),
            'media_type': document.get('media_type', ''),
            'created_at': document.get('created_at', ''),
            'updated_at': document.get('updated_at', ''),
            'checked_at': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"✅ Document status check completed for {document_id}: {total_pages} pages, status: {processing_status}")
        return create_success_response(status_data)
        
    except Exception as e:
        logger.error(f"Error handling document status request: {str(e)}")
        return handle_lambda_error(e)
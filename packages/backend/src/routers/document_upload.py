"""
Document Upload Router
Handles direct file uploads to S3 through backend
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import boto3
from botocore.exceptions import ClientError
import os
import uuid
from typing import Optional
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/documents",
    tags=["documents"]
)

# AWS clients initialization
try:
    s3_client = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    
    BUCKET_NAME = os.environ.get('DOCUMENTS_BUCKET_NAME', 'aws-idp-ai-documents-383137109840-us-west-2-dev')
    DOCUMENTS_TABLE = os.environ.get('DOCUMENTS_TABLE_NAME', 'documents')
    
    documents_table = dynamodb.Table(DOCUMENTS_TABLE)
except Exception as e:
    logger.error(f"Failed to initialize AWS clients: {str(e)}")
    s3_client = None
    dynamodb = None
    documents_table = None
    BUCKET_NAME = None

def infer_media_type(file_type: str, file_name: str) -> str:
    """Infer media type for pipeline branching"""
    if not file_type and file_name:
        ext = os.path.splitext(file_name.lower())[1]
        file_type_map = {
            '.pdf': 'application/pdf',
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.mp4': 'video/mp4',
            '.mp3': 'audio/mpeg'
        }
        file_type = file_type_map.get(ext, 'application/octet-stream')
    
    if file_type and file_type.startswith('image/'):
        return 'IMAGE'
    elif file_type and file_type.startswith('video/'):
        return 'VIDEO'  
    elif file_type and file_type.startswith('audio/'):
        return 'AUDIO'
    elif file_type == 'application/pdf':
        return 'DOCUMENT'
    else:
        return 'DOCUMENT'



@router.post("/backend-upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    index_id: str = Form(...),
    description: Optional[str] = Form(None)
):
    """
    Upload document directly through backend
    No CORS issues, no size limits (within ECS limits)
    Requires can_upload_documents permission
    """
    # Permission check
    from src.dependencies.permissions import get_user_permissions
    permissions = await get_user_permissions(request)

    if not permissions.get("can_upload_documents", False):
        logger.warning(f"Upload permission denied for user")
        raise HTTPException(status_code=403, detail="Permission denied: can_upload_documents required")

    # Index access check
    accessible = permissions.get("accessible_indexes", [])
    if accessible != "*" and (not isinstance(accessible, list) or index_id not in accessible):
        logger.warning(f"Index access denied: {index_id}")
        raise HTTPException(status_code=403, detail=f"Access denied to index: {index_id}")    
    if not s3_client or not BUCKET_NAME:
        logger.error("S3 client or bucket name not initialized")
        raise HTTPException(status_code=500, detail="S3 client not properly configured")
    
    try:
        # Generate document ID and S3 key with sanitized filename
        from .common.utils import sanitize_filename
        document_id = str(uuid.uuid4())
        safe_filename = sanitize_filename(file.filename or 'unknown_file')
        s3_key = f"indexes/{index_id}/documents/{document_id}/{safe_filename}"
        
        # Read and upload file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Encode non-ASCII metadata values for S3 compatibility
        import base64
        original_filename_encoded = base64.b64encode((file.filename or 'unknown').encode('utf-8')).decode('ascii')
        description_encoded = base64.b64encode((description or '').encode('utf-8')).decode('ascii')
        
        response = s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=file_content,
            ContentType=file.content_type or 'application/octet-stream',
            ServerSideEncryption='AES256',
            Metadata={
                'index_id': index_id,
                'document_id': document_id,
                'original_filename_b64': original_filename_encoded,  # Base64 encoded
                'description_b64': description_encoded,  # Base64 encoded
                'safe_filename': safe_filename  # ASCII-safe filename
            }
        )
        
        # Create DynamoDB record
        file_uri = f"s3://{BUCKET_NAME}/{s3_key}"
        current_time = datetime.now(timezone.utc).isoformat()
        media_type = infer_media_type(file.content_type or '', file.filename or '')
        
        if documents_table:
            document_item = {
                'document_id': document_id,
                'index_id': index_id,
                'file_name': file.filename or 'unknown',
                'safe_file_name': safe_filename,  # BDA-compatible filename
                'file_type': file.content_type or 'application/octet-stream',
                'file_size': file_size,
                'file_uri': file_uri,
                'status': 'pending_upload',  # Lambda expects this status
                'media_type': media_type,
                'description': description or '',
                'summary': '',
                'total_pages': 0,
                'created_at': current_time,
                'updated_at': current_time,
                'statistics': {
                    'table_count': 0,
                    'figure_count': 0,
                    'hyperlink_count': 0,
                    'element_count': 0
                },
                'representation': {
                    'markdown': ''
                }
            }
            
            try:
                documents_table.put_item(Item=document_item)
                logger.info(f"Document record created: {document_id}")
            except Exception as e:
                logger.error(f"Failed to create DynamoDB record: {str(e)}")
        
        # Call Lambda upload-complete endpoint to trigger workflow
        try:
            import requests
            import json as json_lib
            
            # Get API Gateway URL from environment
            api_base_url = os.environ.get('API_BASE_URL')
            if api_base_url:
                upload_complete_url = f"{api_base_url}/api/documents/{document_id}/upload-complete"
                
                # Call the upload-complete Lambda endpoint
                response = requests.post(
                    upload_complete_url,
                    json={},  # Empty body as Lambda expects
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                
                if response.status_code == 200:
                    logger.info(f"Upload complete callback successful: {document_id}")
                else:
                    logger.error(f"Upload complete callback failed: {response.status_code} - {response.text}")
            else:
                logger.warning("API_BASE_URL not set, skipping upload-complete callback")
                
        except Exception as e:
            logger.error(f"Failed to call upload-complete: {str(e)}")
            # Don't fail the upload if callback fails, but log the error
        
        response_data = {
            "success": True,
            "document_id": document_id,
            "index_id": index_id,
            "file_name": file.filename,
            "file_size": file_size,
            "file_uri": file_uri,
            "status": "uploaded",
            "message": "File uploaded successfully through backend"
        }
        
        return JSONResponse(status_code=200, content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/backend-upload-chunked")
async def upload_document_chunked(
    file: UploadFile = File(...),
    index_id: str = Form(...),
    description: Optional[str] = Form(None),
    chunk_size: int = Form(default=5 * 1024 * 1024)  # 5MB chunks
):
    """
    Upload large document with streaming
    Handles files of any size efficiently
    """
    if not s3_client or not BUCKET_NAME:
        logger.error("S3 client or bucket name not initialized")
        raise HTTPException(status_code=500, detail="S3 client not properly configured")

    try:
        # Generate document ID and sanitize filename
        from .common.utils import sanitize_filename
        document_id = str(uuid.uuid4())
        safe_filename = sanitize_filename(file.filename or 'unknown_file')

        # Create S3 key
        s3_key = f"indexes/{index_id}/documents/{document_id}/{safe_filename}"

        # Encode metadata for S3 compatibility
        import base64
        original_filename_encoded = base64.b64encode((file.filename or 'unknown').encode('utf-8')).decode('ascii')
        description_encoded = base64.b64encode((description or '').encode('utf-8')).decode('ascii')

        # Initiate multipart upload with metadata
        multipart_upload = s3_client.create_multipart_upload(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            ContentType=file.content_type or 'application/octet-stream',
            ServerSideEncryption='AES256',
            Metadata={
                'index_id': index_id,
                'document_id': document_id,
                'original_filename_b64': original_filename_encoded,
                'description_b64': description_encoded,
                'safe_filename': safe_filename
            }
        )
        upload_id = multipart_upload['UploadId']
        
        parts = []
        part_number = 1
        total_size = 0
        
        try:
            # Stream upload in chunks
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                
                # Upload part
                part_response = s3_client.upload_part(
                    Bucket=BUCKET_NAME,
                    Key=s3_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk
                )
                
                parts.append({
                    'ETag': part_response['ETag'],
                    'PartNumber': part_number
                })
                
                total_size += len(chunk)
                part_number += 1
                
                logger.info(f"Uploaded part {part_number - 1}, total size: {total_size}")
            
            # Complete multipart upload
            s3_client.complete_multipart_upload(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            file_uri = f"s3://{BUCKET_NAME}/{s3_key}"

            # Create DynamoDB record for large file
            current_time = datetime.now(timezone.utc).isoformat()
            media_type = infer_media_type(file.content_type or '', file.filename or '')

            if documents_table:
                document_item = {
                    'document_id': document_id,
                    'index_id': index_id,
                    'file_name': file.filename or 'unknown',
                    'safe_file_name': safe_filename,
                    'file_type': file.content_type or 'application/octet-stream',
                    'file_size': total_size,
                    'file_uri': file_uri,
                    'status': 'pending_upload',  # Lambda expects this status
                    'media_type': media_type,
                    'description': description or '',
                    'summary': '',
                    'total_pages': 0,
                    'created_at': current_time,
                    'updated_at': current_time,
                    'statistics': {
                        'table_count': 0,
                        'figure_count': 0,
                        'hyperlink_count': 0,
                        'element_count': 0
                    },
                    'representation': {
                        'markdown': ''
                    }
                }

                try:
                    documents_table.put_item(Item=document_item)
                    logger.info(f"Document record created for large file: {document_id}")
                except Exception as e:
                    logger.error(f"Failed to create DynamoDB record: {str(e)}")

            # Call Lambda upload-complete endpoint to trigger workflow
            try:
                import requests
                import json as json_lib

                # Get API Gateway URL from environment
                api_base_url = os.environ.get('API_BASE_URL')
                if api_base_url:
                    upload_complete_url = f"{api_base_url}/api/documents/{document_id}/upload-complete"

                    # Call the upload-complete Lambda endpoint
                    response = requests.post(
                        upload_complete_url,
                        json={},  # Empty body as Lambda expects
                        headers={'Content-Type': 'application/json'},
                        timeout=30
                    )

                    if response.status_code == 200:
                        logger.info(f"Upload complete callback successful for large file: {document_id}")
                    else:
                        logger.error(f"Upload complete callback failed: {response.status_code} - {response.text}")
                else:
                    logger.warning("API_BASE_URL not set, skipping upload-complete callback")

            except Exception as e:
                logger.error(f"Failed to call upload-complete for large file: {str(e)}")
                # Don't fail the upload if callback fails, but log the error

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "document_id": document_id,
                    "index_id": index_id,
                    "file_name": file.filename,
                    "file_size": total_size,
                    "file_uri": file_uri,
                    "parts_uploaded": len(parts),
                    "status": "uploaded",
                    "message": "Large file uploaded successfully through backend"
                }
            )
            
        except Exception as e:
            # Abort multipart upload on error
            s3_client.abort_multipart_upload(
                Bucket=BUCKET_NAME,
                Key=s3_key,
                UploadId=upload_id
            )
            raise e
            
    except Exception as e:
        logger.error(f"Chunked upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
"""
S3 Service for unified S3 operations across all Lambda functions.
"""

import boto3
import os
import tempfile
from typing import Dict, List, Any, Optional, Union, Tuple
from urllib.parse import urlparse, unquote
import logging
from botocore.exceptions import ClientError
from PIL import Image
import io
import base64

from .aws_clients import AWSClientFactory

logger = logging.getLogger(__name__)


class S3Service:
    """Unified service for all S3 operations."""
    
    def __init__(self, region: Optional[str] = None, timeout: int = 3600):
        self.region = region or os.environ.get('AWS_REGION', 'us-west-2')
        self.s3_client = AWSClientFactory.get_s3_client(region, timeout)
        
        # Get bucket names from environment
        self.documents_bucket = AWSClientFactory.get_bucket_name('documents')
        if not self.documents_bucket:
            logger.warning("Documents bucket name not configured")
    
    def parse_s3_uri(self, s3_uri: str) -> Tuple[str, str]:
        """Parse S3 URI into bucket and key components."""
        try:
            if s3_uri.startswith('s3://'):
                # Remove s3:// prefix
                path = s3_uri[5:]
                parts = path.split('/', 1)
                if len(parts) == 2:
                    return parts[0], parts[1]
                elif len(parts) == 1:
                    return parts[0], ''
            
            # If not S3 URI format, assume it's just a key
            return self.documents_bucket, s3_uri
            
        except Exception as e:
            logger.error(f"Failed to parse S3 URI '{s3_uri}': {str(e)}")
            return '', s3_uri
    
    def upload_file(self, 
                   file_content: Union[bytes, str, io.IOBase],
                   s3_key: str,
                   bucket_name: Optional[str] = None,
                   content_type: Optional[str] = None,
                   metadata: Optional[Dict[str, str]] = None) -> str:
        """Upload file content to S3."""
        try:
            bucket_name = bucket_name or self.documents_bucket
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            kwargs = {
                'Bucket': bucket_name,
                'Key': s3_key,
                'Body': file_content
            }
            
            if content_type:
                kwargs['ContentType'] = content_type
            
            if metadata:
                kwargs['Metadata'] = metadata
            
            response = self.s3_client.put_object(**kwargs)
            
            s3_uri = f"s3://{bucket_name}/{s3_key}"
            logger.info(f"Uploaded file to S3: {s3_uri}")
            return s3_uri
            
        except Exception as e:
            logger.error(f"Failed to upload file to S3: {str(e)}")
            raise
    
    def download_file(self, 
                     s3_uri_or_key: str,
                     local_path: Optional[str] = None,
                     bucket_name: Optional[str] = None) -> str:
        """Download file from S3 to local path."""
        try:
            # Parse S3 URI
            if s3_uri_or_key.startswith('s3://'):
                bucket_name, s3_key = self.parse_s3_uri(s3_uri_or_key)
            else:
                bucket_name = bucket_name or self.documents_bucket
                s3_key = s3_uri_or_key
            
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            # Create temp file if no local path provided
            if not local_path:
                suffix = os.path.splitext(s3_key)[1]
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                local_path = temp_file.name
                temp_file.close()
            
            # Download file
            self.s3_client.download_file(bucket_name, s3_key, local_path)
            
            logger.info(f"Downloaded S3 file to: {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"Failed to download file from S3: {str(e)}")
            raise
    
    def get_object(self, 
                  s3_uri_or_key: str,
                  bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """Get object content from S3."""
        try:
            # Parse S3 URI
            if s3_uri_or_key.startswith('s3://'):
                bucket_name, s3_key = self.parse_s3_uri(s3_uri_or_key)
            else:
                bucket_name = bucket_name or self.documents_bucket
                s3_key = s3_uri_or_key
            
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            response = self.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            
            logger.info(f"Retrieved object from S3: s3://{bucket_name}/{s3_key}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to get object from S3: {str(e)}")
            raise
    
    def delete_object(self, 
                     s3_uri_or_key: str,
                     bucket_name: Optional[str] = None) -> bool:
        """Delete object from S3."""
        try:
            # Parse S3 URI
            if s3_uri_or_key.startswith('s3://'):
                bucket_name, s3_key = self.parse_s3_uri(s3_uri_or_key)
            else:
                bucket_name = bucket_name or self.documents_bucket
                s3_key = s3_uri_or_key
            
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            self.s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
            
            logger.info(f"Deleted object from S3: s3://{bucket_name}/{s3_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete object from S3: {str(e)}")
            raise
    
    def delete_objects(self, 
                      s3_keys: List[str],
                      bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """Delete multiple objects from S3."""
        try:
            bucket_name = bucket_name or self.documents_bucket
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            if not s3_keys:
                return {'Deleted': [], 'Errors': []}
            
            # Prepare delete request
            delete_objects = [{'Key': key} for key in s3_keys]
            
            response = self.s3_client.delete_objects(
                Bucket=bucket_name,
                Delete={'Objects': delete_objects}
            )
            
            deleted_count = len(response.get('Deleted', []))
            error_count = len(response.get('Errors', []))
            
            logger.info(f"Batch deleted {deleted_count} objects, {error_count} errors")
            return response
            
        except Exception as e:
            logger.error(f"Failed to batch delete objects: {str(e)}")
            raise
    
    def list_objects(self, 
                    prefix: str = "",
                    bucket_name: Optional[str] = None,
                    max_keys: int = 1000) -> List[Dict[str, Any]]:
        """List objects in S3 bucket with optional prefix."""
        try:
            bucket_name = bucket_name or self.documents_bucket
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            objects = []
            continuation_token = None
            
            while True:
                kwargs = {
                    'Bucket': bucket_name,
                    'Prefix': prefix,
                    'MaxKeys': min(max_keys - len(objects), 1000)
                }
                
                if continuation_token:
                    kwargs['ContinuationToken'] = continuation_token
                
                response = self.s3_client.list_objects_v2(**kwargs)
                
                objects.extend(response.get('Contents', []))
                
                # Check if we have more objects or reached max_keys
                if not response.get('IsTruncated', False) or len(objects) >= max_keys:
                    break
                
                continuation_token = response.get('NextContinuationToken')
            
            logger.info(f"Listed {len(objects)} objects with prefix: {prefix}")
            return objects[:max_keys]
            
        except Exception as e:
            logger.error(f"Failed to list objects: {str(e)}")
            raise
    
    def generate_presigned_url(self, 
                              s3_uri_or_key: str,
                              bucket_name: Optional[str] = None,
                              expiration: int = 3600,
                              method: str = 'get_object') -> str:
        """Generate presigned URL for S3 object."""
        try:
            # Parse S3 URI
            if s3_uri_or_key.startswith('s3://'):
                bucket_name, s3_key = self.parse_s3_uri(s3_uri_or_key)
            else:
                bucket_name = bucket_name or self.documents_bucket
                s3_key = s3_uri_or_key
            
            if not bucket_name or not s3_key:
                raise ValueError("Both bucket name and key are required")
            
            # Check if object exists
            try:
                self.s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.warning(f"Object not found: s3://{bucket_name}/{s3_key}")
                    return ""
                raise
            
            # Generate presigned URL
            url = self.s3_client.generate_presigned_url(
                method,
                Params={'Bucket': bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated presigned URL for: s3://{bucket_name}/{s3_key}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return ""
    
    def copy_object(self, 
                   source_uri: str,
                   destination_key: str,
                   destination_bucket: Optional[str] = None,
                   source_bucket: Optional[str] = None) -> str:
        """Copy object within S3."""
        try:
            # Parse source
            if source_uri.startswith('s3://'):
                source_bucket, source_key = self.parse_s3_uri(source_uri)
            else:
                source_bucket = source_bucket or self.documents_bucket
                source_key = source_uri
            
            destination_bucket = destination_bucket or self.documents_bucket
            
            if not source_bucket or not destination_bucket:
                raise ValueError("Source and destination bucket names are required")
            
            copy_source = {'Bucket': source_bucket, 'Key': source_key}
            
            self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=destination_bucket,
                Key=destination_key
            )
            
            destination_uri = f"s3://{destination_bucket}/{destination_key}"
            logger.info(f"Copied object to: {destination_uri}")
            return destination_uri
            
        except Exception as e:
            logger.error(f"Failed to copy object: {str(e)}")
            raise
    
    def get_object_metadata(self, 
                           s3_uri_or_key: str,
                           bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """Get object metadata without downloading content."""
        try:
            # Parse S3 URI
            if s3_uri_or_key.startswith('s3://'):
                bucket_name, s3_key = self.parse_s3_uri(s3_uri_or_key)
            else:
                bucket_name = bucket_name or self.documents_bucket
                s3_key = s3_uri_or_key
            
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            response = self.s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            
            metadata = {
                'size': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'content_type': response.get('ContentType', ''),
                'etag': response.get('ETag', '').strip('"'),
                'metadata': response.get('Metadata', {})
            }
            
            logger.info(f"Retrieved metadata for: s3://{bucket_name}/{s3_key}")
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get object metadata: {str(e)}")
            raise
    
    def object_exists(self, 
                     s3_uri_or_key: str,
                     bucket_name: Optional[str] = None) -> bool:
        """Check if object exists in S3."""
        try:
            self.get_object_metadata(s3_uri_or_key, bucket_name)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
        except Exception:
            return False
    
    def download_image_as_base64(self, 
                                s3_uri_or_key: str,
                                bucket_name: Optional[str] = None,
                                max_size: Tuple[int, int] = (1024, 1024)) -> str:
        """Download image from S3 and return as base64 string with optional resizing."""
        try:
            # Get image from S3
            response = self.get_object(s3_uri_or_key, bucket_name)
            image_data = response['Body'].read()
            
            # Open image with PIL
            image = Image.open(io.BytesIO(image_data))
            
            # Resize if larger than max_size
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized image from {image.size} to {max_size}")
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Save to bytes buffer
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            image_bytes = buffer.getvalue()
            
            # Convert to base64
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            
            logger.info(f"Downloaded and converted image to base64: {len(base64_string)} chars")
            return base64_string
            
        except Exception as e:
            logger.error(f"Failed to download image as base64: {str(e)}")
            raise
    
    def delete_objects_with_prefix(self, 
                                  prefix: str,
                                  bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """Delete all objects with given prefix (directory deletion)."""
        try:
            # Parse S3 URI if prefix starts with s3://
            if prefix.startswith('s3://'):
                bucket_name, prefix = self.parse_s3_uri(prefix)
                # Remove trailing slash if present to get proper prefix
                prefix = prefix.rstrip('/')
                # Add back trailing slash for prefix matching
                prefix = prefix + '/'
            else:
                bucket_name = bucket_name or self.documents_bucket
                # Ensure prefix ends with / for directory-like matching
                if not prefix.endswith('/'):
                    prefix = prefix + '/'
            
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            # List all objects with prefix
            objects = self.list_objects(prefix, bucket_name)
            
            if not objects:
                logger.info(f"No files found with prefix: {prefix}")
                return {'deleted_count': 0, 'errors': []}
            
            # Extract keys for batch deletion
            object_keys = [obj['Key'] for obj in objects]
            
            # Batch delete in chunks of 1000 (S3 limit)
            deleted_count = 0
            errors = []
            
            for i in range(0, len(object_keys), 1000):
                chunk = object_keys[i:i+1000]
                try:
                    response = self.delete_objects(chunk, bucket_name)
                    deleted_count += len(response.get('Deleted', []))
                    errors.extend(response.get('Errors', []))
                except Exception as e:
                    logger.error(f"Failed to delete chunk: {str(e)}")
                    errors.append({'Error': str(e)})
            
            logger.info(f"Deleted {deleted_count} files with prefix '{prefix}', {len(errors)} errors")
            return {'deleted_count': deleted_count, 'errors': errors}
            
        except Exception as e:
            logger.error(f"Failed to delete objects with prefix: {str(e)}")
            raise

    def cleanup_project_files(self, project_id: str) -> Dict[str, Any]:
        """Delete all files associated with a project."""
        try:
            prefix = f"projects/{project_id}/"
            return self.delete_objects_with_prefix(prefix)
            
        except Exception as e:
            logger.error(f"Failed to cleanup project files: {str(e)}")
            raise
    
    def handle_generate_presigned_url_request(self, event: dict) -> dict:
        """Handle pre-signed URL generation request."""
        from .utils import (
            extract_path_parameter, 
            extract_query_parameter, 
            validate_uuid,
            create_success_response, 
            create_validation_error_response, 
            create_internal_error_response,
            handle_lambda_error
        )
        
        try:
            project_id = extract_path_parameter(event, 'project_id')
            
            if not project_id:
                return create_validation_error_response("project_id가 필요합니다")
            
            if not validate_uuid(project_id):
                return create_validation_error_response("유효하지 않은 project_id 형식입니다")
            
            # Get S3 key from query parameters
            s3_key = extract_query_parameter(event, 's3_key')
            
            if not s3_key:
                return create_validation_error_response("s3_key가 필요합니다")
            
            # Generate pre-signed URL
            try:
                presigned_url = self.generate_presigned_url(s3_key)
                
                if not presigned_url:
                    return create_internal_error_response("Pre-signed URL 생성에 실패했습니다")
                
                response_data = {
                    "presigned_url": presigned_url,
                    "s3_key": s3_key,
                    "project_id": project_id
                }
                
                return create_success_response(response_data)
                
            except Exception as e:
                logger.error(f"Pre-signed URL 생성 실패: {str(e)}")
                return handle_lambda_error(e)
            
        except Exception as e:
            logger.error(f"Pre-signed URL 요청 처리 오류: {str(e)}")
            return handle_lambda_error(e)
    
    def get_object_metadata(self, 
                           s3_uri_or_key: str,
                           bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """Get S3 object metadata."""
        try:
            # Parse S3 URI
            if s3_uri_or_key.startswith('s3://'):
                bucket_name, s3_key = self.parse_s3_uri(s3_uri_or_key)
            else:
                bucket_name = bucket_name or self.documents_bucket
                s3_key = s3_uri_or_key
            
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            # Get object metadata
            response = self.s3_client.head_object(
                Bucket=bucket_name,
                Key=s3_key
            )
            
            logger.debug(f"Retrieved metadata for {s3_key}")
            return response
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"Object not found: {s3_key}")
                return {}
            logger.error(f"Failed to get object metadata: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to get object metadata: {str(e)}")
            raise
    
    def get_original_filename(self, 
                             s3_uri_or_key: str,
                             bucket_name: Optional[str] = None) -> Optional[str]:
        """Get original filename from S3 object metadata (URL-decoded)."""
        try:
            metadata = self.get_object_metadata(s3_uri_or_key, bucket_name)
            
            if not metadata:
                return None
            
            # Get original_name from metadata and URL-decode it
            original_name = metadata.get('Metadata', {}).get('original_name')
            
            if original_name:
                # URL-decode the filename
                return unquote(original_name)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get original filename: {str(e)}")
            return None
    
    def generate_presigned_url_with_filename(self, 
                                           s3_uri_or_key: str,
                                           bucket_name: Optional[str] = None,
                                           expiration: int = 3600,
                                           use_original_filename: bool = True) -> str:
        """Generate presigned URL with original filename for downloads."""
        try:
            # Parse S3 URI
            if s3_uri_or_key.startswith('s3://'):
                bucket_name, s3_key = self.parse_s3_uri(s3_uri_or_key)
            else:
                bucket_name = bucket_name or self.documents_bucket
                s3_key = s3_uri_or_key
            
            if not bucket_name:
                raise ValueError("Bucket name is required")
            
            params = {
                'Bucket': bucket_name,
                'Key': s3_key
            }
            
            # Try to get original filename if requested
            if use_original_filename:
                original_filename = self.get_original_filename(s3_uri_or_key, bucket_name)
                if original_filename:
                    # Set Content-Disposition header to force download with original filename
                    params['ResponseContentDisposition'] = f'attachment; filename="{original_filename}"'
            
            # Generate presigned URL
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params=params,
                ExpiresIn=expiration
            )
            
            logger.debug(f"Generated presigned URL for {s3_key}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate presigned URL with filename: {str(e)}")
            # Fallback to regular presigned URL
            return self.generate_presigned_url(s3_uri_or_key, bucket_name, expiration)
    
    def generate_presigned_url_for_upload(self, 
                                        s3_key: str,
                                        bucket_name: Optional[str] = None,
                                        content_type: Optional[str] = None,
                                        expiration: int = 3600) -> str:
        """Generate presigned URL for uploading files to S3."""
        try:
            bucket_name = bucket_name or self.documents_bucket
            if not bucket_name or not s3_key:
                raise ValueError("Both bucket name and key are required")
            
            # Prepare parameters for presigned URL
            params = {
                'Bucket': bucket_name,
                'Key': s3_key
            }
            
            # Add content type if provided
            if content_type:
                params['ContentType'] = content_type
            
            # Generate presigned URL for PUT operation
            url = self.s3_client.generate_presigned_url(
                'put_object',
                Params=params,
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated presigned upload URL for: s3://{bucket_name}/{s3_key}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate presigned upload URL: {str(e)}")
            return ""
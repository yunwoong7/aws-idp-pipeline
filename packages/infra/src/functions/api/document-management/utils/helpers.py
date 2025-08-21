"""
Document management helper utility
"""

import base64
import tempfile
import logging
from typing import Dict, Any, Optional, List
import PyPDF2
import boto3
from botocore.exceptions import ClientError
from datetime import datetime

logger = logging.getLogger()


def decode_base64_file(file_content: str, file_name: str) -> bytes:
    """Decode Base64 encoded file"""
    try:
        # Base64 decoding
        file_data = base64.b64decode(file_content)
        logger.info(f"File decoding successful: {file_name}, size: {len(file_data)} bytes")
        return file_data
    except Exception as e:
        logger.error(f"Base64 decoding failed: {file_name}, error: {str(e)}")
        raise


def get_pdf_page_count(file_data: bytes) -> int:
    """Return page count of PDF file"""
    try:
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(file_data)
            temp_file.flush()
            
            with open(temp_file.name, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                page_count = len(pdf_reader.pages)
                logger.info(f"PDF page count: {page_count}")
                return page_count
    except Exception as e:
        logger.error(f"PDF page count check failed: {str(e)}")
        return 1  # Return 1 page as default


def generate_s3_key(index_id: str, doc_id: str, file_name: str) -> str:
    """Generate S3 key for an object under an index workspace"""
    return f"indexes/{index_id}/documents/{doc_id}/{file_name}"


def generate_page_image_url(bucket_name: str, project_id: str, doc_id: str, page_number: int) -> str:
    """Generate page image URL"""
    key = f"projects/{project_id}/documents/{doc_id}/images/page_{page_number}.png"
    return f"https://{bucket_name}.s3.amazonaws.com/{key}"


def extract_s3_bucket_and_key(s3_uri: str) -> tuple[str, str]:
    """Extract bucket and key from S3 URI (s3://bucket/key -> (bucket, key))"""
    if s3_uri.startswith('s3://'):
        # s3://bucket-name/path/to/file -> (bucket-name, path/to/file)
        parts = s3_uri[5:].split('/', 1)  # Remove 's3://' and split once
        if len(parts) == 2:
            return parts[0], parts[1]  # Return bucket and key
        elif len(parts) == 1:
            return parts[0], ''  # Return bucket with empty key
    return '', s3_uri  # Return empty bucket with original string as key


def extract_s3_key_from_uri(s3_uri: str) -> str:
    """Extract key from S3 URI (s3://bucket/key -> key)"""
    _, key = extract_s3_bucket_and_key(s3_uri)
    return key


def generate_presigned_url(s3_client, bucket_name: str, s3_key_or_uri: str, expiration: int = 3600) -> Optional[str]:
    """Generate S3 Pre-signed URL (supports both S3 URI and key)"""
    try:
        # Extract bucket and key from S3 URI
        if s3_key_or_uri.startswith('s3://'):
            extracted_bucket, s3_key = extract_s3_bucket_and_key(s3_key_or_uri)
            # Use extracted bucket name if available, otherwise use parameter bucket name
            actual_bucket = extracted_bucket if extracted_bucket else bucket_name
        else:
            actual_bucket = bucket_name
            s3_key = s3_key_or_uri
        
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': actual_bucket, 'Key': s3_key},
            ExpiresIn=expiration
        )
        logger.info(f"Pre-signed URL created successfully: s3://{actual_bucket}/{s3_key}")
        return url
    except ClientError as e:
        logger.error(f"Pre-signed URL creation failed: {s3_key_or_uri}, error: {str(e)}")
        return None

def validate_file_extension(file_name: str, allowed_extensions: List[str] = None) -> bool:
    """Validate file extension"""
    if allowed_extensions is None:
        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    
    file_extension = file_name.lower().split('.')[-1]
    return f".{file_extension}" in [ext.lower() for ext in allowed_extensions]


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"
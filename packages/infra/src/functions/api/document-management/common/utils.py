"""
Common utility functions for Lambda Layer.
"""

import os
import uuid
import logging
import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Generator
from decimal import Decimal


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """Parse S3 URI into bucket and key components."""
    if s3_uri.startswith('s3://'):
        # Remove s3:// prefix
        path = s3_uri[5:]
        parts = path.split('/', 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        elif len(parts) == 1:
            return parts[0], ''
    
    # If not S3 URI format, return empty bucket and the original string as key
    return '', s3_uri


def setup_logging(level: str = 'INFO') -> logging.Logger:
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def handle_lambda_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Handle Lambda function errors with standardized response format."""
    error_response = {
        'statusCode': 500,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'error': True,
            'message': str(error),
            'type': type(error).__name__
        })
    }
    
    if context:
        error_response['body'] = json.dumps({
            'error': True,
            'message': str(error),
            'type': type(error).__name__,
            'context': context
        })
    
    logging.error(f"Lambda error: {str(error)}", exc_info=True)
    return error_response


def create_success_response(data: Any, status_code: int = 200) -> Dict[str, Any]:
    """Create standardized success response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(data, default=decimal_default)
    }


def decimal_default(obj):
    """JSON serializer for Decimal objects."""
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def extract_path_parameter(event: Dict[str, Any], parameter_name: str) -> Optional[str]:
    """Extract path parameter from Lambda event."""
    path_parameters = event.get('pathParameters', {})
    if path_parameters:
        return path_parameters.get(parameter_name)
    return None


def extract_query_parameter(event: Dict[str, Any], parameter_name: str) -> Optional[str]:
    """Extract query parameter from Lambda event."""
    query_parameters = event.get('queryStringParameters', {})
    if query_parameters:
        return query_parameters.get(parameter_name)
    return None


def extract_request_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and parse request body from Lambda event."""
    body = event.get('body', '{}')
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    return body if isinstance(body, dict) else {}


def get_environment_variable(name: str, default: Optional[str] = None, required: bool = False) -> str:
    """Get environment variable with validation."""
    value = os.environ.get(name, default)
    
    if required and not value:
        raise ValueError(f"Required environment variable '{name}' is not set")
    
    return value or ""


def validate_uuid(uuid_string: str) -> bool:
    """Validate if string is a valid UUID."""
    try:
        uuid.UUID(uuid_string)
        return True
    except ValueError:
        return False


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for BDA compatibility and safe storage."""
    import re
    import os
    
    # Get file extension
    name, ext = os.path.splitext(filename)
    
    # Remove or replace unsafe characters for BDA compatibility
    # BDA requires strict S3 URI patterns, so we'll be very conservative
    # Allow only alphanumeric, dots, hyphens, and underscores
    name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
    ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)  # Extensions should be clean
    
    # Remove consecutive underscores
    name = re.sub(r'_{2,}', '_', name)
    
    # Remove leading/trailing underscores and dots
    name = name.strip('_.')
    
    # Ensure name is not empty
    if not name:
        name = "file"
    
    # Limit total length (BDA has URI length limits)
    max_length = 100  # Conservative limit for BDA
    if len(name + ext) > max_length:
        name = name[:max_length-len(ext)]
    
    # Ensure the name starts and ends with alphanumeric (BDA pattern requirement)
    if name and not name[0].isalnum():
        name = 'f' + name[1:]
    if name and not name[-1].isalnum():
        name = name[:-1] + 'e'
    
    return name + ext


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def chunk_list(lst: list, chunk_size: int) -> Generator[list, None, None]:
    """Split list into chunks of specified size."""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def deep_merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result


def get_request_id(event: Dict[str, Any]) -> str:
    """Extract request ID from Lambda event."""
    # Try to get from request context
    request_context = event.get('requestContext', {})
    request_id = request_context.get('requestId', '')
    
    if not request_id:
        # Generate new request ID if not found
        request_id = generate_uuid()
    
    return request_id



def is_valid_document_id(document_id: str) -> bool:
    """Validate document ID format."""
    return bool(document_id and len(document_id) > 0 and validate_uuid(document_id))


def get_content_type_from_filename(filename: str) -> str:
    """Get content type based on file extension."""
    extension = os.path.splitext(filename)[1].lower()
    
    content_types = {
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.txt': 'text/plain',
        '.json': 'application/json',
        '.csv': 'text/csv',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    }
    
    return content_types.get(extension, 'application/octet-stream')


def calculate_md5_hash(content: bytes) -> str:
    """Calculate MD5 hash of content."""
    import hashlib
    return hashlib.md5(content).hexdigest()


def retry_with_backoff(func, max_retries: int = 3, backoff_factor: float = 2.0, exceptions: tuple = (Exception,)):
    """Retry function with exponential backoff."""
    import time
    
    def wrapper(*args, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                if attempt == max_retries - 1:
                    raise
                
                wait_time = backoff_factor ** attempt
                logging.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
    
    return wrapper


def truncate_text(text: str, max_length: int = 1000, suffix: str = "...") -> str:
    """Truncate text to specified length."""
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def create_validation_error_response(message: str) -> Dict[str, Any]:
    """Create validation error response."""
    return {
        'statusCode': 400,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'error': True,
            'message': message,
            'type': 'ValidationError'
        })
    }


def create_internal_error_response(message: str) -> Dict[str, Any]:
    """Create internal server error response."""
    return {
        'statusCode': 500,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'error': True,
            'message': message,
            'type': 'InternalServerError'
        })
    }
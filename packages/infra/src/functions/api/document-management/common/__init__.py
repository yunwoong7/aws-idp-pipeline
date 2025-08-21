"""
Common utilities for AWS IDP AI Analysis Lambda functions.

This package provides shared services for DynamoDB, OpenSearch, and S3 operations
to reduce code duplication and improve maintainability across Lambda functions.
"""

from .aws_clients import AWSClientFactory
from .dynamodb_service import DynamoDBService
from .opensearch_service import OpenSearchService
from .s3_service import S3Service

from .utils import (
    get_current_timestamp,
    parse_s3_uri,
    generate_uuid,
    setup_logging,
    handle_lambda_error,
    create_success_response,
    create_validation_error_response,
    create_internal_error_response,
    extract_path_parameter,
    extract_query_parameter,
    validate_uuid,
    sanitize_filename
)

__version__ = "1.0.0"

__all__ = [
    "AWSClientFactory",
    "DynamoDBService", 
    "OpenSearchService",
    "S3Service",
    "get_current_timestamp",
    "parse_s3_uri",
    "generate_uuid",
    "setup_logging",
    "handle_lambda_error",
    "create_success_response",
    "create_validation_error_response",
    "create_internal_error_response",
    "extract_path_parameter",
    "extract_query_parameter",
    "validate_uuid",
    "sanitize_filename"
]
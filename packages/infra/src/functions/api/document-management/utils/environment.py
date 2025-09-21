"""
Environment variable management utility
"""

import os
from typing import Optional

def get_documents_bucket_name() -> str:
    """Documents bucket name"""
    return os.environ.get('DOCUMENTS_BUCKET_NAME', '')


def get_documents_table_name() -> str:
    """Documents table name"""
    return os.environ.get('DOCUMENTS_TABLE_NAME', '')


def get_segments_table_name() -> str:
    """Segments table name"""
    return os.environ.get('SEGMENTS_TABLE_NAME', '')


def get_indices_table_name() -> str:
    """Indices table name"""
    return os.environ.get('INDICES_TABLE_NAME', '')


def get_document_processing_queue_url() -> str:
    """Document processing SQS queue URL"""
    return os.environ.get('DOCUMENT_PROCESSING_QUEUE_URL', '')


def get_workflow_state_machine_arn() -> Optional[str]:
    """Workflow Step Function ARN"""
    return os.environ.get('WORKFLOW_STATE_MACHINE_ARN')


def get_opensearch_endpoint() -> str:
    """OpenSearch endpoint"""
    return os.environ.get('OPENSEARCH_ENDPOINT', '')


def get_opensearch_index_name() -> str:
    """OpenSearch index name"""
    return os.environ.get('OPENSEARCH_INDEX_NAME', 'aws-idp-ai-analysis')


def get_opensearch_region() -> str:
    """OpenSearch region"""
    return os.environ.get('OPENSEARCH_REGION', 'us-west-2')


def get_stage() -> str:
    """Deployment stage"""
    return os.environ.get('STAGE', 'prod')


def get_aws_region() -> str:
    """AWS region"""
    return os.environ.get('AWS_REGION', 'us-west-2')


# Supported file types
SUPPORTED_FILE_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.tif': 'image/tiff',
    '.tiff': 'image/tiff',
    '.bmp': 'image/bmp',
}

# Maximum file size (500MB) - aligned with frontend and backend configuration
MAX_FILE_SIZE = 500 * 1024 * 1024
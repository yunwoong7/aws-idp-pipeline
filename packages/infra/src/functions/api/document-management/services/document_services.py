"""
Document related service module
"""

import os
import sys
import json
import boto3
from datetime import datetime, timezone
from typing import Dict, Any
import logging

# Add parent directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.environment import (
    get_documents_table_name,
    get_document_processing_queue_url,
    get_opensearch_endpoint,
    get_opensearch_index_name,
    get_opensearch_region,
    get_aws_region,
    get_stage
)

# Initialize AWS resources
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')

logger = logging.getLogger()

# Initialize OpenSearch client
opensearch_client = None
try:
    opensearch_endpoint = get_opensearch_endpoint()
    if opensearch_endpoint:
        from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
        
        credentials = boto3.Session().get_credentials()
        auth = AWSV4SignerAuth(credentials, get_aws_region(), 'es')
        
        opensearch_client = OpenSearch(
            hosts=[{'host': opensearch_endpoint.replace('https://', ''), 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        )
        logger.info(f"OpenSearch client initialized: {opensearch_endpoint}")
except Exception as e:
    logger.error(f"OpenSearch client initialization failed: {str(e)}")
    opensearch_client = None

def send_document_processing_message(index_id: str, doc_id: str, file_name: str, 
                                   file_type: str, file_size: int, file_uri: str, 
                                   total_pages: int, current_time: str) -> None:
    """Send document processing message to SQS"""
    try:
        queue_url = get_document_processing_queue_url()
        stage = get_stage()
        
        # Convert any Decimal objects to int/float for JSON serialization
        queue_message = {
            "event_type": "document_uploaded",
            "index_id": index_id,
            "document_id": doc_id,
            "file_name": file_name,
            "file_type": file_type,
            "file_size": int(file_size) if hasattr(file_size, '__int__') else file_size,
            "file_uri": file_uri,
            "total_pages": int(total_pages) if hasattr(total_pages, '__int__') else total_pages,
            "upload_time": current_time,
            "stage": stage
        }
        
        sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(queue_message),
            MessageAttributes={
                'event_type': {
                    'StringValue': 'document_uploaded',
                    'DataType': 'String'
                },
                'index_id': {
                    'StringValue': index_id,
                    'DataType': 'String'
                },
                'file_type': {
                    'StringValue': file_type,
                    'DataType': 'String'
                }
            }
        )
        
        logger.info(f"SQS message sent: {doc_id}")
        
    except Exception as e:
        logger.error(f"SQS message sending failed: {str(e)}")
        raise


def delete_documents_from_opensearch(index_id: str, document_id: str) -> None:
    """Delete related documents from OpenSearch"""
    if not opensearch_client:
        logger.warning("OpenSearch client not initialized")
        return
    
    try:
        # Check number of documents to delete first
        # Many documents do not store 'index_id' as a field (index name already encodes it).
        # Align with read paths that filter only by 'document_id' while specifying the index in API.
        count_query = {
            "query": {
                "term": {"document_id": document_id}
            }
        }
        
        count_response = opensearch_client.count(
            index=index_id,
            body=count_query
        )
        
        documents_to_delete = count_response.get('count', 0)
        logger.info(f"🗑️ Number of documents to delete: {documents_to_delete} (index_id: {index_id}, document_id: {document_id})")
        
        if documents_to_delete == 0:
            logger.info(f"✅ No documents to delete from OpenSearch (index_id: {index_id}, document_id: {document_id})")
            return
        
        # Delete related documents by project_id and document_id
        delete_query = {
            "query": {
                "term": {"document_id": document_id}
            }
        }
        
        response = opensearch_client.delete_by_query(
            index=index_id,
            body=delete_query,
            request_timeout=30,  # numeric seconds; avoid '30s' string to fix ValueError
            wait_for_completion=True,  # synchronous execution for verification
            refresh=True,
            conflicts='proceed'  # Continue even with conflicts
        )
        
        deleted_count = response.get('deleted', 0)
        version_conflicts = response.get('version_conflicts', 0)
        failures = response.get('failures', [])
        
        if failures:
            logger.warning(f"⚠️ OpenSearch deletion failed: {len(failures)} failures")
            for failure in failures[:3]:  # Log only first 3 failures
                logger.warning(f"    Failure reason: {failure}")
        
        if version_conflicts > 0:
            logger.warning(f"⚠️ OpenSearch deletion failed: {version_conflicts} version conflicts")
        
        logger.info(f"✅ OpenSearch document deletion complete - deleted documents: {deleted_count}/{documents_to_delete}, index_id: {index_id}, document_id: {document_id}")
        
        # Verify deletion (optional)
        if deleted_count > 0:
            verification_response = opensearch_client.count(
                index=index_id,
                body=count_query
            )
            remaining_count = verification_response.get('count', 0)
            if remaining_count > 0:
                logger.warning(f"⚠️ After deletion, {remaining_count} documents remain in OpenSearch")
            else:
                logger.info(f"✅ OpenSearch deletion verification complete - all documents deleted")
        
    except Exception as e:
        logger.error(f"❌ OpenSearch document deletion failed (index_id: {index_id}, document_id: {document_id}): {str(e)}")
        # OpenSearch deletion failure does not stop overall document deletion (log only)
        # raise  # Commented out to prevent OpenSearch failure from stopping overall deletion
"""
AWS IDP AI Analysis - BDA Status Checker Lambda
Check BDA job status
"""

import json
import logging
import os
import time
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional
from dataclasses import dataclass

# Common module imports
from common import (
    DynamoDBService,
    S3Service,
    AWSClientFactory,
    get_current_timestamp,
)

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize common services
db_service = DynamoDBService()
s3_service = S3Service()
aws_clients = AWSClientFactory()

# Initialize AWS clients (BDA is not yet in the common module)
bda_runtime_client = boto3.client("bedrock-data-automation-runtime")

# Environment variable
STAGE = os.environ.get('STAGE', 'prod')

@dataclass
class BDAStatusResult:
    """BDA status check result"""
    success: bool
    index_id: str
    document_id: str
    bda_invocation_arn: str
    status: str
    is_completed: bool = False
    error: Optional[str] = None
    bda_metadata_uri: Optional[str] = None

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    BDA status check main handler
    """
    start_time = time.time()
    
    try:
        logger.info(f"BDA status check started - Stage: {STAGE}")
        logger.info(f"Received event: {json.dumps(event, ensure_ascii=False, indent=2)}")
        
        # Validate input data
        validate_input(event)
        
        # Check BDA status
        status_result = check_bda_status(event)
        
        # Return result
        response = {
            'success': status_result.success,
            'index_id': status_result.index_id,
            'document_id': status_result.document_id,
            'bda_invocation_arn': status_result.bda_invocation_arn,
            'status': status_result.status,
            'is_completed': status_result.is_completed,
            'processing_time': time.time() - start_time,
            'stage': STAGE,
            'file_type': event.get('file_type'),
            'processing_type': event.get('processing_type'),
            'bda_metadata_uri': status_result.bda_metadata_uri  # Always include, can be None
        }
            
        if not status_result.success:
            response['error'] = status_result.error
        
        logger.info(f"BDA status check completed: {json.dumps(response, ensure_ascii=False, indent=2)}")
        return response
        
    except Exception as e:
        error_message = f"BDA status check failed: {str(e)}"
        logger.error(error_message)
        
        return {
            'success': False,
            'index_id': event.get('index_id', 'unknown'),
            'document_id': event.get('document_id', 'unknown'),
            'bda_invocation_arn': event.get('bda_invocation_arn', 'unknown'),
            'status': 'ERROR',
            'is_completed': False,
            'error': error_message,
            'processing_time': time.time() - start_time,
            'stage': STAGE
        }

def validate_input(event: Dict[str, Any]) -> None:
    """
    Validate input data
    """
    required_fields = ['index_id', 'document_id']
    
    for field in required_fields:
        if field not in event:
            raise ValueError(f"Missing required field: {field}")
    
    # bda_invocation_arn is optional (not present for skipped file types)

def check_bda_status(event: Dict[str, Any]) -> BDAStatusResult:
    """
    Check BDA job status
    """
    try:
        invocation_arn = event.get('bda_invocation_arn')
        
        # Handle skipped BDA processing (no invocation ARN)
        if not invocation_arn:
            logger.info("No BDA invocation ARN found - file type was skipped from BDA processing")
            return BDAStatusResult(
                success=True,
                index_id=event['index_id'],
                document_id=event['document_id'],
                bda_invocation_arn='',
                status='Success',  # Return success to continue workflow
                is_completed=True,
                bda_metadata_uri=None  # Explicitly set to None for skipped files
            )
        
        # Get BDA status
        response = bda_runtime_client.get_data_automation_status(
            invocationArn=invocation_arn
        )
        
        logger.info(f"BDA status check response: {json.dumps(response, default=str, ensure_ascii=False, indent=2)}")
        
        status = response['status']
        logger.info(f"BDA status: {status}")
        
        # Check completed status (Success is the same as COMPLETED)
        is_completed = status in ['Success', 'COMPLETED', 'FAILED', 'STOPPED', 'ServiceError', 'ClientError']
        
        result = BDAStatusResult(
            success=True,
            index_id=event['index_id'],
            document_id=event['document_id'],
            bda_invocation_arn=invocation_arn,
            status=status,
            is_completed=is_completed
        )
        
        # If successful, add output URI (try different field names)
        if status in ['Success', 'COMPLETED']:
            # Check multiple possible output paths
            output_uri = None
            
            # 1. Check outputConfiguration
            if 'outputConfiguration' in response:
                output_config = response['outputConfiguration']
                if isinstance(output_config, dict):
                    if 's3Uri' in output_config:
                        output_uri = output_config['s3Uri']
                    elif 's3OutputConfiguration' in output_config:
                        s3_config = output_config['s3OutputConfiguration']
                        if 's3Uri' in s3_config:
                            output_uri = s3_config['s3Uri']
            
            # 2. Check direct output field
            elif 'output' in response:
                output = response['output']
                if isinstance(output, dict) and 's3Uri' in output:
                    output_uri = output['s3Uri']
                elif isinstance(output, str):
                    output_uri = output
            
            # 3. Find s3Uri directly in response
            elif 's3Uri' in response:
                output_uri = response['s3Uri']
            
            if output_uri:
                result.bda_metadata_uri = output_uri
                logger.info(f"Found BDA output URI (original): {output_uri}")
            else:
                logger.warning("BDA output URI not found")
        
        # Update Documents table based on status
        if status == 'Success':
            update_document_status(event['document_id'], 'bda_completed')
        elif status in ['ServiceError', 'ClientError']:
            update_document_status(event['document_id'], 'bda_failed')
        # InProgress, Created status is not updated (already in bda_analyzing state)
        
        return result
        
    except ClientError as e:
        error_message = f"BDA status check failed: {str(e)}"
        logger.error(error_message)
        
        # Update document status to error if error occurs
        update_document_status(event['document_id'], 'error')
        
        return BDAStatusResult(
            success=False,
            index_id=event['index_id'],
            document_id=event['document_id'],
            bda_invocation_arn=event['bda_invocation_arn'],
            status='ERROR',
            error=error_message
        )

def update_document_status(document_id: str, status: str) -> None:
    """
    Update document status in Documents table
    """
    try:
        current_time = get_current_timestamp()
        
        db_service.update_item(
            table_name='documents',
            key={'document_id': document_id},
            update_expression='SET #status = :status, updated_at = :updated_at',
            expression_attribute_names={'#status': 'status'},
            expression_attribute_values={
                ':status': status,
                ':updated_at': current_time
            }
        )
        
        logger.info(f"Document status updated: {document_id} -> {status}")
        
    except Exception as e:
        logger.error(f"Document status update failed: {str(e)}")
        # Update failure does not stop the entire process
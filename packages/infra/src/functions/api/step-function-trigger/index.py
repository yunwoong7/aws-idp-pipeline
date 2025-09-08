"""
AWS IDP AI Analysis - Step Function Trigger Lambda
Lambda function that receives SQS messages and starts the document processing Step Function
"""

import json
import logging
import os
import boto3
import uuid
from datetime import datetime
from typing import Dict, Any, List

# Logging setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS client initialization
stepfunctions_client = boto3.client('stepfunctions')

# Environment variables
STEP_FUNCTION_ARN = os.environ.get('STEP_FUNCTION_ARN')
STAGE = os.environ.get('STAGE', 'prod')

def check_running_executions():
    """
    Check if there are any running Step Function executions
    Returns True if any executions are currently running
    """
    try:
        if not STEP_FUNCTION_ARN:
            logger.warning("STEP_FUNCTION_ARN not set, cannot check running executions")
            return False
            
        response = stepfunctions_client.list_executions(
            stateMachineArn=STEP_FUNCTION_ARN,
            statusFilter='RUNNING',
            maxResults=1  # We only need to know if any are running
        )
        
        running_count = len(response['executions'])
        if running_count > 0:
            logger.info(f"Found {running_count} running Step Function execution(s)")
            return True
        else:
            logger.info("No running Step Function executions found")
            return False
            
    except Exception as e:
        logger.error(f"Failed to check Step Function executions: {str(e)}")
        # In case of error, assume no executions are running to avoid blocking
        return False

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Main handler that receives SQS messages and starts the Step Function
    """
    try:
        logger.info(f"Step Function trigger started - Stage: {STAGE}")
        logger.info(f"Received event: {json.dumps(event, ensure_ascii=False, indent=2)}")
        
        # Check Step Function ARN
        if not STEP_FUNCTION_ARN:
            raise ValueError("STEP_FUNCTION_ARN environment variable is not set")
        
        # Process SQS records
        if 'Records' not in event:
            raise ValueError("No SQS Records found")
        
        results = []
        
        # Check if Step Function is already running BEFORE processing any records
        if check_running_executions():
            logger.info("Step Function still running, failing entire Lambda to trigger SQS retry")
            raise Exception("Processing in progress, retry later")
        
        for record in event['Records']:
            try:
                
                # Parse SQS message
                sqs_body = json.loads(record['body'])
                logger.info(f"SQS message content: {json.dumps(sqs_body, ensure_ascii=False, indent=2)}")
                
                # Prepare Step Function execution input
                execution_input = prepare_step_function_input(sqs_body)
                
                # Start Step Function execution
                execution_result = start_step_function_execution(execution_input)
                
                results.append({
                    'record_id': record.get('messageId', 'unknown'),
                    'execution_arn': execution_result['executionArn'],
                    'success': True
                })
                
                logger.info(f"Step Function execution success: {execution_result['executionArn']}")
                
            except Exception as record_error:
                logger.error(f"Record processing failed: {str(record_error)}")
                results.append({
                    'record_id': record.get('messageId', 'unknown'),
                    'success': False,
                    'error': str(record_error)
                })
        
        # Return processing results
        successful_count = sum(1 for r in results if r['success'])
        failed_count = len(results) - successful_count
        
        logger.info(f"Processing complete - Success: {successful_count}, Failed: {failed_count}")
        
        return {
            'statusCode': 200,
            'body': {
                'message': f'Step Function trigger complete - Success: {successful_count}, Failed: {failed_count}',
                'results': results,
                'stage': STAGE
            }
        }
        
    except Exception as e:
        logger.error(f"Step Function trigger failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'stage': STAGE
            }
        }

def prepare_step_function_input(sqs_message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert SQS message to Step Function input format
    """
    try:
        # Validate required fields
        required_fields = [
            'event_type', 'index_id', 'document_id',
            'file_name', 'file_type', 'file_uri'
        ]
        
        for field in required_fields:
            if field not in sqs_message:
                raise ValueError(f"Missing required field: {field}")
        
        # document_id is already passed as a simple UUID
        document_id = sqs_message['document_id']
        
        # Extract file extension and determine processing type
        file_name = sqs_message['file_name']
        file_extension = file_name.lower().split('.')[-1] if '.' in file_name else ''
        
        # Define MIME type and processing type mapping
        type_map = {
            # Documents
            'pdf': ('application/pdf', 'document'),
            'doc': ('application/msword', 'document'),
            'docx': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'document'),
            'txt': ('text/plain', 'document'),
            'rtf': ('application/rtf', 'document'),
            'odt': ('application/vnd.oasis.opendocument.text', 'document'),
            # Images
            'jpg': ('image/jpeg', 'image'),
            'jpeg': ('image/jpeg', 'image'),
            'png': ('image/png', 'image'),
            'gif': ('image/gif', 'image'),
            'bmp': ('image/bmp', 'image'),
            'tiff': ('image/tiff', 'image'),
            'tif': ('image/tiff', 'image'),
            'webp': ('image/webp', 'image'),
            # Videos
            'mp4': ('video/mp4', 'video'),
            'avi': ('video/x-msvideo', 'video'),
            'mov': ('video/quicktime', 'video'),
            'wmv': ('video/x-ms-wmv', 'video'),
            'flv': ('video/x-flv', 'video'),
            'mkv': ('video/x-matroska', 'video'),
            'webm': ('video/webm', 'video'),
            '3gp': ('video/3gpp', 'video'),
            # Audio
            'mp3': ('audio/mpeg', 'audio'),
            'wav': ('audio/wav', 'audio'),
            'flac': ('audio/flac', 'audio'),
            'm4a': ('audio/mp4', 'audio'),
            'aac': ('audio/aac', 'audio'),
            'ogg': ('audio/ogg', 'audio'),
            'wma': ('audio/x-ms-wma', 'audio'),
            'aiff': ('audio/aiff', 'audio'),
        }
        
        # Determine file_type and processing_type
        detected_file_type, processing_type = type_map.get(file_extension, ('application/octet-stream', 'unknown'))
        
        # Use original file_type from SQS if available, otherwise use detected
        original_file_type = sqs_message['file_type']
        final_file_type = original_file_type if original_file_type else detected_file_type
        
        logger.info(f"File type detection - Extension: {file_extension}, Detected: {detected_file_type}, Processing: {processing_type}")
        
        # Build Step Function input data
        step_function_input = {
            'event_type': sqs_message['event_type'],
            'index_id': sqs_message['index_id'],
            'document_id': document_id,
            'file_name': sqs_message['file_name'],
            'file_type': final_file_type,
            'processing_type': processing_type,
            'file_size': sqs_message.get('file_size', 0),
            'file_uri': sqs_message['file_uri'],
            'total_pages': sqs_message.get('total_pages', 1),
            'upload_time': sqs_message.get('upload_time', datetime.utcnow().isoformat() + 'Z'),
            'stage': sqs_message.get('stage', STAGE),
            'processing_started_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Additional metadata
        if 'metadata' in sqs_message:
            step_function_input['metadata'] = sqs_message['metadata']
        
        logger.info(f"Step Function input data prepared: {json.dumps(step_function_input, ensure_ascii=False, indent=2)}")
        return step_function_input
        
    except Exception as e:
        logger.error(f"Failed to prepare Step Function input data: {str(e)}")
        raise

def start_step_function_execution(execution_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start Step Function execution
    """
    try:
        # Generate execution name (must be unique)
        execution_name = f"doc-proc-{execution_input['index_id'][:8]}-{execution_input['document_id'][:8]}-{uuid.uuid4().hex[:8]}"
        
        # Start Step Function execution
        response = stepfunctions_client.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=execution_name,
            input=json.dumps(execution_input, ensure_ascii=False)
        )
        
        logger.info(f"Step Function execution started - Name: {execution_name}")
        logger.info(f"Execution ARN: {response['executionArn']}")
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to start Step Function execution: {str(e)}")
        raise

def validate_sqs_message(sqs_message: Dict[str, Any]) -> bool:
    """
    Validate SQS message
    """
    try:
        # Validate event type
        if sqs_message.get('event_type') != 'document_uploaded':
            logger.warning(f"Unsupported event type: {sqs_message.get('event_type')}")
            return False
        
        # Validate file_uri exists
        file_uri = sqs_message.get('file_uri', '')
        if not file_uri:
            logger.warning(f"Invalid file_uri: {file_uri}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate SQS message: {str(e)}")
        return False 
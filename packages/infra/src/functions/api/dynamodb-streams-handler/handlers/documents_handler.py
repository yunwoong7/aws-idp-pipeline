"""
DynamoDB Streams handler for Documents table
Detects changes in the Documents table and sends real-time notifications via WebSocket.
"""

import os
import sys
import logging
import json
import boto3
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from decimal import Decimal

# Add parent directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.websocket_sender import send_to_project_connections, create_message

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
dynamodb = boto3.resource('dynamodb')
stepfunctions_client = boto3.client('stepfunctions')

# Environment variables
DOCUMENTS_TABLE_NAME = os.environ.get('DOCUMENTS_TABLE_NAME')
STEP_FUNCTION_ARN = os.environ.get('STEP_FUNCTION_ARN')
STAGE = os.environ.get('STAGE', 'prod')

def check_upload_completion(record, message_data):
    """
    Check file upload completion status and generate notification message.
    
    Args:
        record: DynamoDB Stream record
        message_data: Base message data
    
    Returns:
        dict: Upload completion notification message or None
    """
    try:
        event_name = record['eventName']
        
        # Only check MODIFY events (status change)
        if event_name != 'MODIFY':
            return None
            
        old_image = record['dynamodb'].get('OldImage', {})
        new_image = record['dynamodb'].get('NewImage', {})
        
        # Check processing_status change
        old_status = old_image.get('processing_status', {}).get('S', '')
        new_status = new_image.get('processing_status', {}).get('S', '')
        
        # Upload completion condition: processing_status changes to 'completed' from 'processing' or other status
        if new_status == 'completed' and old_status != 'completed':
            file_name = new_image.get('file_name', {}).get('S', 'Unknown')
            document_id = new_image.get('document_id', {}).get('S', '')
            
            return {
                'type': 'upload_completion',
                'message': f'File "{file_name}" upload and processing completed.',
                'document_id': document_id,
                'file_name': file_name,
                'status': 'success',
                'timestamp': message_data.get('timestamp', 0)
            }
        
        # Check error status
        elif new_status in ['failed', 'error'] and old_status not in ['failed', 'error']:
            file_name = new_image.get('file_name', {}).get('S', 'Unknown')
            document_id = new_image.get('document_id', {}).get('S', '')
            
            return {
                'type': 'upload_completion',
                'message': f'An error occurred while processing file "{file_name}".',
                'document_id': document_id,
                'file_name': file_name,
                'status': 'error',
                'timestamp': message_data.get('timestamp', 0)
            }
            
        return None
        
    except Exception as e:
        logger.error(f"Error checking upload completion: {str(e)}")
        return None

def convert_decimal_to_json(obj):
    """
    Convert DynamoDB Decimal types to JSON serializable types
    """
    if isinstance(obj, dict):
        return {k: convert_decimal_to_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal_to_json(v) for v in obj]
    elif isinstance(obj, Decimal):
        # Convert Decimal to int if it's a whole number, otherwise to float
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj

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

def get_next_uploaded_document() -> Optional[Dict[str, Any]]:
    """
    Get the oldest uploaded document from DynamoDB
    Returns document data or None if no uploaded documents found
    """
    try:
        if not DOCUMENTS_TABLE_NAME:
            logger.warning("DOCUMENTS_TABLE_NAME not set")
            return None
            
        table = dynamodb.Table(DOCUMENTS_TABLE_NAME)
        
        # Scan for documents with status="uploaded", ordered by created_at
        response = table.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'uploaded'
            }
        )
        
        items = response.get('Items', [])
        if not items:
            logger.info("No uploaded documents found")
            return None
            
        # Sort by created_at (oldest first)
        sorted_items = sorted(items, key=lambda x: x.get('created_at', ''))
        oldest_document = sorted_items[0]
        
        logger.info(f"Found oldest uploaded document: {oldest_document.get('document_id', 'unknown')}")
        return oldest_document
        
    except Exception as e:
        logger.error(f"Failed to get next uploaded document: {str(e)}")
        return None

def prepare_step_function_input(document_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert document data to Step Function input format
    """
    try:
        # Extract file extension and determine processing type
        file_name = document_data.get('file_name', '')
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
        
        # Use original file_type from document if available, otherwise use detected
        original_file_type = document_data.get('file_type', '')
        final_file_type = original_file_type if original_file_type else detected_file_type
        
        logger.info(f"File type detection - Extension: {file_extension}, Detected: {detected_file_type}, Processing: {processing_type}")
        
        # Build Step Function input data
        step_function_input = {
            'event_type': 'document_uploaded',
            'index_id': document_data.get('index_id', ''),
            'document_id': document_data.get('document_id', ''),
            'file_name': document_data.get('file_name', ''),
            'file_type': final_file_type,
            'processing_type': processing_type,
            'file_size': document_data.get('file_size', 0),
            'file_uri': document_data.get('file_uri', ''),
            'total_pages': document_data.get('total_pages', 1),
            'upload_time': document_data.get('upload_time', document_data.get('created_at', datetime.utcnow().isoformat() + 'Z')),
            'stage': document_data.get('stage', STAGE),
            'processing_started_at': datetime.utcnow().isoformat() + 'Z'
        }
        
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

def trigger_next_document_processing():
    """
    Check if Step Function is running, if not, start processing next uploaded document
    """
    try:
        # Check if Step Function is already running
        if check_running_executions():
            logger.info("Step Function already running, skipping trigger")
            return
            
        # Get next uploaded document
        next_document = get_next_uploaded_document()
        if not next_document:
            logger.info("No uploaded documents to process")
            return
            
        # Convert Decimal types before processing
        next_document = convert_decimal_to_json(next_document)
        
        # Prepare and start Step Function
        execution_input = prepare_step_function_input(next_document)
        execution_result = start_step_function_execution(execution_input)
        
        logger.info(f"Successfully triggered Step Function for document: {next_document.get('document_id', 'unknown')}")
        
    except Exception as e:
        logger.error(f"Failed to trigger next document processing: {str(e)}")
        # Don't re-raise - this is called from stream handler and shouldn't fail the entire handler

def handler(event, context):
    """DynamoDB Streams handler for Documents table - only status changes"""
    try:
        processed_records = 0
        
        for record in event.get('Records', []):
            try:
                event_name = record['eventName']
                
                # Only handle MODIFY events for status changes
                if event_name != 'MODIFY':
                    continue
                
                # Check if status field has changed
                old_image = record['dynamodb'].get('OldImage', {})
                new_image = record['dynamodb'].get('NewImage', {})
                
                old_status = old_image.get('status', {}).get('S', '')
                new_status = new_image.get('status', {}).get('S', '')
                
                # Only process if status has actually changed
                if old_status == new_status:
                    logger.info(f"Status unchanged ({new_status}), skipping record")
                    continue
                
                logger.info(f"Status changed from '{old_status}' to '{new_status}'")
                
                # Extract index_id from changed record (MODIFY only)
                index_id = new_image.get('index_id', {}).get('S')
                
                if not index_id:
                    logger.warning(f"No index_id found in record")
                    continue
                
                # Create message
                message_data = create_message(record, 'documents')
                
                # Check file upload completion notification
                upload_completion_message = check_upload_completion(record, message_data)
                
                # If upload completion message exists, send additionally
                if upload_completion_message:
                    upload_result = send_to_project_connections(
                        project_id=index_id,
                        message_data=upload_completion_message,
                        websocket_api_id=os.environ['WEBSOCKET_API_ID'],
                        stage=os.environ['WEBSOCKET_STAGE']
                    )
                    logger.info(f"Upload completion notification sent to {upload_result['sent_count']} connections")
                
                # Send general update message
                result = send_to_project_connections(
                    project_id=index_id,
                    message_data=message_data,
                    websocket_api_id=os.environ['WEBSOCKET_API_ID'],
                    stage=os.environ['WEBSOCKET_STAGE']
                )
                
                logger.info(f"Documents update sent to {result['sent_count']} connections for index {index_id} (failed: {result['failed_count']})")
                processed_records += 1
                
                # Try to trigger next document processing (any status change might free up processing)
                trigger_next_document_processing()
                
            except Exception as e:
                logger.error(f"Error processing record: {str(e)}")
                continue
        
        logger.info(f"Processed {processed_records} documents stream records")
        return {'statusCode': 200, 'body': f'Processed {processed_records} records'}
        
    except Exception as e:
        logger.error(f"Documents stream handler error: {str(e)}")
        return {'statusCode': 500, 'body': f'Handler failed: {str(e)}'}
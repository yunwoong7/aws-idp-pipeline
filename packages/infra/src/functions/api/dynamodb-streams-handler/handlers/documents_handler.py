"""
DynamoDB Streams handler for Documents table
Detects changes in the Documents table and sends real-time notifications via WebSocket.
"""

import os
import sys
import logging

# Add parent directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.websocket_sender import send_to_project_connections, create_message

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
                
            except Exception as e:
                logger.error(f"Error processing record: {str(e)}")
                continue
        
        logger.info(f"Processed {processed_records} documents stream records")
        return {'statusCode': 200, 'body': f'Processed {processed_records} records'}
        
    except Exception as e:
        logger.error(f"Documents stream handler error: {str(e)}")
        return {'statusCode': 500, 'body': f'Handler failed: {str(e)}'}
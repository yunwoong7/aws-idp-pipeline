"""
DynamoDB Streams handler for Segments table
Detects changes in the Segments table and sends real-time notifications via WebSocket.
"""

import os
import sys
import logging

# Add parent directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.websocket_sender import send_to_project_connections, create_message

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """DynamoDB Streams handler for Segments table"""
    try:
        processed_records = 0
        
        for record in event.get('Records', []):
            try:
                event_name = record['eventName']
                
                # Only handle INSERT, MODIFY, REMOVE events
                if event_name not in ['INSERT', 'MODIFY', 'REMOVE']:
                    continue
                
                # Extract index_id from changed record
                index_id = None
                
                if event_name == 'REMOVE':
                    # If deleted, extract from OldImage
                    old_image = record['dynamodb'].get('OldImage', {})
                    index_id = old_image.get('index_id', {}).get('S')
                else:
                    # If added/modified, extract from NewImage
                    new_image = record['dynamodb'].get('NewImage', {})
                    index_id = new_image.get('index_id', {}).get('S')
                
                if not index_id:
                    logger.warning(f"No index_id found in record: {record['eventName']}")
                    continue
                
                # Create message
                message_data = create_message(record, 'segments')
                
                # Send message to all project connections via WebSocket
                result = send_to_project_connections(
                    project_id=index_id,
                    message_data=message_data,
                    websocket_api_id=os.environ['WEBSOCKET_API_ID'],
                    stage=os.environ['WEBSOCKET_STAGE']
                )
                
                logger.info(f"Segments update sent to {result['sent_count']} connections for index {index_id} (failed: {result['failed_count']})")
                processed_records += 1
                
            except Exception as e:
                logger.error(f"Error processing record: {str(e)}")
                continue
        
        logger.info(f"Processed {processed_records} segments stream records")
        return {'statusCode': 200, 'body': f'Processed {processed_records} records'}
        
    except Exception as e:
        logger.error(f"Segments stream handler error: {str(e)}")
        return {'statusCode': 500, 'body': f'Handler failed: {str(e)}'}
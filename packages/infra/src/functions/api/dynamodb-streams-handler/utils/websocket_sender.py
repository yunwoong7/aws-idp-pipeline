"""
WebSocket message sending utility
Provides common functionality for sending real-time messages from DynamoDB Streams to WebSocket.
"""

import json
import boto3
import os
import logging
from decimal import Decimal
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
connections_table = dynamodb.Table(os.environ['WEBSOCKET_CONNECTIONS_TABLE'])

def send_to_project_connections(project_id, message_data, websocket_api_id, stage):
    """
    Send message to all WebSocket connections for a specific index
    
    Args:
        project_id (str): Index ID (kept as project_id for backward compatibility)
        message_data (dict): Message data to send
        websocket_api_id (str): WebSocket API ID
        stage (str): API Gateway Stage
    
    Returns:
        dict: Sending result statistics
    """
    try:
        # Get all WebSocket connections for the index
        response = connections_table.query(
            IndexName='IndexIdIndex',
            KeyConditionExpression='index_id = :index_id',
            ExpressionAttributeValues={':index_id': project_id}
        )
        
        # Create WebSocket API Gateway Management API client
        api_gateway_management_api = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=f"https://{websocket_api_id}.execute-api.{os.environ['AWS_REGION']}.amazonaws.com/{stage}"
        )
        
        # Convert message to JSON
        message_json = json.dumps(message_data, cls=DecimalEncoder).encode('utf-8')
        
        # Send message to each connection
        sent_count = 0
        failed_count = 0
        
        for connection in response['Items']:
            connection_id = connection['connection_id']
            try:
                api_gateway_management_api.post_to_connection(
                    ConnectionId=connection_id,
                    Data=message_json
                )
                sent_count += 1
            except ClientError as e:
                if e.response['Error']['Code'] == 'GoneException':
                    # Remove connection from table if it's closed
                    connections_table.delete_item(Key={'connection_id': connection_id})
                    logger.info(f"Removed stale connection: {connection_id}")
                else:
                    logger.error(f"Failed to send message to {connection_id}: {str(e)}")
                failed_count += 1
        
        logger.info(f"Sent updates to {sent_count} connections for project {project_id} (failed: {failed_count})")
        
        return {
            'sent_count': sent_count,
            'failed_count': failed_count,
            'total_connections': len(response['Items'])
        }
        
    except Exception as e:
        logger.error(f"Error sending to project connections: {str(e)}")
        raise


def create_message(record, table_type):
    """
    Convert DynamoDB Stream record to WebSocket message
    
    Args:
        record (dict): DynamoDB Stream record
        table_type (str): Table type ('documents' or 'pages')
    
    Returns:
        dict: WebSocket message
    """
    event_name = record['eventName']
    
    message = {
        'type': 'real_time_update',
        'table': table_type,
        'event': event_name.lower(),
        'timestamp': record['dynamodb'].get('ApproximateCreationDateTime', 0)
    }
    
    if event_name in ['INSERT', 'MODIFY']:
        new_image = record['dynamodb'].get('NewImage', {})
        message['data'] = convert_dynamodb_to_json(new_image)
        
        if event_name == 'MODIFY':
            old_image = record['dynamodb'].get('OldImage', {})
            message['old_data'] = convert_dynamodb_to_json(old_image)
    
    elif event_name == 'REMOVE':
        old_image = record['dynamodb'].get('OldImage', {})
        message['data'] = convert_dynamodb_to_json(old_image)
    
    return message


def convert_dynamodb_to_json(dynamodb_item):
    """
    Convert DynamoDB item to general JSON
    
    Args:
        dynamodb_item (dict): DynamoDB item
    
    Returns:
        dict: Converted item in general JSON format
    """
    def convert_value(value):
        if 'S' in value:
            return value['S']
        elif 'N' in value:
            return Decimal(value['N'])
        elif 'B' in value:
            return value['B']
        elif 'SS' in value:
            return value['SS']
        elif 'NS' in value:
            return [Decimal(n) for n in value['NS']]
        elif 'BS' in value:
            return value['BS']
        elif 'M' in value:
            return {k: convert_value(v) for k, v in value['M'].items()}
        elif 'L' in value:
            return [convert_value(item) for item in value['L']]
        elif 'NULL' in value:
            return None
        elif 'BOOL' in value:
            return value['BOOL']
        else:
            return value
    
    return {key: convert_value(value) for key, value in dynamodb_item.items()}


class DecimalEncoder(json.JSONEncoder):
    """Custom encoder to encode Decimal objects to JSON"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super(DecimalEncoder, self).default(obj)
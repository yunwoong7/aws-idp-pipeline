"""
WebSocket Disconnect Handler
Removes connection info from DynamoDB when a WebSocket connection is closed.
"""

import json
import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['WEBSOCKET_CONNECTIONS_TABLE'])

def handler(event, context):
    """WebSocket disconnect handler"""
    try:
        connection_id = event['requestContext']['connectionId']
        
        # Delete connection info
        table.delete_item(
            Key={'connection_id': connection_id}
        )
        
        logger.info(f"WebSocket disconnected: {connection_id}")
        
        return {'statusCode': 200, 'body': 'Disconnected'}
        
    except Exception as e:
        logger.error(f"Disconnection error: {str(e)}")
        return {'statusCode': 500, 'body': f'Disconnection failed: {str(e)}'}
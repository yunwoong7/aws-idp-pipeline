"""
WebSocket Connect Handler
Manages project-specific WebSocket connections and stores connection info in DynamoDB.
"""

import json
import boto3
import os
from datetime import datetime, timezone
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['WEBSOCKET_CONNECTIONS_TABLE'])

def handler(event, context):
    """WebSocket connect handler"""
    try:
        connection_id = event['requestContext']['connectionId']
        
        # Extract index_id and user_id from query parameters
        query_params = event.get('queryStringParameters') or {}
        index_id = query_params.get('index_id')
        user_id = query_params.get('user_id', 'anonymous')
        
        if not index_id:
            logger.error("index_id is required")
            return {'statusCode': 400, 'body': 'index_id is required'}
        
        # Save connection info (TTL: 24 hours)
        ttl = int((datetime.now(timezone.utc).timestamp() + 86400))  # 24시간 후
        
        table.put_item(
            Item={
                'connection_id': connection_id,
                'index_id': index_id,
                'user_id': user_id,
                'connected_at': datetime.now(timezone.utc).isoformat(),
                'ttl': ttl
            }
        )
        
        logger.info(f"WebSocket connected: {connection_id}, index: {index_id}, user: {user_id}")
        
        return {'statusCode': 200, 'body': 'Connected'}
        
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return {'statusCode': 500, 'body': f'Connection failed: {str(e)}'}
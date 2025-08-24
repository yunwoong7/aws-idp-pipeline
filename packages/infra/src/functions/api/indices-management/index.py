"""
AWS IDP AI - Indices (Workspace) Management Lambda (Modular)

Endpoints:
1. GET /api/indices - list indices
2. POST /api/indices - create index
3. GET /api/indices/{index_id} - get an index
4. PUT /api/indices/{index_id} - update an index
5. DELETE /api/indices/{index_id} - delete an index
"""

import os
import sys
import json
from typing import Dict, Any
from datetime import datetime, timezone

# Add current directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from handlers.index_handlers import (
    handle_indices_list,
    handle_index_create,
    handle_index_get,
    handle_index_update,
    handle_index_delete,
    handle_index_deep_delete,
)
from utils.response import (
    create_cors_response,
    create_not_found_response,
    create_validation_error_response,
    create_internal_error_response,
)

import logging

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler function for indices management
    Handles API Gateway HTTP API events.
    """
    start_time = datetime.now(timezone.utc)
    
    try:
        # Lambda handler start logging
        logger.info(f"Indices management service started")
        logger.info(f"Received event: {json.dumps(event, ensure_ascii=False, indent=2)}")
        
        # Extract request info
        http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
        route_key = event.get('requestContext', {}).get('routeKey', '')
        path_parameters = event.get('pathParameters') or {}
        
        # Debug logs
        logger.info(f">> Indices management request: {http_method} {route_key}")
        logger.info(f">> Path parameters: {path_parameters}")

        body = {}
        if event.get('body'):
            try:
                body = json.loads(event['body'])
            except json.JSONDecodeError:
                return create_validation_error_response('Invalid JSON format.')

        if http_method == 'OPTIONS':
            return create_cors_response()

        index_id = path_parameters.get('index_id')

        routes = {
            'GET /api/indices': lambda: handle_indices_list(),
            'POST /api/indices': lambda: handle_index_create(body),
            'GET /api/indices/{index_id}': lambda: handle_index_get(index_id) if index_id else create_validation_error_response('index_id is required.'),
            'PUT /api/indices/{index_id}': lambda: handle_index_update(index_id, body) if index_id else create_validation_error_response('index_id is required.'),
            'DELETE /api/indices/{index_id}': lambda: handle_index_delete(index_id) if index_id else create_validation_error_response('index_id is required.'),
            # Deep delete: remove DynamoDB docs/segments, S3 files, and OpenSearch index
            'POST /api/indices/{index_id}/deep-delete': lambda: handle_index_deep_delete(index_id) if index_id else create_validation_error_response('index_id is required.'),
        }

        handler = routes.get(route_key)
        if handler:
            return handler()
        return create_not_found_response(f'Unsupported endpoint: {route_key}')
        
    except Exception as e:
        # Log all errors
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        logger.error("=" * 80)
        logger.error("INDICES MANAGEMENT SERVICE LAMBDA HANDLER ERROR")
        logger.error("=" * 80)
        logger.error(f"Error occurred at: {end_time.isoformat()}")
        logger.error(f"Processing time before error: {duration:.3f}s")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Request ID: {context.aws_request_id}")
        
        # Log stack trace
        import traceback
        logger.error("Stack trace:")
        logger.error(traceback.format_exc())
        
        logger.error("=" * 80)
        
        return create_internal_error_response(f"Indices management service processing failed: {str(e)}")
    
    finally:
        # Lambda handler completion logging
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        logger.info("=" * 80)
        logger.info("INDICES MANAGEMENT SERVICE LAMBDA HANDLER COMPLETE")
        logger.info("=" * 80)
        logger.info(f"End time: {end_time.isoformat()}")
        logger.info(f"Total processing time: {duration:.3f}s")
        logger.info("=" * 80)



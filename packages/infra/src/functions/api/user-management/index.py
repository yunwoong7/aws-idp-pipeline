"""
AWS IDP AI Analysis - User Management Lambda Function

User management endpoints:
1. GET /api/users/me - Get current user permissions
2. GET /api/users - List all users
3. PUT /api/users/{user_id}/permissions - Update user permissions
4. POST /api/users/{user_id}/status - Update user status
"""

import os
import sys
import json
from typing import Dict, Any
from datetime import datetime, timezone

# Add current directory to Python path for Lambda environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from users_handlers import (
    handle_get_current_user_permissions,
    handle_list_users,
    handle_update_user_permissions,
    handle_update_user_status
)

from handlers.auth_handlers import (
    handle_get_current_user,
    handle_logout
)

import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def create_cors_response(status_code: int = 200, body: str = "") -> Dict[str, Any]:
    """Create CORS response"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Amz-Date, X-Api-Key, X-Amz-Security-Token"
        },
        "body": body
    }


def create_not_found_response(message: str = "Not found") -> Dict[str, Any]:
    """Create 404 response"""
    return {
        "statusCode": 404,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": message})
    }


def create_internal_error_response(message: str) -> Dict[str, Any]:
    """Create 500 response"""
    return {
        "statusCode": 500,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": message})
    }


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda handler function for user management
    Handles API Gateway HTTP API events.
    """
    start_time = datetime.now(timezone.utc)

    try:
        logger.info(f"User management service started")
        logger.info(f"Received event: {json.dumps(event, ensure_ascii=False, indent=2)}")

        # Extract request info
        http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
        path = event.get('path') or event.get('rawPath', '')
        path_parameters = event.get('pathParameters') or {}

        logger.info(f"User management request: {http_method} {path}")
        logger.info(f"Path parameters: {path_parameters}")

        # Handle OPTIONS request (CORS)
        if http_method == 'OPTIONS':
            return create_cors_response()

        # Routing logic
        response = None

        # Authentication APIs - handle first
        if '/api/auth/' in path:
            if http_method == 'GET' and path.endswith('/api/auth/user'):
                response = handle_get_current_user(event, context)
            elif http_method == 'POST' and path.endswith('/api/auth/logout'):
                response = handle_logout(event, context)
        # Users APIs
        elif http_method == 'GET' and path.endswith('/api/users/me'):
            response = handle_get_current_user_permissions(event, context)
        elif http_method == 'GET' and path.endswith('/api/users'):
            response = handle_list_users(event, context)
        elif http_method == 'PUT' and '/api/users/' in path and '/permissions' in path:
            response = handle_update_user_permissions(event, context)
        elif http_method == 'POST' and '/api/users/' in path and '/status' in path:
            response = handle_update_user_status(event, context)

        if response is None:
            response = create_not_found_response("Unsupported endpoint")

        return response

    except Exception as e:
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        logger.error("=" * 80)
        logger.error("USER MANAGEMENT SERVICE LAMBDA HANDLER ERROR")
        logger.error("=" * 80)
        logger.error(f"Error occurred at: {end_time.isoformat()}")
        logger.error(f"Processing time before error: {duration:.3f}s")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Request ID: {context.aws_request_id}")

        import traceback
        logger.error("Stack trace:")
        logger.error(traceback.format_exc())

        logger.error("=" * 80)

        return create_internal_error_response(f"User management service processing failed: {str(e)}")

    finally:
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        logger.info("=" * 80)
        logger.info("USER MANAGEMENT SERVICE LAMBDA HANDLER COMPLETE")
        logger.info("=" * 80)
        logger.info(f"End time: {end_time.isoformat()}")
        logger.info(f"Total processing time: {duration:.3f}s")
        logger.info("=" * 80)

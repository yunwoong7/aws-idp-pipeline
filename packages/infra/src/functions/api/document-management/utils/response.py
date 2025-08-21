"""
API response creation utility
"""

import json
from typing import Dict, Any, Optional


def create_cors_headers() -> Dict[str, str]:
    """Create CORS headers"""
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Amz-Date, X-Api-Key, X-Amz-Security-Token',
        'Access-Control-Max-Age': '86400',
    }


def create_response(status_code: int, body: Dict[str, Any], message: Optional[str] = None) -> Dict[str, Any]:
    """Create default API response"""
    response_body = body.copy()
    if message:
        response_body['message'] = message
    
    return {
        'statusCode': status_code,
        'headers': create_cors_headers(),
        'body': json.dumps(response_body, ensure_ascii=False, default=str)
    }


def create_success_response(data: Dict[str, Any], message: Optional[str] = None) -> Dict[str, Any]:
    """Create success response (200)"""
    return create_response(200, {'success': True, 'data': data}, message)


def create_created_response(data: Dict[str, Any], message: Optional[str] = None) -> Dict[str, Any]:
    """Create created response (201)"""
    return create_response(201, {'success': True, 'data': data}, message)


def create_validation_error_response(message: str) -> Dict[str, Any]:
    """Create validation error response (400)"""
    return create_response(400, {'success': False, 'error': 'ValidationError'}, message)


def create_bad_request_response(message: str) -> Dict[str, Any]:
    """Create bad request response (400)"""
    return create_response(400, {'success': False, 'error': 'BadRequest'}, message)


def create_not_found_response(message: str) -> Dict[str, Any]:
    """Create not found response (404)"""
    return create_response(404, {'success': False, 'error': 'NotFound'}, message)


def create_internal_error_response(message: str) -> Dict[str, Any]:
    """Create internal server error response (500)"""
    return create_response(500, {'success': False, 'error': 'InternalServerError'}, message)


def create_cors_response(status_code: int = 200, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create CORS preflight response"""
    return {
        'statusCode': status_code,
        'headers': create_cors_headers(),
        'body': json.dumps(body or {'message': 'OK'}, ensure_ascii=False)
    }
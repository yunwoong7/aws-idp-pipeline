"""
Response utility for Document Indexer Lambda
응답 생성을 위한 유틸리티 함수들
"""

import json
from typing import Dict, Any, Union


def create_response(
    status_code: int, 
    body: Union[Dict[str, Any], str],
    headers: Dict[str, str] = None
) -> Dict[str, Any]:
    """
    HTTP 응답 생성
    
    Args:
        status_code: HTTP 상태 코드
        body: 응답 본문 (딕셔너리 또는 문자열)
        headers: 추가 헤더 (옵션)
        
    Returns:
        Lambda 응답 형식의 딕셔너리
    """
    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    }
    
    if headers:
        default_headers.update(headers)
    
    # body가 딕셔너리인 경우 JSON 문자열로 변환
    if isinstance(body, dict):
        body_str = json.dumps(body, ensure_ascii=False)
    else:
        body_str = str(body)
    
    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': body_str
    }


def create_success_response(data: Dict[str, Any] = None, message: str = "Success") -> Dict[str, Any]:
    """
    성공 응답 생성
    
    Args:
        data: 응답 데이터
        message: 성공 메시지
        
    Returns:
        성공 응답
    """
    response_body = {
        'success': True,
        'message': message
    }
    
    if data:
        response_body['data'] = data
    
    return create_response(200, response_body)


def create_error_response(
    status_code: int, 
    error_message: str, 
    error_code: str = None
) -> Dict[str, Any]:
    """
    오류 응답 생성
    
    Args:
        status_code: HTTP 상태 코드
        error_message: 오류 메시지
        error_code: 오류 코드 (옵션)
        
    Returns:
        오류 응답
    """
    response_body = {
        'success': False,
        'error': error_message
    }
    
    if error_code:
        response_body['error_code'] = error_code
    
    return create_response(status_code, response_body)


def create_validation_error_response(errors: Dict[str, str]) -> Dict[str, Any]:
    """
    유효성 검증 오류 응답 생성
    
    Args:
        errors: 필드별 오류 메시지 딕셔너리
        
    Returns:
        유효성 검증 오류 응답
    """
    return create_response(400, {
        'success': False,
        'error': 'Validation failed',
        'validation_errors': errors
    }) 
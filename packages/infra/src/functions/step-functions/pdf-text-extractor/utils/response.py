"""
Lambda 응답 생성 유틸리티
표준화된 응답 형식을 제공하는 기능
"""

from typing import Dict, Any, Optional

def create_response(
    success: bool,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    status_code: int = None
) -> Dict[str, Any]:
    """
    Step Function용 Lambda 응답 생성 (API Gateway 형태가 아닌 직접 데이터)
    
    Args:
        success: 성공 여부
        message: 응답 메시지
        data: 응답 데이터
        status_code: HTTP 상태 코드 (사용하지 않음, 호환성 유지용)
        
    Returns:
        직접 데이터 응답 딕셔너리 (Step Function 호환)
    """
    response = {
        'success': success,
        'message': message
    }
    
    if data is not None:
        response.update(data)  # data의 내용을 최상위 레벨로 병합
    
    return response

def create_success_response(message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    성공 응답 생성
    
    Args:
        message: 성공 메시지
        data: 응답 데이터
        
    Returns:
        성공 응답 딕셔너리
    """
    return create_response(success=True, message=message, data=data)

def create_error_response(
    message: str,
    data: Optional[Dict[str, Any]] = None,
    status_code: int = 500
) -> Dict[str, Any]:
    """
    오류 응답 생성
    
    Args:
        message: 오류 메시지
        data: 오류 관련 데이터
        status_code: HTTP 상태 코드 (사용하지 않음, 호환성 유지용)
        
    Returns:
        오류 응답 딕셔너리
    """
    return create_response(success=False, message=message, data=data)

def create_validation_error_response(message: str, validation_errors: Dict[str, Any]) -> Dict[str, Any]:
    """
    유효성 검사 오류 응답 생성
    
    Args:
        message: 오류 메시지
        validation_errors: 유효성 검사 오류 정보
        
    Returns:
        유효성 검사 오류 응답 딕셔너리
    """
    return create_error_response(
        message=message,
        data={'validation_errors': validation_errors}
    ) 
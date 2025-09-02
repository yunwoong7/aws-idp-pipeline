"""
Authentication router for user information from Cognito/ALB headers
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import base64
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

class User(BaseModel):
    email: str
    name: Optional[str] = None
    groups: Optional[List[str]] = None

def decode_cognito_token(token: str) -> dict:
    """
    Decode the x-amzn-oidc-data token from ALB
    """
    try:
        # JWT 토큰의 payload 부분 (두 번째 부분) 추출
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT token format")
        
        # Base64 디코딩 (패딩 추가)
        payload = parts[1]
        # Base64 패딩 처리
        payload += '=' * (4 - len(payload) % 4)
        
        decoded_bytes = base64.b64decode(payload)
        decoded_str = decoded_bytes.decode('utf-8')
        
        return json.loads(decoded_str)
    except Exception as e:
        logger.error(f"Failed to decode Cognito token: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

@router.get("/user", response_model=User)
async def get_current_user(request: Request):
    """
    Get current user information from ALB Cognito headers or return local dev user
    """
    # 로컬 개발 환경 체크 (AUTH_DISABLED 환경 변수로만 판단)
    auth_disabled = os.getenv("AUTH_DISABLED")
    logger.info(f"AUTH_DISABLED environment variable: {auth_disabled}")
    
    if auth_disabled == "true":
        logger.info("Local development mode - returning admin user")
        return User(
            email="admin@localhost",
            name="Admin",
            groups=["aws-idp-ai-admins", "aws-idp-ai-users"]
        )
    
    # ALB가 설정한 Cognito 헤더에서 사용자 정보 추출
    logger.info(f"Request headers: {dict(request.headers)}")
    oidc_data = request.headers.get("x-amzn-oidc-data")
    
    if not oidc_data:
        logger.warning("No OIDC data found in headers")
        logger.info("Available headers: " + str(list(request.headers.keys())))
        raise HTTPException(status_code=401, detail="No authentication data found")
    
    try:
        # OIDC 토큰 디코딩
        user_data = decode_cognito_token(oidc_data)
        
        # 사용자 정보 추출
        email = user_data.get("email")
        name = user_data.get("name") or user_data.get("given_name")
        
        # 그룹 정보는 cognito:groups 클레임에서 가져옴
        groups = user_data.get("cognito:groups", [])
        
        if not email:
            raise HTTPException(status_code=401, detail="Email not found in token")
        
        logger.info(f"User authenticated: {email}")
        
        return User(
            email=email,
            name=name,
            groups=groups
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process user authentication: {e}")
        raise HTTPException(status_code=401, detail="Authentication processing failed")

@router.post("/logout")
async def logout():
    """
    Logout endpoint (for local development simulation)
    """
    return {"message": "Logout successful"}
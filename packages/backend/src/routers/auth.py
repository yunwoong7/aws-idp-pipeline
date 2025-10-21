"""
Authentication router for user information from Cognito/ALB headers
"""

from fastapi import APIRouter, Request, HTTPException, Response
from pydantic import BaseModel
from typing import List, Optional
import json
import base64
import os
import logging
from urllib.parse import quote

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
        # OIDC ID 토큰 디코딩 (기본 사용자 정보)
        user_data = decode_cognito_token(oidc_data)

        # Debug: Log all available fields in the token
        logger.info(f"🔍 ID token fields: {list(user_data.keys())}")
        logger.info(f"🔍 ID token data: {user_data}")

        # 사용자 정보 추출
        email = user_data.get("email")
        # Try to get name from various Cognito attributes
        # Priority: name > given_name > preferred_username > username > cognito:username > email prefix
        name = (
            user_data.get("name") or
            user_data.get("given_name") or
            user_data.get("preferred_username") or
            user_data.get("username") or
            user_data.get("cognito:username") or
            (email.split("@")[0] if email else None)
        )

        # 그룹 정보는 Access Token에서 가져옴 (ID Token에는 없음)
        # ALB는 x-amzn-oidc-accesstoken 헤더로 Access Token을 전달
        access_token = request.headers.get("x-amzn-oidc-accesstoken")
        groups = []

        if access_token:
            try:
                # Access Token 디코딩하여 그룹 정보 추출
                access_data = decode_cognito_token(access_token)
                groups = access_data.get("cognito:groups", [])
                logger.info(f"🔍 Access token fields: {list(access_data.keys())}")
                logger.info(f"👥 Groups from access token: {groups}")
            except Exception as e:
                logger.warning(f"Failed to decode access token for groups: {e}")
                # Fallback to ID token groups (if any)
                groups = user_data.get("cognito:groups", [])
        else:
            # Fallback to ID token groups (if any)
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

@router.get("/debug-env")
async def debug_env():
    """Debug endpoint to check environment variables"""
    return {
        "COGNITO_USER_POOL_DOMAIN": os.getenv("COGNITO_USER_POOL_DOMAIN", "NOT_SET"),
        "COGNITO_CLIENT_ID": os.getenv("COGNITO_CLIENT_ID", "NOT_SET"),
        "AWS_REGION": os.getenv("AWS_REGION", "NOT_SET"),
        "AUTH_DISABLED": os.getenv("AUTH_DISABLED", "NOT_SET"),
    }

@router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Logout endpoint - clears ALB session cookies and generates Cognito logout URL

    For Cognito + ALB authentication, we need to:
    1. Clear ALB HttpOnly session cookies server-side
    2. Logout from Cognito to clear Cognito session
    3. Redirect to /logged-out page

    The ALB session cookies are HttpOnly, so they cannot be deleted by JavaScript.
    We must delete them server-side using Set-Cookie headers.
    """
    # 로컬 개발 환경 체크
    auth_disabled = os.getenv("AUTH_DISABLED")

    if auth_disabled == "true":
        logger.info("Local development mode - logout simulation")
        return {"message": "Logout successful (local dev)"}

    # 요청 헤더에서 현재 호스트 정보 추출
    host = request.headers.get("host")
    x_forwarded_proto = request.headers.get("x-forwarded-proto", "https")

    # ALB 세션 쿠키 삭제 (HttpOnly 쿠키는 서버에서만 삭제 가능)
    # ALB가 생성하는 쿠키들: AWSELBAuthSessionCookie, AWSELBAuthSessionCookie-0, -1, -2
    cookie_names = [
        'AWSELBAuthSessionCookie',
        'AWSELBAuthSessionCookie-0',
        'AWSELBAuthSessionCookie-1',
        'AWSELBAuthSessionCookie-2',
    ]

    logger.info(f"🧹 Clearing ALB session cookies: {cookie_names}")

    for cookie_name in cookie_names:
        # Set-Cookie 헤더로 쿠키 삭제
        # 쿠키를 삭제하려면 과거 날짜로 expires를 설정
        response.set_cookie(
            key=cookie_name,
            value="",
            max_age=0,
            expires=0,
            path="/",
            secure=True,  # HTTPS only
            httponly=True,  # JavaScript 접근 불가
            samesite="lax"
        )
        logger.info(f"   ✅ Cleared cookie: {cookie_name}")

    # Cognito 로그아웃 URL 생성
    user_pool_domain = os.getenv("COGNITO_USER_POOL_DOMAIN")
    client_id = os.getenv("COGNITO_CLIENT_ID")
    region = os.getenv("AWS_REGION", "us-west-2")

    # 디버깅을 위한 로그
    logger.info(f"🔍 Logout attempt - user_pool_domain: {user_pool_domain}, client_id: {client_id}, region: {region}")

    # 로그아웃 후 리다이렉트할 URL (로그아웃 완료 페이지)
    # Cognito 허용된 로그아웃 URL과 정확히 일치해야 함
    logout_uri = f"{x_forwarded_proto}://{host}/logged-out"

    logger.info(f"Generating logout URL - domain: {user_pool_domain}, client_id: {client_id}, logout_uri: {logout_uri}")

    # ALB + Cognito 로그아웃 - Cognito logout endpoint 사용
    if user_pool_domain and client_id:
        # URL 인코딩
        encoded_logout_uri = quote(logout_uri, safe='')

        # Cognito logout endpoint
        # https://docs.aws.amazon.com/cognito/latest/developerguide/logout-endpoint.html
        #
        # IMPORTANT: For ALB + Cognito integration:
        # 1. Clear ALB session cookies (done above with Set-Cookie headers)
        # 2. Cognito session is cleared by calling Cognito logout endpoint
        # 3. User is redirected to /logged-out page (no auth required)
        # 4. When user clicks "Log In Again", they'll be redirected to / which requires fresh auth
        logout_url = f"https://{user_pool_domain}.auth.{region}.amazoncognito.com/logout"
        logout_url += f"?client_id={client_id}"
        logout_url += f"&logout_uri={encoded_logout_uri}"

        logger.info(f"✅ Generated Cognito logout URL: {logout_url}")
        logger.info(f"🔍 Encoded logout_uri: {encoded_logout_uri}")

        return {
            "message": "Logout URL generated",
            "logout_url": logout_url
        }
    else:
        # Cognito 설정이 없으면 홈으로
        logger.warning(f"⚠️ Cognito configuration missing - redirecting to home")
        return {
            "message": "Logout successful",
            "action": "clear_cookies",
            "redirect_url": logout_uri
        }
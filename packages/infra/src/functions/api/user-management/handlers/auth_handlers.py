"""
Authentication handlers for AWS IDP AI Analysis
"""

import os
import json
import base64
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
        raise ValueError("Invalid authentication token")

def handle_get_current_user(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Get current user information from ALB Cognito headers or return local dev user
    """
    try:
        # 로컬 개발 환경 체크 (AUTH_DISABLED 환경 변수로만 판단)
        auth_disabled = os.getenv("AUTH_DISABLED")
        logger.info(f"AUTH_DISABLED environment variable: {auth_disabled}")
        
        if auth_disabled == "true":
            logger.info("Local development mode - returning admin user")
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Amz-Date, X-Api-Key, X-Amz-Security-Token"
                },
                "body": json.dumps({
                    "email": "admin@localhost",
                    "name": "Admin",
                    "groups": ["aws-idp-ai-admins", "aws-idp-ai-users"]
                })
            }
        
        # ALB가 설정한 Cognito 헤더에서 사용자 정보 추출
        headers = event.get("headers", {})
        logger.info(f"Request headers: {headers}")
        
        oidc_data = headers.get("x-amzn-oidc-data")
        
        if not oidc_data:
            logger.warning("No OIDC data found in headers")
            logger.info("Available headers: " + str(list(headers.keys())))
            return {
                "statusCode": 401,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "No authentication data found"})
            }
        
        # OIDC 토큰 디코딩
        user_data = decode_cognito_token(oidc_data)

        # Debug: Log all available fields in the token
        logger.info(f"🔍 JWT token fields: {list(user_data.keys())}")
        logger.info(f"🔍 JWT token data: {user_data}")

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

        # 그룹 정보는 cognito:groups 클레임에서 가져옴
        groups = user_data.get("cognito:groups", [])
        
        if not email:
            logger.error("Email not found in token")
            return {
                "statusCode": 401,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Email not found in token"})
            }
        
        logger.info(f"User authenticated: {email}")
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Amz-Date, X-Api-Key, X-Amz-Security-Token"
            },
            "body": json.dumps({
                "email": email,
                "name": name,
                "groups": groups
            })
        }
        
    except ValueError as ve:
        logger.error(f"Authentication validation error: {ve}")
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Authentication processing failed"})
        }
    except Exception as e:
        logger.error(f"Failed to process user authentication: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Internal server error"})
        }

def handle_logout(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Logout endpoint - generates Cognito logout URL

    For Cognito + ALB authentication, this endpoint returns the Cognito logout URL
    that the frontend should redirect to.

    The logout URL format:
    https://<domain>.auth.<region>.amazoncognito.com/logout?client_id=<client_id>&logout_uri=<logout_uri>
    """
    try:
        # 로컬 개발 환경 체크
        auth_disabled = os.getenv("AUTH_DISABLED")

        if auth_disabled == "true":
            logger.info("Local development mode - logout simulation")
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization"
                },
                "body": json.dumps({"message": "Logout successful (local dev)"})
            }

        # Cognito 로그아웃 URL 생성
        # 환경 변수에서 Cognito 설정 가져오기
        user_pool_domain = os.getenv("COGNITO_USER_POOL_DOMAIN")
        client_id = os.getenv("COGNITO_CLIENT_ID")
        region = os.getenv("AWS_REGION", "us-east-1")

        # 요청 헤더에서 현재 호스트 정보 추출
        headers = event.get("headers", {})
        host = headers.get("host") or headers.get("Host")

        # 로그아웃 후 리다이렉트할 URL (/logged-out 페이지)
        protocol = "https" if headers.get("x-forwarded-proto") == "https" else "http"
        logout_uri = f"{protocol}://{host}/logged-out"

        logger.info(f"Generating logout URL - domain: {user_pool_domain}, client_id: {client_id}, logout_uri: {logout_uri}")

        # Cognito 로그아웃 URL 생성
        if user_pool_domain and client_id:
            # Cognito hosted UI logout endpoint
            logout_url = f"https://{user_pool_domain}.auth.{region}.amazoncognito.com/logout"
            logout_url += f"?client_id={client_id}"
            logout_url += f"&logout_uri={logout_uri}"

            logger.info(f"Generated Cognito logout URL: {logout_url}")

            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization"
                },
                "body": json.dumps({
                    "message": "Logout URL generated",
                    "logout_url": logout_url
                })
            }
        else:
            # 환경 변수가 없으면 기본 로그아웃 (쿠키 클리어만)
            logger.warning("Cognito configuration not found, returning basic logout")
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({
                    "message": "Logout successful (cookie clear only)"
                })
            }

    except Exception as e:
        logger.error(f"Logout error: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Internal server error during logout"})
        }
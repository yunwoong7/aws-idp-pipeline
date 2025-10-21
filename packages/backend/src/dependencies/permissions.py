"""
Permission check dependencies for RBAC
"""

from fastapi import Request, HTTPException, Depends
from typing import Dict, Any, List
import boto3
import os
import logging

logger = logging.getLogger(__name__)

# DynamoDB client
dynamodb = boto3.resource('dynamodb')
users_table_name = os.getenv('USERS_TABLE_NAME', 'aws-idp-ai-users')
users_table = dynamodb.Table(users_table_name)

def get_current_user_from_request(request: Request) -> Dict[str, Any]:
    """Extract user info from ALB Cognito headers"""
    from src.routers.auth import decode_cognito_token

    # Check local dev mode via env variable
    auth_disabled = os.getenv("AUTH_DISABLED")
    if auth_disabled == "true":
        return {
            "sub": "admin-local",
            "email": "admin@localhost",
            "name": "Admin",
            "cognito:groups": ["aws-idp-ai-admins"]
        }

    # Auto-detect localhost requests (local development)
    client_host = request.client.host if request.client else None
    if client_host and client_host in ["127.0.0.1", "localhost", "::1"]:
        logger.info(f"Localhost request detected from {client_host} - using local admin user")
        return {
            "sub": "admin-local",
            "email": "admin@localhost",
            "name": "Local Admin",
            "cognito:groups": ["aws-idp-ai-admins"]
        }

    # Get OIDC data from ALB headers
    oidc_data = request.headers.get("x-amzn-oidc-data")
    if not oidc_data:
        raise HTTPException(status_code=401, detail="No authentication data found")

    try:
        # Decode ID token for basic user info
        user_data = decode_cognito_token(oidc_data)

        # Get groups from access token (ID token doesn't include groups)
        access_token = request.headers.get("x-amzn-oidc-accesstoken")
        if access_token:
            try:
                access_data = decode_cognito_token(access_token)
                user_data["cognito:groups"] = access_data.get("cognito:groups", [])
                logger.info(f"👥 Groups from access token: {user_data['cognito:groups']}")
            except Exception as e:
                logger.warning(f"Failed to decode access token for groups: {e}")
                user_data["cognito:groups"] = []
        else:
            user_data["cognito:groups"] = []

        return user_data
    except Exception as e:
        logger.error(f"Failed to decode Cognito token: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

async def get_user_permissions(request: Request) -> Dict[str, Any]:
    """Get current user's permissions from DynamoDB"""
    try:
        cognito_user = get_current_user_from_request(request)
        user_id = cognito_user.get("sub", cognito_user.get("email"))

        # Get user from DynamoDB
        response = users_table.get_item(Key={"user_id": user_id})

        if "Item" not in response:
            # User not in DB yet - check Cognito groups for default permissions
            groups = cognito_user.get("cognito:groups", [])
            if "aws-idp-ai-admins" in groups:
                # Admin has all permissions
                return {
                    "can_create_index": True,
                    "can_delete_index": True,
                    "can_upload_documents": True,
                    "can_delete_documents": True,
                    "accessible_indexes": "*",
                    "available_tabs": ["documents", "analysis", "search", "verification"]
                }
            else:
                # Default user permissions
                return {
                    "can_create_index": False,
                    "can_delete_index": False,
                    "can_upload_documents": False,
                    "can_delete_documents": False,
                    "accessible_indexes": [],
                    "available_tabs": ["search"]
                }

        user_item = response["Item"]
        return user_item.get("permissions", {})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user permissions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get permissions: {str(e)}")

def require_permission(permission_name: str):
    """
    Dependency to check if user has a specific permission

    Usage:
        @router.post("/create", dependencies=[Depends(require_permission("can_create_index"))])
        async def create_index(...):
            ...
    """
    async def permission_checker(request: Request):
        permissions = await get_user_permissions(request)

        if not permissions.get(permission_name, False):
            logger.warning(f"Permission denied: {permission_name} for user")
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission_name} required"
            )

        return permissions

    return Depends(permission_checker)

def require_index_access(index_id_param: str = "index_id"):
    """
    Dependency to check if user has access to a specific index

    Usage:
        @router.get("/documents")
        async def get_documents(index_id: str, _ = Depends(require_index_access())):
            ...

    Args:
        index_id_param: Name of the parameter that contains the index_id
    """
    async def index_access_checker(request: Request, index_id: str):
        permissions = await get_user_permissions(request)
        accessible = permissions.get("accessible_indexes", [])

        # "*" means access to all indexes
        if accessible == "*":
            return True

        # Check if index_id is in the list
        if isinstance(accessible, list) and index_id in accessible:
            return True

        logger.warning(f"Index access denied: {index_id} for user")
        raise HTTPException(
            status_code=403,
            detail=f"Access denied to index: {index_id}"
        )

    return Depends(index_access_checker)

def require_admin(request: Request) -> Dict[str, Any]:
    """
    Dependency to check if user is admin

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_admin)])
        async def admin_endpoint(...):
            ...
    """
    cognito_user = get_current_user_from_request(request)
    groups = cognito_user.get("cognito:groups", [])

    if "aws-idp-ai-admins" not in groups:
        logger.warning(f"Admin access denied for user: {cognito_user.get('email')}")
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    return cognito_user

def require_tab_access(tab_name: str):
    """
    Dependency to check if user has access to a specific tab

    Usage:
        @router.get("/analysis-data", dependencies=[Depends(require_tab_access("analysis"))])
        async def get_analysis_data(...):
            ...
    """
    async def tab_access_checker(request: Request):
        permissions = await get_user_permissions(request)
        available_tabs = permissions.get("available_tabs", [])

        if tab_name not in available_tabs:
            logger.warning(f"Tab access denied: {tab_name} for user")
            raise HTTPException(
                status_code=403,
                detail=f"Access denied to tab: {tab_name}"
            )

        return permissions

    return Depends(tab_access_checker)

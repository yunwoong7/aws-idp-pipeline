"""
User management handlers for RBAC
"""

import os
import json
import boto3
import logging
import base64
from typing import Dict, Any, Optional
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def decode_cognito_token(token: str) -> dict:
    """
    Decode the x-amzn-oidc-data token from ALB
    """
    try:
        # JWT token payload (second part)
        parts = token.split('.')
        if len(parts) != 3:
            raise ValueError("Invalid JWT token format")

        # Base64 decode (add padding)
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)

        decoded_bytes = base64.b64decode(payload)
        decoded_str = decoded_bytes.decode('utf-8')

        return json.loads(decoded_str)
    except Exception as e:
        logger.error(f"Failed to decode Cognito token: {e}")
        raise ValueError("Invalid authentication token")

# DynamoDB client
dynamodb = boto3.resource('dynamodb')
users_table_name = os.getenv('USERS_TABLE_NAME', 'aws-idp-ai-users')
users_table = dynamodb.Table(users_table_name)


def get_current_user_from_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    """Extract user info from ALB Cognito headers or return default local user"""

    # Try to get Cognito user info from ALB headers
    # ALB sets these headers after Cognito authentication
    oidc_data = headers.get('x-amzn-oidc-data') or headers.get('X-Amzn-Oidc-Data')

    if oidc_data:
        try:
            # Decode the OIDC token from ALB
            cognito_user = decode_cognito_token(oidc_data)
            logger.info(f"🔍 Decoded Cognito user data: {json.dumps(cognito_user, indent=2)}")
            logger.info(f"📧 Email: {cognito_user.get('email')}")
            logger.info(f"👥 Groups: {cognito_user.get('cognito:groups', [])}")
            return cognito_user
        except Exception as e:
            logger.warning(f"Failed to decode Cognito token, using local admin: {e}")

    # Fallback to local admin user for development (when AUTH_DISABLED or local testing)
    logger.info("No Cognito headers found, using local admin user")
    return {
        "sub": "admin-local",
        "email": "admin@localhost",
        "name": "Local Admin",
        "cognito:groups": ["aws-idp-ai-admins"]
    }


def create_user_from_cognito(cognito_user: Dict[str, Any]) -> Dict[str, Any]:
    """Create DynamoDB user from Cognito user data"""
    user_id = cognito_user.get("sub", cognito_user.get("email", "unknown"))
    email = cognito_user.get("email", "unknown@example.com")
    # Try to get name from various Cognito attributes
    # Priority: name > given_name + family_name > preferred_username > username > cognito:username > email prefix
    name = (
        cognito_user.get("name") or
        (cognito_user.get("given_name", "") + " " + cognito_user.get("family_name", "")).strip() or
        cognito_user.get("preferred_username") or
        cognito_user.get("username") or
        cognito_user.get("cognito:username") or
        email.split("@")[0]
    )
    groups = cognito_user.get("cognito:groups", [])

    logger.info(f"🔍 Creating user from Cognito data:")
    logger.info(f"   - Email: {email}")
    logger.info(f"   - Name: {name}")
    logger.info(f"   - Groups: {groups}")
    logger.info(f"   - Checking if 'aws-idp-ai-admins' in groups: {'aws-idp-ai-admins' in groups}")

    # Set initial permissions based on Cognito groups
    if "aws-idp-ai-admins" in groups:
        role = "admin"
        permissions = {
            "can_create_index": True,
            "can_delete_index": True,
            "can_upload_documents": True,
            "can_delete_documents": True,
            "accessible_indexes": "*",
            "available_tabs": ["documents", "analysis", "search", "verification"]
        }
        logger.info(f"✅ User assigned ADMIN role (found in aws-idp-ai-admins group)")
    else:
        role = "user"
        permissions = {
            "can_create_index": False,
            "can_delete_index": False,
            "can_upload_documents": False,
            "can_delete_documents": False,
            "accessible_indexes": [],
            "available_tabs": ["search"]
        }
        logger.info(f"⚠️ User assigned USER role (NOT in aws-idp-ai-admins group)")

    timestamp = datetime.utcnow().isoformat()
    user_item = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "role": role,
        "permissions": permissions,
        "status": "active",
        "created_at": timestamp,
        "updated_at": timestamp,
        "last_login_at": timestamp,
    }

    logger.info(f"💾 Saving user to DynamoDB: {email} with role {role}")
    users_table.put_item(Item=user_item)

    return user_item


def handle_get_current_user_permissions(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Get current user's information and permissions"""
    try:
        # Try to get user info from query parameters first (for API Gateway calls)
        query_params = event.get("queryStringParameters") or {}
        user_id = query_params.get("user_id")
        email = query_params.get("email")
        name = query_params.get("name")
        groups_str = query_params.get("groups")

        # Parse groups from comma-separated string
        groups = groups_str.split(",") if groups_str else []

        # If not in query params, try headers (for ALB calls)
        if not user_id or not email:
            headers = event.get("headers", {})
            cognito_user = get_current_user_from_headers(headers)
            user_id = cognito_user.get("sub", cognito_user.get("email"))
            email = cognito_user.get("email")
            name = cognito_user.get("name") or cognito_user.get("username")
            groups = cognito_user.get("cognito:groups", [])

        logger.info(f"Getting permissions for user: {email}")

        # Try to get user from DynamoDB
        response = users_table.get_item(Key={"user_id": user_id})

        if "Item" not in response:
            # First login - create user automatically
            logger.info(f"User not found in DB, creating: {email}")
            # Create cognito_user object for create_user_from_cognito
            cognito_user = {
                "sub": user_id,
                "email": email,
                "name": name,
                "cognito:groups": groups
            }
            user_item = create_user_from_cognito(cognito_user)
        else:
            user_item = response["Item"]

            # Update last login time
            users_table.update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET last_login_at = :timestamp",
                ExpressionAttributeValues={":timestamp": datetime.utcnow().isoformat()}
            )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            },
            "body": json.dumps(user_item, default=str)
        }

    except Exception as e:
        logger.error(f"Failed to get user permissions: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": f"Failed to get user permissions: {str(e)}"})
        }


def handle_list_users(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """List all users"""
    try:
        logger.info("Fetching all users from DynamoDB")

        response = users_table.scan()
        items = response.get("Items", [])

        # Sort by created_at descending
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            },
            "body": json.dumps(items, default=str)
        }

    except Exception as e:
        logger.error(f"Failed to list users: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": f"Failed to list users: {str(e)}"})
        }


def handle_update_user_permissions(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Update user permissions"""
    try:
        # Get user_id from path parameters
        path_parameters = event.get("pathParameters", {})
        user_id = path_parameters.get("user_id")

        if not user_id:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "user_id is required"})
            }

        # Parse request body
        body = event.get("body")
        if isinstance(body, str):
            body = json.loads(body)

        permissions = body.get("permissions")
        role = body.get("role")

        if not permissions:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "permissions is required"})
            }

        logger.info(f"Updating permissions for user_id: {user_id}")

        # Build update expression
        # Note: "permissions" is a DynamoDB reserved keyword, so we use ExpressionAttributeNames
        update_expr = "SET #permissions = :permissions, updated_at = :timestamp"
        expr_values = {
            ":permissions": permissions,
            ":timestamp": datetime.utcnow().isoformat(),
        }
        expr_names = {
            "#permissions": "permissions"
        }

        # Update role if provided
        if role:
            update_expr += ", #role = :role"
            expr_values[":role"] = role
            expr_names["#role"] = "role"

        # Update user
        users_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )

        logger.info(f"Successfully updated permissions for user_id: {user_id}")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "PUT, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            },
            "body": json.dumps({"message": "Permissions updated successfully"})
        }

    except Exception as e:
        logger.error(f"Failed to update permissions: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": f"Failed to update permissions: {str(e)}"})
        }


def handle_update_user_status(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Update user status"""
    try:
        # Get user_id from path parameters
        path_parameters = event.get("pathParameters", {})
        user_id = path_parameters.get("user_id")

        if not user_id:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "user_id is required"})
            }

        # Parse request body
        body = event.get("body")
        if isinstance(body, str):
            body = json.loads(body)

        status = body.get("status")

        if status not in ["active", "inactive"]:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Status must be 'active' or 'inactive'"})
            }

        logger.info(f"Updating status for user_id: {user_id} to {status}")

        # Update user status
        users_table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #status = :status, updated_at = :timestamp",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": status,
                ":timestamp": datetime.utcnow().isoformat(),
            }
        )

        logger.info(f"Successfully updated status for user_id: {user_id}")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            },
            "body": json.dumps({"message": f"User status updated to {status}"})
        }

    except Exception as e:
        logger.error(f"Failed to update status: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": f"Failed to update status: {str(e)}"})
        }

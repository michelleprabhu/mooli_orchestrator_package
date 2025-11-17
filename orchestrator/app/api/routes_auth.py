"""
Authentication API Routes
=========================

Provides login/logout endpoints with Microsoft Entra ID (MSAL) authentication.
"""

import os
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from ..services.auth_service import (
    authenticate_user, 
    create_jwt_token, 
    validate_jwt_token,
    list_dev_users
)
from ..msal_auth.entra_auth import (
    validate_entra_token,
    get_authorization_url,
    exchange_code_for_token,
    FRONTEND_URL
)
from ..core.logging_config import get_logger, audit_logger, log_exception
from fastapi.responses import RedirectResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
security = HTTPBearer(auto_error=False)

# Request/Response Models
class LoginRequest(BaseModel):
    username: str
    password: Optional[str] = None  # Optional in development mode
    org_id: Optional[str] = "org_001"

class LoginResponse(BaseModel):
    success: bool
    token: str
    user: dict
    expires_at: str
    message: str

class UserResponse(BaseModel):
    user_id: str
    username: str
    full_name: str
    department: Optional[str]
    is_admin: bool
    is_connected: bool = False

class DevUsersResponse(BaseModel):
    users: list[UserResponse]
    total: int
    development_mode: bool


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, http_request: Request):
    """
    Login endpoint with development bypass.
    
    Development mode: Password optional, creates JWT for any valid username
    Production mode: Validates password and creates secure JWT
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    environment = os.getenv("ENVIRONMENT", "production").lower()
    
    logger.info(f"Login attempt | username={request.username} | org={request.org_id} | ip={client_ip} | env={environment}")
    
    try:
        # Authenticate user
        user_data = await authenticate_user(
            username=request.username,
            password=request.password or "",  # Empty password in dev mode
            org_id=request.org_id
        )
        
        if not user_data:
            logger.warning(f"❌ Authentication failed | username={request.username} | org={request.org_id} | ip={client_ip}")
            audit_logger.log_login(
                user_id=request.username,  # Use username since auth failed
                username=request.username,
                success=False,
                ip_address=client_ip
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        # Create JWT token
        try:
            jwt_token = create_jwt_token(user_data)
            
            # Calculate expiry time
            from datetime import timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            
            logger.info(f"✅ Login successful | user={user_data['username']} | user_id={user_data['user_id']} | org={request.org_id} | ip={client_ip}")
            
            # Log successful authentication
            audit_logger.log_login(
                user_id=user_data['user_id'],
                username=user_data['username'],
                success=True,
                ip_address=client_ip
            )
            
            return LoginResponse(
                success=True,
                token=jwt_token,
                user=user_data,
                expires_at=expires_at.isoformat(),
                message=f"Welcome back, {user_data['full_name'] or user_data['username']}!"
            )
            
        except Exception as e:
            logger.error(f"❌ JWT token creation failed for user {user_data['username']}")
            log_exception(logger, e, {"username": user_data['username'], "ip_address": client_ip})
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication token creation failed"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )


@router.post("/logout")
async def logout():
    """
    Logout endpoint.
    
    In JWT-based auth, logout is typically handled client-side by discarding the token.
    This endpoint can be used for logging/audit purposes.
    """
    return {
        "success": True,
        "message": "Logged out successfully"
    }


@router.get("/me")
async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """
    Get current authenticated user information.
    
    Validates Microsoft Entra ID (MSAL) tokens.
    Falls back to development mode if no token provided in development environment.
    """
    is_development = os.getenv("ENVIRONMENT", "development") == "development"
    
    if is_development and not credentials:
        # Development mode without token - return default user
        dev_users = await list_dev_users()
        if dev_users:
            default_user = dev_users[0]  # Return first dev user
            return {
                "user_id": default_user["user_id"],
                "username": default_user["username"],
                "full_name": default_user["full_name"],
                "email": default_user.get("username") + "@dev.local",
                "department": default_user.get("department"),
                "is_admin": default_user.get("is_admin", False),
                "authenticated": True,
                "auth_type": "development",
                "development_mode": True
            }
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    # Try to validate as MSAL token first
    try:
        msal_payload = await validate_entra_token(credentials.credentials)
        if msal_payload:
            # Extract user information from MSAL token
            oid = msal_payload.get("oid") or msal_payload.get("sub")
            email = msal_payload.get("email") or msal_payload.get("preferred_username")
            name = msal_payload.get("name") or f"{msal_payload.get('given_name', '')} {msal_payload.get('family_name', '')}".strip()
            
            logger.info(f"✅ MSAL authentication successful | user={email} | oid={oid}")
            
            return {
                "user_id": oid,
                "username": email,
                "full_name": name,
                "email": email,
                "oid": oid,
                "roles": msal_payload.get("roles", []),
                "is_admin": "Admin" in msal_payload.get("roles", []),
                "authenticated": True,
                "auth_type": "msal",
                "development_mode": is_development
            }
    except Exception as e:
        logger.warning(f"MSAL token validation failed: {e}")
    
    # Fallback to legacy JWT validation if MSAL fails
    token_data = validate_jwt_token(credentials.credentials)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    return {
        "user_id": token_data["user_id"],
        "username": token_data["username"],
        "full_name": token_data.get("full_name", token_data["username"]),
        "email": token_data.get("email", token_data["username"]),
        "org_id": token_data.get("org_id"),
        "is_admin": token_data.get("is_admin", False),
        "authenticated": True,
        "auth_type": "jwt_legacy",
        "development_mode": is_development
    }


@router.get("/users/dev", response_model=DevUsersResponse)
async def get_development_users():
    """
    Get available development users for login.
    Only available in development mode.
    """
    is_development = os.getenv("ENVIRONMENT", "development") == "development"
    
    if not is_development:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Development users only available in development mode"
        )
    
    try:
        dev_users = await list_dev_users()
        
        users = [
            UserResponse(
                user_id=user["user_id"],
                username=user["username"],
                full_name=user["full_name"],
                department=user.get("department"),
                is_admin=user.get("is_admin", False),
                is_connected=False  # TODO: Check WebSocket connections
            )
            for user in dev_users
        ]
        
        return DevUsersResponse(
            users=users,
            total=len(users),
            development_mode=True
        )
        
    except Exception as e:
        logger.error(f"Failed to get development users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve development users"
        )


@router.get("/validate")
async def validate_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """
    Validate JWT token.
    
    Returns token validation status and user info if valid.
    """
    if not credentials:
        return {
            "valid": False,
            "message": "No token provided"
        }
    
    token_data = validate_jwt_token(credentials.credentials)
    if not token_data:
        return {
            "valid": False,
            "message": "Invalid or expired token"
        }
    
    return {
        "valid": True,
        "user": token_data,
        "message": "Token is valid"
    }


@router.get("/status")
async def get_auth_status():
    """Get authentication system status."""
    is_development = os.getenv("ENVIRONMENT", "development") == "development"
    multi_user_enabled = os.getenv("MULTI_USER_MODE", "true").lower() == "true"
    
    return {
        "development_mode": is_development,
        "multi_user_enabled": multi_user_enabled,
        "jwt_enabled": True,
        "development_bypass": is_development,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ========== Microsoft Entra ID OAuth Endpoints ==========

@router.get("/entra/login")
async def entra_login():
    """
    Initiate Microsoft Entra ID OAuth flow.
    Redirects user to Microsoft sign-in page.
    """
    try:
        # Generate random state for CSRF protection
        import secrets
        state = secrets.token_urlsafe(32)
        
        # Get Microsoft authorization URL
        auth_url = get_authorization_url(state=state)
        
        logger.info(f"🔐 Initiating Microsoft OAuth flow | redirect={auth_url[:80]}...")
        
        # Redirect user to Microsoft sign-in
        return RedirectResponse(url=auth_url)
        
    except Exception as e:
        logger.error(f"Error initiating OAuth flow: {e}")
        log_exception(logger, e, {"endpoint": "/entra/login"})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate authentication"
        )


@router.get("/entra/callback")
async def entra_callback(code: Optional[str] = None, error: Optional[str] = None, state: Optional[str] = None):
    """
    OAuth callback endpoint.
    Microsoft redirects here after user signs in.
    """
    try:
        # Handle error from Microsoft
        if error:
            logger.error(f"❌ Microsoft OAuth error: {error}")
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error={error}")
        
        # Validate we have the authorization code
        if not code:
            logger.error("❌ No authorization code received")
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=no_code")
        
        logger.info(f"🔐 Received OAuth callback | code={code[:20]}... | state={state}")
        
        # Exchange code for token
        token_response = await exchange_code_for_token(code)
        if not token_response:
            logger.error("❌ Failed to exchange code for token")
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=token_exchange_failed")
        
        # Extract tokens
        access_token = token_response.get("access_token")
        id_token = token_response.get("id_token")
        
        # Use ID token for authentication (not access token)
        if not id_token:
            logger.error("❌ No ID token in response")
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=no_token")
        
        logger.info(f"🔐 Validating ID token (not access token) for authentication")
        
        # Validate the ID token (this is for authentication, not API access)
        token_payload = await validate_entra_token(id_token)
        if not token_payload:
            logger.error("❌ ID token validation failed")
            return RedirectResponse(url=f"{FRONTEND_URL}/login?error=invalid_token")
        
        # Extract user info
        user_id = token_payload.get("oid") or token_payload.get("sub")
        email = token_payload.get("email") or token_payload.get("preferred_username")
        name = token_payload.get("name", "")
        
        logger.info(f"✅ Microsoft authentication successful | user={email} | oid={user_id}")
        
        # Create JWT token for our system
        user_data = {
            "user_id": user_id,
            "username": email,
            "full_name": name,
            "email": email,
            "is_admin": False,  # TODO: Check roles from token
            "org_id": "org_001"
        }
        jwt_token = create_jwt_token(user_data)
        
        # Create response with redirect to dashboard
        response = RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
        
        # Set secure HTTP-only cookie with the JWT token
        response.set_cookie(
            key="auth_token",
            value=jwt_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=86400,  # 24 hours
        )
        
        logger.info(f"✅ User authenticated and redirected to dashboard | user={email}")
        
        return response
        
    except Exception as e:
        logger.error(f"❌ OAuth callback error: {e}")
        log_exception(logger, e, {"endpoint": "/entra/callback"})
        return RedirectResponse(url=f"{FRONTEND_URL}/login?error=callback_failed")
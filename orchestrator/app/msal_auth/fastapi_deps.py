# Essential FastAPI dependency for Microsoft Entra ID authentication
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any
import logging
from .entra_auth import validate_entra_token

logger = logging.getLogger(__name__)
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """FastAPI dependency to get current user from Microsoft Entra ID token"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    token = credentials.credentials
    payload = await validate_entra_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Extract user information
    oid = payload.get("oid") or payload.get("sub")
    email = payload.get("email") or payload.get("preferred_username")
    name = payload.get("name") or f"{payload.get('given_name', '')} {payload.get('family_name', '')}".strip()
    
    return {
        "id": oid,
        "oid": oid,
        "email": email,
        "name": name,
        "roles": payload.get("roles", []),
        "raw_payload": payload
    }

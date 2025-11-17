"""FastAPI dependency providers for orchestrator services."""

import os
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..core.openai_proxy import get_openai_proxy
from ..core.openai_manager import get_openai_client
from ..msal_auth.entra_auth import validate_entra_token
from ..services.auth_service import validate_jwt_token, list_dev_users

security = HTTPBearer(auto_error=False)


async def get_prompt_agent(request: Request):
	"""Dependency to get prompt response agent from app state."""
	if hasattr(request.app.state, 'prompt_agent') and request.app.state.prompt_agent:
		return request.app.state.prompt_agent
	else:
		# Use global OpenAI client instead of creating new instances
		from ..agents import PromptResponseAgent
		return PromptResponseAgent(
			openai_client=get_openai_client()
		)


async def get_openai_proxy():
	"""Dependency to get the global OpenAI proxy."""
	return get_openai_proxy()


async def get_openai_client_dependency():
	"""Dependency to get the global OpenAI client."""
	return get_openai_client()


async def get_current_user_msal(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
	"""
	FastAPI dependency to get current user from MSAL token.
	
	Validates Microsoft Entra ID tokens and returns user information.
	Falls back to development mode in development environment.
	"""
	is_development = os.getenv("ENVIRONMENT", "development") == "development"
	
	if is_development and not credentials:
		# Development mode without token - return default user
		dev_users = await list_dev_users()
		if dev_users:
			default_user = dev_users[0]
			return {
				"user_id": default_user["user_id"],
				"username": default_user["username"],
				"full_name": default_user["full_name"],
				"email": default_user.get("username") + "@dev.local",
				"is_admin": default_user.get("is_admin", False),
				"auth_type": "development"
			}
	
	if not credentials:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Authentication required"
		)
	
	# Try MSAL token validation first
	try:
		msal_payload = await validate_entra_token(credentials.credentials)
		if msal_payload:
			oid = msal_payload.get("oid") or msal_payload.get("sub")
			email = msal_payload.get("email") or msal_payload.get("preferred_username")
			name = msal_payload.get("name") or f"{msal_payload.get('given_name', '')} {msal_payload.get('family_name', '')}".strip()
			
			return {
				"user_id": oid,
				"username": email,
				"full_name": name,
				"email": email,
				"oid": oid,
				"roles": msal_payload.get("roles", []),
				"is_admin": "Admin" in msal_payload.get("roles", []),
				"auth_type": "msal"
			}
	except Exception:
		pass
	
	# Fallback to legacy JWT validation
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
		"is_admin": token_data.get("is_admin", False),
		"auth_type": "jwt_legacy"
	}
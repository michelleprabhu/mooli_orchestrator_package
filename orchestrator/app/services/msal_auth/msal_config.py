"""
MSAL Configuration
==================

Configuration for Microsoft Authentication Library integration.
"""

import os
from typing import List, Optional
from pydantic import BaseModel, Field


class MSALConfig(BaseModel):
    """MSAL configuration settings."""
    
    # Azure AD Application Settings
    client_id: str = Field(
        default_factory=lambda: os.getenv("AZURE_CLIENT_ID", ""),
        description="Azure AD Application (client) ID"
    )
    
    client_secret: Optional[str] = Field(
        default_factory=lambda: os.getenv("AZURE_CLIENT_SECRET"),
        description="Azure AD Application client secret (for confidential clients)"
    )
    
    tenant_id: str = Field(
        default_factory=lambda: os.getenv("AZURE_TENANT_ID", "common"),
        description="Azure AD Tenant ID or 'common' for multi-tenant"
    )
    
    # Authority URL
    authority: Optional[str] = Field(
        default=None,
        description="Full authority URL (overrides tenant_id if provided)"
    )
    
    # Redirect URIs
    redirect_uri: str = Field(
        default_factory=lambda: os.getenv(
            "AZURE_REDIRECT_URI", 
            "http://localhost:8000/api/v1/auth/msal/callback"
        ),
        description="OAuth2 redirect URI"
    )
    
    post_logout_redirect_uri: str = Field(
        default_factory=lambda: os.getenv(
            "AZURE_POST_LOGOUT_REDIRECT_URI",
            "http://localhost:8000"
        ),
        description="Redirect URI after logout"
    )
    
    # Scopes
    scopes: List[str] = Field(
        default_factory=lambda: [
            "User.Read",  # Read user profile
            "openid",     # OpenID Connect
            "profile",    # Basic profile info
            "email"       # Email address
        ],
        description="OAuth2 scopes to request"
    )
    
    # Token validation
    validate_tokens: bool = Field(
        default=True,
        description="Whether to validate tokens with Azure AD"
    )
    
    # Session configuration
    token_cache_enabled: bool = Field(
        default=True,
        description="Enable token caching"
    )
    
    # Development settings
    enable_dev_bypass: bool = Field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "production").lower() == "development",
        description="Allow authentication bypass in development mode"
    )
    
    @property
    def authority_url(self) -> str:
        """Get the full authority URL."""
        if self.authority:
            return self.authority
        return f"https://login.microsoftonline.com/{self.tenant_id}"
    
    @property
    def is_configured(self) -> bool:
        """Check if MSAL is properly configured."""
        return bool(self.client_id and self.tenant_id)
    
    def get_authorization_url_params(self) -> dict:
        """Get parameters for authorization URL generation."""
        return {
            "scopes": self.scopes,
            "redirect_uri": self.redirect_uri,
        }
    
    def validate_config(self) -> tuple[bool, Optional[str]]:
        """
        Validate the MSAL configuration.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.client_id:
            return False, "AZURE_CLIENT_ID is required"
        
        if not self.tenant_id:
            return False, "AZURE_TENANT_ID is required"
        
        if not self.redirect_uri:
            return False, "AZURE_REDIRECT_URI is required"
        
        # For confidential client flow (server-side), client secret is typically required
        # For public client flow (SPA), it's not needed
        # We'll support both modes
        
        return True, None


# Global configuration instance
msal_config = MSALConfig()

"""
Microsoft Authentication Library (MSAL) Integration
====================================================

Provides Azure AD/Microsoft authentication for the orchestrator.
"""

from .msal_service import MSALService, get_msal_service
from .msal_config import MSALConfig

__all__ = ["MSALService", "get_msal_service", "MSALConfig"]

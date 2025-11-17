# Essential Microsoft Entra ID authentication for backend
import os
import logging
from typing import Optional, Dict, Any
from jose import jwt, JWTError
import httpx
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Microsoft Entra ID Configuration from environment
TENANT_ID = os.getenv("ENTRA_TENANT_ID", "c6d7b4e0-4445-4400-9e33-304791e9f706")
CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "23402417-0408-46f0-a336-fe3ff94b07af")
CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("ENTRA_REDIRECT_URI", "http://localhost:8000/api/v1/auth/entra/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Microsoft Entra ID endpoints
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
JWKS_URL = f"{AUTHORITY}/discovery/v2.0/keys"
ISSUER_V2 = f"{AUTHORITY}/v2.0"
ISSUER_V1 = f"https://sts.windows.net/{TENANT_ID}/"  # v1.0 endpoint format
AUTHORIZE_URL = f"{AUTHORITY}/oauth2/v2.0/authorize"
TOKEN_URL = f"{AUTHORITY}/oauth2/v2.0/token"

# Valid audiences for token validation
# Include Microsoft Graph audience since we request User.Read scope
VALID_AUDIENCES = [
    CLIENT_ID, 
    f"api://{CLIENT_ID}",
    "00000003-0000-0000-c000-000000000000"  # Microsoft Graph
]

# Valid issuers (v1.0 and v2.0 formats)
VALID_ISSUERS = [ISSUER_V1, ISSUER_V2]

async def validate_entra_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate Microsoft Entra ID JWT token"""
    try:
        # Get token header and payload without verification for debugging
        unverified_header = jwt.get_unverified_header(token)
        unverified_payload = jwt.get_unverified_claims(token)
        kid = unverified_header.get('kid')
        
        logger.info(f"🔍 Token validation - kid: {kid}")
        logger.info(f"🔍 Token issuer (iss): {unverified_payload.get('iss')}")
        logger.info(f"🔍 Token audience (aud): {unverified_payload.get('aud')}")
        logger.info(f"🔍 Expected issuers: {VALID_ISSUERS}")
        logger.info(f"🔍 Expected audiences: {VALID_AUDIENCES}")
        logger.info(f"🔍 JWKS URL: {JWKS_URL}")
        
        # Fetch JWKS
        async with httpx.AsyncClient() as client:
            response = await client.get(JWKS_URL)
            response.raise_for_status()
            jwks = response.json()
        
        logger.info(f"🔍 Fetched {len(jwks.get('keys', []))} keys from JWKS")
        
        # Find matching key
        key = None
        for jwk in jwks['keys']:
            if jwk['kid'] == kid:
                key = jwk
                logger.info(f"✅ Found matching key for kid: {kid}")
                break
        
        if not key:
            logger.error(f"❌ No matching key found for kid: {kid}")
            logger.error(f"Available kids: {[k.get('kid') for k in jwks.get('keys', [])]}")
            return None
        
        # Verify token with relaxed options first
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                options={
                    "verify_signature": True,
                    "verify_aud": False,  # Don't verify audience yet
                    "verify_iss": False,  # Don't verify issuer yet
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                }
            )
            logger.info("✅ Token signature verified successfully")
        except Exception as e:
            logger.error(f"❌ Signature verification failed: {str(e)}")
            raise
        
        # Validate issuer manually
        iss_claim = payload.get('iss')
        if iss_claim not in VALID_ISSUERS:
            logger.error(f"❌ Invalid issuer: {iss_claim} (expected one of {VALID_ISSUERS})")
            return None
        logger.info(f"✅ Issuer validated: {iss_claim}")
        
        # Validate audience
        aud_claim = payload.get('aud')
        if isinstance(aud_claim, str):
            if aud_claim not in VALID_AUDIENCES:
                logger.error(f"❌ Invalid audience: {aud_claim} (expected one of {VALID_AUDIENCES})")
                return None
            logger.info(f"✅ Audience validated: {aud_claim}")
        elif isinstance(aud_claim, list):
            if not any(aud in VALID_AUDIENCES for aud in aud_claim):
                logger.error(f"❌ Invalid audience: {aud_claim} (expected one of {VALID_AUDIENCES})")
                return None
            logger.info(f"✅ Audience validated: {aud_claim}")
        
        logger.info(f"✅ Token fully validated for user: {payload.get('preferred_username') or payload.get('upn') or payload.get('email')}")
        return payload
        
    except JWTError as e:
        logger.error(f"JWT validation error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        return None

async def get_graph_token() -> Optional[str]:
    """Get access token for Microsoft Graph API"""
    try:
        if not CLIENT_SECRET:
            logger.error("ENTRA_CLIENT_SECRET environment variable not set")
            return None
        
        token_data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(TOKEN_URL, data=token_data)
            response.raise_for_status()
            return response.json().get("access_token")
            
    except Exception as e:
        logger.error(f"Error getting Graph token: {str(e)}")
        return None


def get_authorization_url(state: str = "random_state") -> str:
    """
    Generate Microsoft OAuth authorization URL.
    User will be redirected here to sign in.
    """
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": "openid profile email User.Read",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> Optional[Dict[str, Any]]:
    """
    Exchange authorization code for access token.
    Called after Microsoft redirects back with the code.
    """
    try:
        if not CLIENT_SECRET:
            logger.error("ENTRA_CLIENT_SECRET environment variable not set")
            return None
        
        token_data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(TOKEN_URL, data=token_data)
            response.raise_for_status()
            token_response = response.json()
            
            logger.info("✅ Successfully exchanged authorization code for token")
            return token_response
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error exchanging code for token: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Error exchanging code for token: {str(e)}")
        return None

"""
Gateway API Routes
==================

FastAPI routes for LLM Router configuration management.
Provides endpoints for DynaRoute integration frontend.
"""

import os
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..services.dynaroute_service import get_dynaroute_service, DynaRouteConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gateway", tags=["gateway"])

# Pydantic models for API requests/responses
class ProviderConfig(BaseModel):
    enabled: bool
    api_key: str = ""
    default_model: str

class DynamicConfig(BaseModel):
    strategy: str = "smart"  # value, smart, turbo

class RouterConfigRequest(BaseModel):
    enabled: bool
    mode: str  # static, dynamic
    providers: Dict[str, ProviderConfig]
    dynamic: DynamicConfig

class ProviderTestRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None
    model: Optional[str] = None

class ProviderTestResponse(BaseModel):
    ok: bool
    latency_ms: float
    message: str

class RoutePreviewRequest(BaseModel):
    input: str
    metadata: Optional[Dict[str, Any]] = None

class RoutePreviewResponse(BaseModel):
    provider: str
    model: str
    reason: str

@router.get("/config")
async def get_router_config():
    """
    Get current router configuration.
    Returns the configuration without sensitive API keys.
    """
    try:
        service = get_dynaroute_service()
        config_info = service.get_config_info()

        # Create sanitized config for frontend
        sanitized_config = {
            "enabled": config_info.get("dynaroute_enabled", True),
            "mode": "static",  # Default mode
            "providers": {
                "dynaroute": {
                    "enabled": config_info.get("dynaroute_enabled", True),
                    "api_key": "••••••••" if config_info.get("api_key_configured") else "",
                    "default_model": "auto"
                },
                "openai": {
                    "enabled": True,  # Always enabled as fallback
                    "api_key": "••••••••",
                    "default_model": "gpt-4o-mini"
                },
                "anthropic": {
                    "enabled": False,
                    "api_key": "",
                    "default_model": "claude-3-5-sonnet"
                },
                "gemini": {
                    "enabled": False,
                    "api_key": "",
                    "default_model": "gemini-1.5-flash"
                }
            },
            "dynamic": {
                "strategy": "smart"
            }
        }

        return sanitized_config

    except Exception as e:
        logger.error(f"Failed to get router config: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve configuration")

@router.post("/config")
async def update_router_config(config: RouterConfigRequest):
    """
    Update router configuration.
    Handles secure storage of API keys and configuration updates.
    """
    try:
        logger.info(f"Updating router configuration: enabled={config.enabled}, mode={config.mode}")

        # Update DynaRoute configuration
        dynaroute_provider = config.providers.get("dynaroute")
        if dynaroute_provider:
            # Create new DynaRoute config
            dynaroute_config = DynaRouteConfig(
                enabled=dynaroute_provider.enabled,
                api_key=dynaroute_provider.api_key if dynaroute_provider.api_key != "••••••••" else None,
                timeout=30,
                circuit_breaker_threshold=3
            )

            # Update the global service
            service = get_dynaroute_service(dynaroute_config)

            logger.info(f"DynaRoute configuration updated: enabled={dynaroute_provider.enabled}")

        # TODO: Store other provider configurations (OpenAI, Anthropic, Gemini)
        # For now, we only handle DynaRoute since others use direct proxies

        return {"status": "success", "message": "Configuration updated successfully"}

    except Exception as e:
        logger.error(f"Failed to update router config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update configuration")

@router.post("/test", response_model=ProviderTestResponse)
async def test_provider(request: ProviderTestRequest):
    """
    Test connectivity to a specific provider.
    """
    try:
        import time
        start_time = time.time()

        if request.provider == "dynaroute":
            service = get_dynaroute_service()

            # Test with a simple message
            test_messages = [{"role": "user", "content": "ping"}]
            response = await service.chat_completion(
                messages=test_messages,
                model="auto",
                max_tokens=5,
                user_id="test",
                service_name="gateway_test"
            )

            latency_ms = (time.time() - start_time) * 1000

            if hasattr(response, 'choices') and response.choices:
                return ProviderTestResponse(
                    ok=True,
                    latency_ms=latency_ms,
                    message="DynaRoute connection successful"
                )
            else:
                return ProviderTestResponse(
                    ok=False,
                    latency_ms=latency_ms,
                    message="DynaRoute returned invalid response"
                )

        elif request.provider == "openai":
            # Test OpenAI fallback
            from ..core.openai_proxy import get_openai_proxy
            proxy = get_openai_proxy()

            health = await proxy.health_check()
            latency_ms = (time.time() - start_time) * 1000

            return ProviderTestResponse(
                ok=health.get("status") == "healthy",
                latency_ms=latency_ms,
                message=f"OpenAI status: {health.get('status', 'unknown')}"
            )

        else:
            return ProviderTestResponse(
                ok=False,
                latency_ms=0,
                message=f"Provider {request.provider} not implemented yet"
            )

    except Exception as e:
        logger.error(f"Provider test failed for {request.provider}: {e}")
        return ProviderTestResponse(
            ok=False,
            latency_ms=0,
            message=f"Test failed: {str(e)}"
        )

@router.post("/route/preview", response_model=RoutePreviewResponse)
async def preview_routing(request: RoutePreviewRequest):
    """
    Preview which provider and model would be selected for a given input.
    """
    try:
        service = get_dynaroute_service()

        # Get service configuration to determine routing logic
        config_info = service.get_config_info()

        if config_info.get("dynaroute_enabled") and config_info.get("dynaroute_available"):
            return RoutePreviewResponse(
                provider="dynaroute",
                model="auto (cost-optimized)",
                reason="DynaRoute is enabled and available"
            )
        else:
            return RoutePreviewResponse(
                provider="openai",
                model="gpt-4o-mini",
                reason="DynaRoute unavailable, using OpenAI fallback"
            )

    except Exception as e:
        logger.error(f"Route preview failed: {e}")
        return RoutePreviewResponse(
            provider="openai",
            model="gpt-4o-mini",
            reason=f"Error occurred, using fallback: {str(e)}"
        )

@router.get("/status")
async def get_gateway_status():
    """
    Get overall gateway and provider status.
    """
    try:
        service = get_dynaroute_service()

        # Get health status
        health = await service.health_check()
        metrics = service.get_metrics()

        return {
            "status": "healthy" if health.get("status") == "healthy" else "degraded",
            "providers": {
                "dynaroute": {
                    "available": health.get("dynaroute", {}).get("available", False),
                    "enabled": health.get("dynaroute", {}).get("enabled", False)
                },
                "openai": {
                    "available": health.get("openai", {}).get("available", False),
                    "enabled": True
                }
            },
            "metrics": {
                "total_requests": metrics.get("total_requests", 0),
                "dynaroute_requests": metrics.get("dynaroute_requests", 0),
                "fallback_requests": metrics.get("openai_fallback_requests", 0),
                "success_rate": metrics.get("success_rate", 0),
                "cost_savings": metrics.get("cost_savings", 0)
            },
            "circuit_breaker": {
                "is_open": metrics.get("circuit_breaker_open", False),
                "failure_count": metrics.get("circuit_breaker_failures", 0)
            }
        }

    except Exception as e:
        logger.error(f"Failed to get gateway status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
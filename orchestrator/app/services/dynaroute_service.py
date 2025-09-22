"""
DynaRoute Service
================

Provides cost-optimized AI model routing with automatic fallback to OpenAI.
This service acts as a drop-in replacement for direct OpenAI calls while
maintaining full compatibility with existing code.

Features:
- Primary: DynaRoute for 70% cost reduction
- Fallback: OpenAI GlobalLLMProxy for reliability
- Compatible interface with existing chat_completion calls
- Automatic error handling and circuit breaker protection
- Response format normalization
"""

import logging
import os
import time
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# DynaRoute client
try:
    from dynaroute import DynaRouteClient
    DYNAROUTE_AVAILABLE = True
except ImportError:
    DYNAROUTE_AVAILABLE = False
    # Create a mock DynaRouteClient class to prevent errors
    class DynaRouteClient:
        def __init__(self, *args, **kwargs):
            pass
        def chat(self, *args, **kwargs):
            raise Exception("DynaRoute not available - install the DynaRoute package from https://dynaroute.vizuara.ai/")

# OpenAI proxy for fallback
from ..core.openai_proxy import get_openai_proxy

logger = logging.getLogger(__name__)

# Log DynaRoute availability after logger is defined
if not DYNAROUTE_AVAILABLE:
    logger.warning("DynaRoute client not available - will only use OpenAI fallback")
    logger.info("To install DynaRoute, visit https://dynaroute.vizuara.ai/ for installation instructions")

@dataclass
class DynaRouteConfig:
    """Configuration for DynaRoute service"""
    enabled: bool = True
    api_key: Optional[str] = None
    timeout: int = 30
    max_retries: int = 2
    circuit_breaker_threshold: int = 3
    circuit_breaker_timeout: int = 60

    @classmethod
    def from_environment(cls) -> 'DynaRouteConfig':
        """Create configuration from environment variables"""
        return cls(
            enabled=os.getenv("DYNAROUTE_ENABLED", "true").lower() == "true",
            api_key=os.getenv("DYNAROUTE_API_KEY"),
            timeout=int(os.getenv("DYNAROUTE_TIMEOUT", "30")),
            max_retries=int(os.getenv("DYNAROUTE_MAX_RETRIES", "2")),
            circuit_breaker_threshold=int(os.getenv("DYNAROUTE_CIRCUIT_BREAKER_THRESHOLD", "3")),
            circuit_breaker_timeout=int(os.getenv("DYNAROUTE_CIRCUIT_BREAKER_TIMEOUT", "60"))
        )

@dataclass
class CircuitBreaker:
    """Simple circuit breaker for DynaRoute failures"""
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    is_open: bool = False

class DynaRouteService:
    """
    Service that routes requests through DynaRoute with OpenAI fallback.

    Provides the same interface as OpenAI proxy but with cost optimization.
    """

    def __init__(self, config: Optional[DynaRouteConfig] = None):
        self.config = config or DynaRouteConfig.from_environment()
        self.circuit_breaker = CircuitBreaker()
        self.openai_proxy = get_openai_proxy()

        # Initialize DynaRoute client if available and configured
        self.dynaroute_client = None
        if DYNAROUTE_AVAILABLE and self.config.enabled:
            self._initialize_dynaroute_client()

        # Metrics tracking
        self.metrics = {
            "total_requests": 0,
            "dynaroute_requests": 0,
            "openai_fallback_requests": 0,
            "failures": 0,
            "cost_savings": 0.0
        }

    def _initialize_dynaroute_client(self):
        """Initialize DynaRoute client with API key"""
        api_key = self.config.api_key or os.getenv("DYNAROUTE_API_KEY")

        if not api_key:
            logger.warning("DYNAROUTE_API_KEY not provided - DynaRoute disabled")
            self.config.enabled = False
            return

        try:
            self.dynaroute_client = DynaRouteClient(api_key=api_key)
            logger.info("DynaRoute client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DynaRoute client: {e}")
            self.config.enabled = False

    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker should block DynaRoute requests"""
        if not self.circuit_breaker.is_open:
            return False

        # Check if enough time has passed to try again
        if self.circuit_breaker.last_failure_time:
            time_since_failure = time.time() - self.circuit_breaker.last_failure_time
            if time_since_failure >= self.config.circuit_breaker_timeout:
                # Reset circuit breaker for retry
                self.circuit_breaker.is_open = False
                self.circuit_breaker.failure_count = 0
                logger.info("Circuit breaker reset - attempting DynaRoute again")
                return False

        return True

    def _record_success(self):
        """Record successful DynaRoute request"""
        self.circuit_breaker.failure_count = 0
        self.circuit_breaker.is_open = False
        self.circuit_breaker.last_failure_time = None

    def _record_failure(self):
        """Record failed DynaRoute request and update circuit breaker"""
        self.circuit_breaker.failure_count += 1
        self.circuit_breaker.last_failure_time = time.time()

        if self.circuit_breaker.failure_count >= self.config.circuit_breaker_threshold:
            self.circuit_breaker.is_open = True
            logger.warning(f"Circuit breaker opened after {self.circuit_breaker.failure_count} failures")

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        service_name: Optional[str] = None,
        operation_name: Optional[str] = None,
        **kwargs
    ):
        """
        Chat completion with DynaRoute primary and OpenAI fallback.

        Maintains the same interface as OpenAI proxy for drop-in replacement.
        """
        logger.info(f"🚀 [DYNAROUTE-SERVICE] Chat completion request started")
        logger.info(f"   👤 User ID: {user_id}")
        logger.info(f"   🏢 Organization: {organization_id}")
        logger.info(f"   🎯 Requested model: {model}")
        logger.info(f"   📝 Messages count: {len(messages)}")
        logger.info(f"   🌡️  Temperature: {temperature}")
        logger.info(f"   📊 Max tokens: {max_tokens}")
        logger.info(f"   🔄 Stream: {stream}")
        logger.info(f"   🔧 Service name: {service_name}")

        self.metrics["total_requests"] += 1
        start_time = time.time()

        # Check DynaRoute availability
        circuit_breaker_open = self._is_circuit_breaker_open()
        logger.info(f"🔍 [DYNAROUTE-SERVICE] Availability check:")
        logger.info(f"   ✅ DynaRoute enabled: {self.config.enabled}")
        logger.info(f"   🔗 DynaRoute client available: {self.dynaroute_client is not None}")
        logger.info(f"   🚫 Circuit breaker open: {circuit_breaker_open}")
        logger.info(f"   📊 Stream requested: {stream}")

        # Try DynaRoute first if enabled and circuit breaker allows
        if (self.config.enabled and
            self.dynaroute_client and
            not circuit_breaker_open and
            not stream):  # DynaRoute doesn't support streaming

            try:
                logger.info(f"🎯 [DYNAROUTE-SERVICE] Using DynaRoute for request")
                response = await self._dynaroute_chat_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    user_id=user_id,
                    service_name=service_name,
                    operation_name=operation_name,
                    **kwargs
                )

                self._record_success()
                self.metrics["dynaroute_requests"] += 1

                # Estimate cost savings (rough estimate)
                duration_ms = (time.time() - start_time) * 1000
                estimated_savings = self._estimate_cost_savings(messages, response)
                self.metrics["cost_savings"] += estimated_savings

                logger.info(f"✅ [DYNAROUTE-SERVICE] DynaRoute request successful:")
                logger.info(f"   ⏱️  Duration: {duration_ms:.2f}ms")
                logger.info(f"   💰 Estimated savings: ${estimated_savings:.4f}")
                logger.info(f"   📈 Total DynaRoute requests: {self.metrics['dynaroute_requests']}")
                return response

            except Exception as e:
                logger.error(f"❌ [DYNAROUTE-SERVICE] DynaRoute failed: {e}")
                logger.info(f"   🔄 Falling back to OpenAI...")
                self._record_failure()
                self.metrics["failures"] += 1
                # Fall through to OpenAI fallback
        else:
            # Log why DynaRoute was skipped
            reasons = []
            if not self.config.enabled:
                reasons.append("DynaRoute disabled")
            if not self.dynaroute_client:
                reasons.append("No DynaRoute client")
            if circuit_breaker_open:
                reasons.append("Circuit breaker open")
            if stream:
                reasons.append("Streaming not supported")

            logger.info(f"⚠️  [DYNAROUTE-SERVICE] Skipping DynaRoute: {', '.join(reasons)}")

        # Fallback to OpenAI
        logger.info(f"🔄 [DYNAROUTE-SERVICE] Using OpenAI fallback")
        logger.info(f"   📊 Total fallback requests: {self.metrics['openai_fallback_requests'] + 1}")
        self.metrics["openai_fallback_requests"] += 1

        response = await self.openai_proxy.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            user_id=user_id,
            organization_id=organization_id,
            service_name=service_name,
            operation_name=operation_name,
            **kwargs
        )

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✅ [DYNAROUTE-SERVICE] OpenAI fallback successful:")
        logger.info(f"   ⏱️  Duration: {duration_ms:.2f}ms")
        logger.info(f"   🏭 Provider used: openai")
        return response

    async def _dynaroute_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
        user_id: Optional[str],
        service_name: Optional[str],
        operation_name: Optional[str],
        **kwargs
    ):
        """
        Make request to DynaRoute and normalize response format.

        DynaRoute returns a different format than OpenAI, so we need to
        normalize it to maintain compatibility with existing code.
        """
        import time

        logger.info(f"🎯 [DYNAROUTE-INTERNAL] Preparing DynaRoute API call")
        start_time = time.time()

        # Prepare DynaRoute request
        dynaroute_request = {
            "messages": messages,
            "stream": False,
            "request_timeout": self.config.timeout
        }

        # Add additional parameters if supported
        if temperature != 0.1:  # Only add if different from default
            dynaroute_request["temperature"] = temperature

        if max_tokens:
            dynaroute_request["max_tokens"] = max_tokens

        logger.info(f"📋 [DYNAROUTE-INTERNAL] Request parameters:")
        logger.info(f"   📝 Messages count: {len(messages)}")
        logger.info(f"   🌡️  Temperature: {temperature}")
        logger.info(f"   📊 Max tokens: {max_tokens}")
        logger.info(f"   ⏱️  Timeout: {self.config.timeout}s")
        logger.info(f"   👤 User ID: {user_id}")
        logger.info(f"   🔧 Service name: {service_name}")

        # Log the messages being sent (truncated for readability)
        for i, msg in enumerate(messages[-3:]):  # Only log last 3 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            logger.info(f"   💬 Message {i+1} ({role}): {content[:100]}{'...' if len(content) > 100 else ''}")

        try:
            # Make DynaRoute request
            logger.info(f"🚀 [DYNAROUTE-INTERNAL] Calling DynaRoute API...")
            response = self.dynaroute_client.chat(**dynaroute_request)

            api_duration = (time.time() - start_time) * 1000
            logger.info(f"✅ [DYNAROUTE-INTERNAL] DynaRoute API call successful:")
            logger.info(f"   ⏱️  API call duration: {api_duration:.2f}ms")
            logger.info(f"   🔍 Response type: {type(response)}")

            # Log response metadata if available
            if hasattr(response, '__dict__'):
                logger.info(f"   📊 Response attributes: {list(response.__dict__.keys())}")

            # Normalize DynaRoute response to OpenAI format
            logger.info(f"🔄 [DYNAROUTE-INTERNAL] Normalizing DynaRoute response to OpenAI format...")
            normalized_response = self._normalize_dynaroute_response(response, model)

            total_duration = (time.time() - start_time) * 1000
            logger.info(f"✅ [DYNAROUTE-INTERNAL] Response normalization complete:")
            logger.info(f"   ⏱️  Total processing time: {total_duration:.2f}ms")

            return normalized_response

        except Exception as e:
            error_duration = (time.time() - start_time) * 1000
            logger.error(f"❌ [DYNAROUTE-INTERNAL] DynaRoute API call failed:")
            logger.error(f"   ⏱️  Time before failure: {error_duration:.2f}ms")
            logger.error(f"   ❗ Error: {str(e)}")
            logger.error(f"   🔧 Error type: {type(e).__name__}")
            raise

    def _normalize_dynaroute_response(self, dynaroute_response: Dict[str, Any], requested_model: str):
        """
        Convert DynaRoute response format to OpenAI-compatible format.

        DynaRoute format:
        {
            "choices": [{"message": {"content": "response"}}],
            "usage": {...},
            "model": "actual_model_used"
        }

        OpenAI format (what existing code expects):
        {
            "id": "...",
            "choices": [{"message": {"content": "...", "role": "assistant"}}],
            "usage": {...},
            "model": "..."
        }
        """
        logger.info(f"🔄 [DYNAROUTE-NORMALIZE] Starting response normalization")
        logger.info(f"   🔍 Raw response type: {type(dynaroute_response)}")
        logger.info(f"   🎯 Requested model: {requested_model}")

        # Log the raw DynaRoute response structure (safely)
        if isinstance(dynaroute_response, dict):
            logger.info(f"   📋 Response keys: {list(dynaroute_response.keys())}")
            if "model" in dynaroute_response:
                logger.info(f"   🎯 Actual model used: {dynaroute_response['model']}")
            if "usage" in dynaroute_response:
                usage = dynaroute_response["usage"]
                logger.info(f"   📊 Token usage: {usage}")

        # Extract response content
        if "choices" in dynaroute_response and dynaroute_response["choices"]:
            content = dynaroute_response["choices"][0]["message"]["content"]
            logger.info(f"   📝 Response content length: {len(content)} chars")
            logger.info(f"   📄 Content preview: {content[:200]}{'...' if len(content) > 200 else ''}")
        else:
            logger.error(f"   ❌ Invalid DynaRoute response format - missing choices")
            raise ValueError("Invalid DynaRoute response format")

        # Check if DynaRoute returned structured JSON response
        parsed_content = None
        try:
            parsed_content = json.loads(content)
            if isinstance(parsed_content, dict) and "response" in parsed_content:
                # DynaRoute returned structured response, extract the actual content
                logger.info(f"   🧩 Structured JSON response detected")
                logger.info(f"   🔑 JSON keys: {list(parsed_content.keys())}")
                actual_content = parsed_content["response"]
                logger.info(f"   ✅ Extracted actual content length: {len(actual_content)} chars")
            else:
                logger.info(f"   📄 JSON response but no 'response' key - using as-is")
                actual_content = content
        except (json.JSONDecodeError, TypeError):
            # Content is not JSON, use as-is
            logger.info(f"   📄 Plain text response - using as-is")
            actual_content = content

        # Create OpenAI-compatible response
        logger.info(f"   🔄 Creating OpenAI-compatible response...")
        normalized_response = {
            "id": f"dynaroute-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": dynaroute_response.get("model", requested_model),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": actual_content
                },
                "finish_reason": "stop"
            }],
            "usage": dynaroute_response.get("usage", {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            })
        }

        # Add metadata if available
        if parsed_content and isinstance(parsed_content, dict):
            metadata = {
                "domain": parsed_content.get("domain"),
                "task_type": parsed_content.get("task_type"),
                "keywords": parsed_content.get("keywords", [])
            }
            normalized_response["dynaroute_metadata"] = metadata
            logger.info(f"   🎯 DynaRoute metadata added: {metadata}")
        else:
            logger.info(f"   ⚠️  No DynaRoute metadata available")

        # Final logging of normalized response
        logger.info(f"✅ [DYNAROUTE-NORMALIZE] Response normalization complete:")
        logger.info(f"   🆔 Response ID: {normalized_response['id']}")
        logger.info(f"   🎯 Final model: {normalized_response['model']}")
        logger.info(f"   📊 Usage tokens: {normalized_response.get('usage', {}).get('total_tokens', 'unknown')}")
        logger.info(f"   📝 Final content length: {len(normalized_response['choices'][0]['message']['content'])} chars")
        logger.info(f"   🎯 Has DynaRoute metadata: {'dynaroute_metadata' in normalized_response}")

        return normalized_response

    def _estimate_cost_savings(
        self,
        messages: List[Dict[str, str]],
        response: Dict[str, Any]
    ) -> float:
        """
        Estimate cost savings from using DynaRoute vs OpenAI.

        This is a rough estimate based on typical pricing differences.
        """
        usage = response.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)

        if total_tokens == 0:
            return 0.0

        # Rough estimate: DynaRoute saves ~70% on average
        # Using rough OpenAI pricing: $0.002 per 1K tokens for gpt-4o-mini
        openai_cost = (total_tokens / 1000) * 0.002
        dynaroute_cost = openai_cost * 0.30  # 30% of OpenAI cost
        savings = openai_cost - dynaroute_cost

        return savings

    async def embedding(
        self,
        input_text: str | List[str],
        model: str = "text-embedding-ada-002",
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        service_name: Optional[str] = None,
        operation_name: Optional[str] = None
    ) -> List[List[float]]:
        """
        Embedding generation - currently only supported by OpenAI.

        DynaRoute doesn't support embeddings yet, so always use OpenAI.
        """
        return await self.openai_proxy.embedding(
            input_text=input_text,
            model=model,
            user_id=user_id,
            organization_id=organization_id,
            service_name=service_name,
            operation_name=operation_name
        )

    async def health_check(self) -> Dict[str, Any]:
        """
        Health check for both DynaRoute and OpenAI services.
        """
        health_status = {
            "dynaroute": {"available": False, "enabled": self.config.enabled},
            "openai": {"available": False},
            "circuit_breaker": {
                "is_open": self.circuit_breaker.is_open,
                "failure_count": self.circuit_breaker.failure_count
            }
        }

        # Test OpenAI (always available as fallback)
        try:
            openai_health = await self.openai_proxy.health_check()
            health_status["openai"] = {
                "available": openai_health["status"] == "healthy",
                **openai_health
            }
        except Exception as e:
            health_status["openai"]["error"] = str(e)

        # Test DynaRoute if enabled
        if self.config.enabled and self.dynaroute_client:
            try:
                # Simple test request to DynaRoute
                test_messages = [{"role": "user", "content": "ping"}]
                response = self.dynaroute_client.chat(
                    messages=test_messages,
                    stream=False,
                    request_timeout=10
                )
                health_status["dynaroute"]["available"] = True
                health_status["dynaroute"]["test_response"] = response["choices"][0]["message"]["content"][:50]
            except Exception as e:
                health_status["dynaroute"]["error"] = str(e)

        # Overall status
        health_status["status"] = "healthy" if health_status["openai"]["available"] else "unhealthy"

        return health_status

    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics and statistics"""
        return {
            **self.metrics,
            "dynaroute_enabled": self.config.enabled,
            "dynaroute_available": DYNAROUTE_AVAILABLE and self.dynaroute_client is not None,
            "circuit_breaker_open": self.circuit_breaker.is_open,
            "circuit_breaker_failures": self.circuit_breaker.failure_count,
            "success_rate": (
                (self.metrics["total_requests"] - self.metrics["failures"]) /
                max(self.metrics["total_requests"], 1)
            ),
            "dynaroute_usage_rate": (
                self.metrics["dynaroute_requests"] /
                max(self.metrics["total_requests"], 1)
            )
        }

    def get_config_info(self) -> Dict[str, Any]:
        """Get current configuration information"""
        return {
            "dynaroute_enabled": self.config.enabled,
            "dynaroute_available": DYNAROUTE_AVAILABLE,
            "api_key_configured": bool(self.config.api_key or os.getenv("DYNAROUTE_API_KEY")),
            "timeout": self.config.timeout,
            "circuit_breaker_threshold": self.config.circuit_breaker_threshold,
            "openai_proxy": self.openai_proxy.get_config_info()
        }

# Global service instance
_global_dynaroute_service: Optional[DynaRouteService] = None

def get_dynaroute_service(config: Optional[DynaRouteConfig] = None) -> DynaRouteService:
    """Get the global DynaRoute service instance"""
    global _global_dynaroute_service
    if _global_dynaroute_service is None:
        _global_dynaroute_service = DynaRouteService(config)
    elif config and config != _global_dynaroute_service.config:
        # Reconfigure if new config provided
        _global_dynaroute_service = DynaRouteService(config)
    return _global_dynaroute_service

def configure_dynaroute(
    enabled: bool = True,
    api_key: Optional[str] = None,
    timeout: int = 30,
    circuit_breaker_threshold: int = 3
) -> DynaRouteService:
    """Configure and get DynaRoute service with specific settings"""
    config = DynaRouteConfig(
        enabled=enabled,
        api_key=api_key,
        timeout=timeout,
        circuit_breaker_threshold=circuit_breaker_threshold
    )
    return get_dynaroute_service(config)
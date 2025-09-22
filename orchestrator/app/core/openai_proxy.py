"""
OpenAI Proxy Wrapper
Provides a unified interface for OpenAI operations with built-in error handling and logging.
"""

import asyncio
import logging
import uuid
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
from openai import AsyncOpenAI
from openai import RateLimitError, APIError, APIConnectionError, APITimeoutError
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from .openai_manager import get_openai_client, get_client_manager

# Phoenix/OpenTelemetry integration
try:
	from opentelemetry import trace
	TRACING_AVAILABLE = True
except ImportError:
	TRACING_AVAILABLE = False

logger = logging.getLogger(__name__)

class OpenAIProxy:
	"""Proxy wrapper for OpenAI client operations."""
	
	def __init__(self):
		self._client_manager = get_client_manager()
	
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
	) -> ChatCompletion | AsyncGenerator[ChatCompletionChunk, None]:
		"""Create a chat completion with automatic retry and error handling."""
		client = self._client_manager.get_client()
		
		# Generate unique request ID for tracking
		request_id = str(uuid.uuid4())
		start_time = time.time()
		
		# Get organization ID for internal tracking
		internal_org_id = organization_id or self._client_manager._organization_id
		service = service_name or "unknown_service"
		operation = operation_name or "chat_completion"
		
		request_params = {
			"model": model,
			"messages": messages,
			"temperature": temperature,
			"stream": stream,
			**kwargs
		}
		
		if max_tokens:
			request_params["max_tokens"] = max_tokens
		
		# Add user ID for OpenAI tracking if provided
		if user_id:
			request_params["user"] = user_id
		
		# Debug logging for parameter forwarding (especially response_format)
		if "response_format" in kwargs:
			logger.info(f"[{request_id}] Using response_format: {kwargs['response_format']}")
		
		# Log all parameters being sent to OpenAI (excluding messages for brevity)
		params_log = {k: v for k, v in request_params.items() if k != "messages"}
		logger.debug(f"[{request_id}] OpenAI request parameters: {params_log}")
		
		# Create a span with service context for proper attribution
		tracer = trace.get_tracer(__name__)
		
		# Start a span with service attribution that will be the parent of the auto-instrumented OpenAI span
		with tracer.start_as_current_span(f"moolai.llm.{operation}") as span:
			# Set service attributes on the parent span
			span.set_attribute("moolai.service_name", service)
			span.set_attribute("moolai.operation_name", operation)
			span.set_attribute("moolai.organization_id", internal_org_id)
			span.set_attribute("moolai.user_id", user_id or "anonymous")
			span.set_attribute("moolai.model", model)
			span.set_attribute("moolai.request_id", request_id)
			
			try:
				logger.info(f"[{request_id}] Chat completion request - service: {service}, operation: {operation}, model: {model}, user: {user_id or 'anonymous'}, org: {internal_org_id}, messages: {len(messages)}")
				
				# The OpenAI call will create a child span that inherits context
				if stream:
					return await client.chat.completions.create(**request_params)
				else:
					response = await client.chat.completions.create(**request_params)
				
				# Calculate metrics
				duration_ms = (time.time() - start_time) * 1000
				tokens_used = response.usage.total_tokens if response.usage else 0
				
				logger.info(f"[{request_id}] Chat completion successful - service: {service}, operation: {operation}, user: {user_id or 'anonymous'}, org: {internal_org_id}, tokens: {tokens_used}, duration: {duration_ms:.2f}ms")
				return response
				
			except RateLimitError as e:
				duration_ms = (time.time() - start_time) * 1000
				logger.warning(f"[{request_id}] Rate limit exceeded - service: {service}, user: {user_id or 'anonymous'}, org: {internal_org_id}, duration: {duration_ms:.2f}ms, Error: {str(e)}")
				raise
			except APIConnectionError as e:
				duration_ms = (time.time() - start_time) * 1000
				logger.error(f"[{request_id}] Connection error - service: {service}, user: {user_id or 'anonymous'}, org: {internal_org_id}, duration: {duration_ms:.2f}ms, Error: {str(e)}")
				raise
			except APITimeoutError as e:
				duration_ms = (time.time() - start_time) * 1000
				logger.error(f"[{request_id}] Timeout error - service: {service}, user: {user_id or 'anonymous'}, org: {internal_org_id}, duration: {duration_ms:.2f}ms, Error: {str(e)}")
				raise
			except APIError as e:
				duration_ms = (time.time() - start_time) * 1000
				logger.error(f"[{request_id}] OpenAI API error - service: {service}, user: {user_id or 'anonymous'}, org: {internal_org_id}, duration: {duration_ms:.2f}ms, Error: {str(e)}")
				
				# Check if it's an API key error and log helpful info
				if "invalid_api_key" in str(e).lower() or "401" in str(e).lower():
					config = self._client_manager.get_current_config()
					logger.error(f"API Key authentication failed. Config: {config}")
				
				# Check if it's a response_format related error and provide specific debugging
				if "response_format" in str(e).lower() or "json_object" in str(e).lower():
					logger.error(f"[{request_id}] Response format error detected. Model: {model}")
					logger.error(f"[{request_id}] Request parameters sent: {params_log}")
					if "response_format" in kwargs:
						logger.error(f"[{request_id}] Response format requested: {kwargs['response_format']}")
						logger.error(f"[{request_id}] Consider using a model that supports JSON mode (gpt-4-1106-preview, gpt-4-0125-preview, gpt-3.5-turbo-1106, or later)")
				
				raise
			except Exception as e:
				duration_ms = (time.time() - start_time) * 1000
				logger.error(f"[{request_id}] Unexpected error - service: {service}, user: {user_id or 'anonymous'}, org: {internal_org_id}, duration: {duration_ms:.2f}ms, Error: {str(e)}")
				raise
	
	async def embedding(
		self,
		input_text: str | List[str],
		model: str = "text-embedding-ada-002",
		user_id: Optional[str] = None,
		organization_id: Optional[str] = None,
		service_name: Optional[str] = None,
		operation_name: Optional[str] = None
	) -> List[List[float]]:
		"""Create embeddings with error handling."""
		client = self._client_manager.get_client()
		
		# Generate unique request ID for tracking
		request_id = str(uuid.uuid4())
		start_time = time.time()
		
		internal_org_id = organization_id or self._client_manager._organization_id
		service = service_name or "unknown_service"
		operation = operation_name or "embedding"
		
		# Create a span with service context for proper attribution
		tracer = trace.get_tracer(__name__)
		
		# Start a span with service attribution that will be the parent of the auto-instrumented OpenAI span
		with tracer.start_as_current_span(f"moolai.embedding.{operation}") as span:
			# Set service attributes on the parent span
			span.set_attribute("moolai.service_name", service)
			span.set_attribute("moolai.operation_name", operation)
			span.set_attribute("moolai.organization_id", internal_org_id)
			span.set_attribute("moolai.user_id", user_id or "anonymous")
			span.set_attribute("moolai.model", model)
			span.set_attribute("moolai.request_id", request_id)
			
			try:
				logger.info(f"[{request_id}] Embeddings request - service: {service}, operation: {operation}, model: {model}, user: {user_id or 'anonymous'}, org: {internal_org_id}")
				
				request_params = {
					"model": model,
					"input": input_text
				}
				
				# Add user ID for OpenAI tracking if provided
				if user_id:
					request_params["user"] = user_id
				
				response = await client.embeddings.create(**request_params)
				
				# Calculate metrics
				duration_ms = (time.time() - start_time) * 1000
				embedding_count = len(response.data)
				
				logger.info(f"[{request_id}] Embeddings successful - service: {service}, operation: {operation}, user: {user_id or 'anonymous'}, org: {internal_org_id}, embeddings: {embedding_count}, duration: {duration_ms:.2f}ms")
				return [data.embedding for data in response.data]
				
			except RateLimitError as e:
				duration_ms = (time.time() - start_time) * 1000
				logger.warning(f"[{request_id}] Rate limit exceeded for embeddings - service: {service}, user: {user_id or 'anonymous'}, org: {internal_org_id}, duration: {duration_ms:.2f}ms, Error: {str(e)}")
				raise
			except APIError as e:
				duration_ms = (time.time() - start_time) * 1000
				logger.error(f"[{request_id}] OpenAI API error for embeddings - service: {service}, user: {user_id or 'anonymous'}, org: {internal_org_id}, duration: {duration_ms:.2f}ms, Error: {str(e)}")
				raise
			except Exception as e:
				duration_ms = (time.time() - start_time) * 1000
				logger.error(f"[{request_id}] Unexpected error in embeddings - service: {service}, user: {user_id or 'anonymous'}, org: {internal_org_id}, duration: {duration_ms:.2f}ms, Error: {str(e)}")
				raise
	
	async def health_check(self) -> Dict[str, Any]:
		"""Perform a health check by making a simple API call."""
		try:
			response = await self.chat_completion(
				messages=[{"role": "user", "content": "ping"}],
				model="gpt-4o-mini",
				max_tokens=1
			)
			
			config = self._client_manager.get_current_config()
			return {
				"status": "healthy",
				"api_key_suffix": config["api_key_suffix"],
				"response_id": response.id if hasattr(response, 'id') else None
			}
			
		except Exception as e:
			config = self._client_manager.get_current_config()
			return {
				"status": "unhealthy",
				"error": str(e),
				"api_key_suffix": config["api_key_suffix"]
			}
	
	def get_config_info(self) -> Dict[str, Any]:
		"""Get current configuration information."""
		return self._client_manager.get_current_config()


# Global proxy instance
_global_proxy: Optional[OpenAIProxy] = None

def get_openai_proxy() -> OpenAIProxy:
	"""Get the global OpenAI proxy instance."""
	global _global_proxy
	if _global_proxy is None:
		_global_proxy = OpenAIProxy()
	return _global_proxy
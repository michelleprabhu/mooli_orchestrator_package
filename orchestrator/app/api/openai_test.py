"""
Test endpoint for the global OpenAI client system
"""

from fastapi import APIRouter, HTTPException, Depends
from ..core.openai_proxy import get_openai_proxy, OpenAIProxy
from ..core.openai_manager import get_client_manager
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(prefix="/openai-test", tags=["OpenAI Test"])

class HealthCheckResponse(BaseModel):
	status: str
	api_key_suffix: str
	client_config: Dict[str, Any]
	test_response: Dict[str, Any] = None

@router.get("/health", response_model=HealthCheckResponse)
async def health_check(proxy: OpenAIProxy = Depends(get_openai_proxy)):
	"""Test the global OpenAI client health."""
	try:
		# Get current configuration
		manager = get_client_manager()
		config = manager.get_current_config()
		
		# Perform health check
		health_result = await proxy.health_check()
		
		return HealthCheckResponse(
			status=health_result["status"],
			api_key_suffix=config["api_key_suffix"],
			client_config=config,
			test_response=health_result
		)
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@router.get("/config")
async def get_config():
	"""Get current OpenAI client configuration."""
	try:
		manager = get_client_manager()
		return manager.get_current_config()
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")

class TestPromptRequest(BaseModel):
	message: str = "Hello, this is a test message"

@router.post("/test-prompt")
async def test_prompt(request: TestPromptRequest, proxy: OpenAIProxy = Depends(get_openai_proxy)):
	"""Test a simple prompt with the global client."""
	try:
		response = await proxy.chat_completion(
			messages=[{"role": "user", "content": request.message}],
			model="gpt-4o-mini",
			max_tokens=50
		)
		
		return {
			"success": True,
			"response": response.choices[0].message.content,
			"model": response.model,
			"tokens": response.usage.total_tokens if response.usage else 0
		}
	except Exception as e:
		raise HTTPException(status_code=500, detail=f"Test prompt failed: {str(e)}")
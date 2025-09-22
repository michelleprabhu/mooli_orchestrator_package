"""FastAPI dependency providers for orchestrator services."""

from fastapi import Request
from ..core.openai_proxy import get_openai_proxy
from ..core.openai_manager import get_openai_client


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
"""Orchestrator agents package."""

import os
import sys
from datetime import datetime
from typing import Optional

# Store the original import
_generate_llm_response = None
_QueryRequest = None
_QueryResponse = None

# Add path to main_response.py and import
current_dir = os.path.dirname(os.path.abspath(__file__))
main_response_path = os.path.join(current_dir, 'Prompt Response')
sys.path.insert(0, main_response_path)

try:
    from main_response import generate_llm_response as _generate_llm_response_import
    from main_response import QueryRequest as _QueryRequest_import
    from main_response import QueryResponse as _QueryResponse_import
    
    # Store references to the imported functions/classes
    _generate_llm_response = _generate_llm_response_import
    _QueryRequest = _QueryRequest_import
    _QueryResponse = _QueryResponse_import
    
    # Make them available at module level
    generate_llm_response = _generate_llm_response
    QueryRequest = _QueryRequest
    QueryResponse = _QueryResponse
finally:
    if main_response_path in sys.path:
        sys.path.remove(main_response_path)

class PromptResponseAgent:
    def __init__(self, openai_api_key=None, organization_id="default", openai_client=None):
        self.openai_api_key = openai_api_key
        self.organization_id = organization_id
        self.openai_client = openai_client

    async def process_prompt(self, request, db_session=None):
        """Process prompt using the main_response.py implementation"""
        try:
            # Get model from request or use None to fall back to environment variable default
            model = getattr(request, 'model', None)
            
            # Use the stored reference to generate_llm_response
            if _generate_llm_response is None:
                raise Exception("generate_llm_response function not available")
            
            # Call the main_response function with model parameter
            result = await _generate_llm_response(request.query, request.session_id, model=model)
            
            # Return a response object compatible with the API
            class AgentResponse:
                def __init__(self, result, model):
                    self.prompt_id = f"prompt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    # Try both 'response' and 'answer' keys for compatibility
                    self.response = result.get("response", result.get("answer", ""))
                    # Use the model from result if available (for actual model used), otherwise use passed model
                    self.model = result.get("model", result.get("user_response_model", model or "gpt-4o"))
                    self.total_tokens = result.get("tokens_used", 0)
                    self.cost = result.get("cost", 0.0)
                    self.latency_ms = result.get("latency_ms", 0)
                    self.timestamp = datetime.now()
                    # Add cache information
                    self.from_cache = result.get("from_cache", False)
                    self.cache_similarity = result.get("similarity", None)
                    # Include message_id for feedback submission
                    self.message_id = result.get("message_id", None)
            
            return AgentResponse(result, model)
            
        except Exception as e:
            import traceback
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Agent processing failed: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise Exception(f"Agent processing failed: {str(e)}")

class PromptResponseService:
    def __init__(self, organization_id="default"):
        self.organization_id = organization_id
        self.agent = PromptResponseAgent(organization_id=organization_id)

__all__ = ["PromptResponseAgent", "PromptResponseService", "generate_llm_response", "QueryRequest", "QueryResponse"]

# Ensure the imported items are available for export
if _generate_llm_response:
    generate_llm_response = _generate_llm_response
if _QueryRequest:
    QueryRequest = _QueryRequest
if _QueryResponse:
    QueryResponse = _QueryResponse
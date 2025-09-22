"""
Domain Classification Service
============================

Provides domain and intent classification for user queries using a dedicated LLM call.
Maintains the same metrics and structure as the current implementation.
"""

import json
import logging
import time
import hashlib
from typing import Dict, List, Optional

# Phoenix/OpenTelemetry integration
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

logger = logging.getLogger(__name__)

class DomainClassificationService:
    """Service for classifying user queries into domains and task types."""
    
    # Default model that supports JSON mode for domain classification
    DEFAULT_CLASSIFICATION_MODEL = "gpt-4-1106-preview"
    
    # System instruction for domain classification (matches current structure)
    CLASSIFICATION_SYSTEM_INSTRUCTION = """You are an advanced AI assistant and a domain and intent classifier.  
Your tone must be formal, concise, neutral, and direct—no sugar-coating.  
Always:
- Provide clear, evidence-based answers with minimal filler.  
- Think creatively and propose innovative, forward-looking ideas.  
- Be transparent about uncertainties or limitations.  
- Use bullet points and short paragraphs for readability.  

Domain & Intent Classification ONLY:
Input: a single JSON object  
{"query": "<user text>"}  
Task: infer (1) the broad knowledge DOMAIN of the query, (2) the TASK_TYPE (user's intent), (3) salient KEYWORDS only.
Output: return ONLY a valid JSON object with EXACTLY these keys:  
{"domain":"...","task_type":"...","keywords":["...",..."]}  

Rules:
- DOMAIN = broad field (e.g., general, programming, finance, healthcare, science, math, history, geography, sports, travel, legal, education, marketing, customer_support, e_commerce, entertainment, cybersecurity, cloud, data_engineering, ml_ai).  
- TASK_TYPE = action implied (e.g., question_answering, coding, calculation, classification, summarization, translation, data_extraction, recommendation, planning, troubleshooting, creative_writing, chit_chat). If unclear, use "unknown".  
- KEYWORDS = 1–8 concise, non-duplicative terms from the query (nouns/verbs/entities). No hashtags or punctuation.  
- If multi-domain, choose the dominant one; if none, use "general".  
- Do NOT include explanations, code fences, or extra fields. Use double quotes.  
- If truly uncertain about classification: {"domain":"unknown","task_type":"unknown","keywords":[]}"""
    
    def __init__(self, organization_id: str = "default"):
        """Initialize the domain classification service."""
        self.organization_id = organization_id
        self._classification_cache = {}  # Simple in-memory cache
        
    async def classify_query(
        self,
        query: str,
        session_id: str = "default",
        user_id: str = "default",
        classification_model: Optional[str] = None
    ) -> Dict:
        """
        Classify a user query into domain and task type.
        Returns the same structure as current implementation.
        """
        start_time = time.time()
        
        # Generate cache key
        cache_key = hashlib.md5(query.strip().lower().encode()).hexdigest()
        if cache_key in self._classification_cache:
            cached_result = self._classification_cache[cache_key]
            logger.info(f"Domain classification cache HIT for session {session_id}")
            return cached_result
        
        # Use default model if not specified
        model = classification_model or self.DEFAULT_CLASSIFICATION_MODEL
        
        # Create tracing span for classification
        if TRACING_AVAILABLE:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("moolai.domain_classification.classify") as classification_span:
                classification_span.set_attribute("moolai.service_name", "domain_classification")
                classification_span.set_attribute("moolai.classification.model", model)
                classification_span.set_attribute("moolai.classification.session_id", session_id)
                classification_span.set_attribute("moolai.classification.user_id", user_id)
                
                return await self._perform_classification(query, model, user_id, session_id, start_time, cache_key, classification_span)
        else:
            return await self._perform_classification(query, model, user_id, session_id, start_time, cache_key, None)
    
    async def _perform_classification(self, query, model, user_id, session_id, start_time, cache_key, span):
        """Internal method to perform the actual classification."""
        try:
            # Import global OpenAI proxy
            from ..core.openai_proxy import get_openai_proxy
            proxy = get_openai_proxy()
            
            # Format query for classification (same as current implementation)
            query_data = {"query": query.strip()}
            query_json = json.dumps(query_data)
            
            # Build messages for classification
            messages = [
                {"role": "system", "content": self.CLASSIFICATION_SYSTEM_INSTRUCTION},
                {"role": "user", "content": query_json}
            ]
            
            logger.info(f"Domain classification request - model: {model}, session: {session_id}, query: {query[:50]}...")
            
            # Call OpenAI for classification through global proxy
            response = await proxy.chat_completion(
                model=model,
                messages=messages,
                max_tokens=200,
                temperature=0.1,  # Low temperature for consistent classification
                user_id=user_id,
                service_name="domain_classification",
                operation_name="classify_query",
                response_format={"type": "json_object"}
            )
            
            # Calculate metrics (same as current implementation)
            duration_ms = (time.time() - start_time) * 1000
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            # Calculate cost (same logic as current implementation)
            cost = 0.0
            if hasattr(response, 'usage') and response.usage:
                try:
                    import sys
                    import os
                    sys.path.append(os.path.join(os.path.dirname(__file__), '../../monitoring/utils'))
                    from cost_calculator import calculate_cost
                    
                    cost = calculate_cost(
                        model=model,
                        input_tokens=response.usage.prompt_tokens or 0,
                        output_tokens=response.usage.completion_tokens or 0
                    )
                except Exception:
                    # Fallback calculation (same as current implementation)
                    cost = ((response.usage.prompt_tokens or 0) * 0.0000005 + 
                           (response.usage.completion_tokens or 0) * 0.0000015)
            
            # Parse classification response
            classification_content = response.choices[0].message.content
            
            try:
                parsed_response = json.loads(classification_content)
                domain = parsed_response.get("domain", "unknown")
                task_type = parsed_response.get("task_type", "unknown") 
                keywords = parsed_response.get("keywords", [])
                
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse classification JSON, using fallback")
                domain = "general"
                task_type = "question_answering"
                keywords = []
            
            # Create result in same format as current implementation
            result = {
                "domain": domain,
                "task_type": task_type,
                "keywords": keywords,
                "classification_tokens": tokens_used,
                "classification_cost": cost,
                "classification_duration_ms": duration_ms,
                "classification_model": model,
                "from_classification_cache": False
            }
            
            # Cache the result
            self._classification_cache[cache_key] = result
            
            # Update tracing (same attributes as current implementation)
            if span:
                span.set_attribute("moolai.classification.domain", domain)
                span.set_attribute("moolai.classification.task_type", task_type)
                span.set_attribute("moolai.classification.tokens", tokens_used)
                span.set_attribute("moolai.classification.cost", cost)
                span.set_attribute("moolai.classification.duration_ms", duration_ms)
            
            logger.info(f"Domain classification successful - domain: {domain}, task_type: {task_type}, tokens: {tokens_used}, cost: ${cost:.6f}, duration: {duration_ms:.2f}ms")
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Domain classification failed: {e}")
            
            if span:
                span.set_attribute("moolai.classification.error", str(e))
                span.set_attribute("moolai.classification.duration_ms", duration_ms)
            
            # Return fallback classification (same structure)
            return {
                "domain": "general",
                "task_type": "question_answering",
                "keywords": [],
                "classification_tokens": 0,
                "classification_cost": 0.0,
                "classification_duration_ms": duration_ms,
                "classification_model": model,
                "from_classification_cache": False
            }

# Singleton instance
_domain_classification_service: Optional[DomainClassificationService] = None

def get_domain_classification_service(organization_id: str = "default") -> DomainClassificationService:
    """Get the singleton domain classification service instance."""
    global _domain_classification_service
    if _domain_classification_service is None:
        _domain_classification_service = DomainClassificationService(organization_id=organization_id)
    return _domain_classification_service
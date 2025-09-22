from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
# Phoenix/OpenTelemetry observability - OpenAI client is auto-instrumented
from openai import AsyncOpenAI
try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
import os
from dotenv import load_dotenv
import asyncio
from typing import Optional
import httpx
import logging
import time
import json
import hashlib
import numpy as np
from urllib.parse import urlparse
from datetime import datetime, timezone

# Configure logging first  
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import enhanced services with fallback for different execution contexts
try:
    # Try relative imports first (when run as package module)
    from ...services.firewall_service import get_firewall_service
    from ...services.enhanced_cache_service import get_cache_service
    from ...services.chat_service import get_chat_service
    from ...services.domain_classification_service import get_domain_classification_service
    from ...services.model_routing_service import get_model_routing_service, CallType
except ImportError:
    # Fallback to absolute imports (when run directly or in different context)
    try:
        from app.services.firewall_service import get_firewall_service
        from app.services.enhanced_cache_service import get_cache_service
        from app.services.chat_service import get_chat_service
        from app.services.domain_classification_service import get_domain_classification_service
        from app.services.model_routing_service import get_model_routing_service, CallType
    except ImportError:
        # Last resort - add path and import
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(os.path.dirname(current_dir))
        root_dir = os.path.dirname(app_dir)
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)
        from app.services.firewall_service import get_firewall_service
        from app.services.enhanced_cache_service import get_cache_service
        from app.services.chat_service import get_chat_service
        from app.services.domain_classification_service import get_domain_classification_service
        from app.services.model_routing_service import get_model_routing_service, CallType
        
logger.info("Enhanced firewall, cache, chat, domain classification, and model routing services imported successfully")

try:
    # Try relative imports first (when run as package module)  
    from ...services.Evaluation.answer_correctness import evaluate_answer_correctness
    from ...services.Evaluation.answer_relevance import evaluate_answer_relevance  
    from ...services.Evaluation.goal_accuracy import evaluate_goal_accuracy
    from ...services.Evaluation.hallucination import evaluate_hallucination
    from ...services.Evaluation.summarization import evaluate_summarization
    from ...services.Evaluation.human_vs_ai import evaluate_human_vs_ai
    logger.info("Evaluation services imported successfully")
except ImportError:
    try:
        # Fallback to absolute imports
        from app.services.Evaluation.answer_correctness import evaluate_answer_correctness
        from app.services.Evaluation.answer_relevance import evaluate_answer_relevance  
        from app.services.Evaluation.goal_accuracy import evaluate_goal_accuracy
        from app.services.Evaluation.hallucination import evaluate_hallucination
        from app.services.Evaluation.summarization import evaluate_summarization
        from app.services.Evaluation.human_vs_ai import evaluate_human_vs_ai
        logger.info("Evaluation services imported successfully (fallback)")
    except ImportError as e:
        logger.warning(f"Could not import evaluation services: {e}")
        # Create placeholder functions to avoid runtime errors
        async def evaluate_answer_correctness(query: str, answer: str, user_id: str = None, session_id: str = None) -> dict:
            return {"score": 0.0, "explanation": "Evaluation service unavailable"}
        async def evaluate_answer_relevance(query: str, answer: str, user_id: str = None, session_id: str = None) -> dict:
            return {"score": 0.0, "explanation": "Evaluation service unavailable"}
        async def evaluate_goal_accuracy(query: str, answer: str, user_id: str = None, session_id: str = None) -> dict:
            return {"score": 0.0, "explanation": "Evaluation service unavailable"}
        async def evaluate_hallucination(query: str, answer: str, user_id: str = None, session_id: str = None) -> dict:
            return {"score": 0.0, "explanation": "Evaluation service unavailable"}
        async def evaluate_summarization(query: str, answer: str, user_id: str = None, session_id: str = None) -> dict:
            return {"score": 0.0, "explanation": "Evaluation service unavailable"}
        async def evaluate_human_vs_ai(query: str, answer: str, user_id: str = None, session_id: str = None) -> dict:
            return {"score": 0.0, "explanation": "Evaluation service unavailable"}

# Import monitoring middleware - conditional to avoid import issues
monitoring_middleware = None
LLMMonitoringMiddleware = None
try:
    # Try relative import first
    from ...monitoring.middleware.monitoring import LLMMonitoringMiddleware
    logger.info("Successfully imported LLMMonitoringMiddleware")
except ImportError:
    try:
        # Fallback to absolute import
        from app.monitoring.middleware.monitoring import LLMMonitoringMiddleware
        logger.info("Successfully imported LLMMonitoringMiddleware (fallback)")
    except ImportError as e:
        logger.warning(f"Could not import monitoring middleware: {e}")
        LLMMonitoringMiddleware = None

# Load environment variables
load_dotenv()

# Organization configuration
organization_id = os.getenv("ORGANIZATION_ID", "org_001")

# Use global OpenAI client instead of module-level initialization
try:
    # Try importing with enhanced path resolution  
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(os.path.dirname(current_dir))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from core.openai_manager import get_openai_client
    client = get_openai_client()
except ImportError:
    # Fallback for backward compatibility
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    client = AsyncOpenAI(api_key=openai_api_key)

# Model configuration
DEFAULT_USER_RESPONSE_MODEL = os.getenv("DEFAULT_USER_RESPONSE_MODEL", "gpt-4o")

# Cache service configuration
ENABLE_CACHING = os.getenv("ENABLE_CACHING", "true").lower() == "true"
LLM_CACHE_REDIS_URL = os.getenv("REDIS_LLM_CACHE_URL", "redis://redis:6379/1")

# Firewall service configuration
ENABLE_FIREWALL = os.getenv("ENABLE_FIREWALL", "true").lower() == "true"

# Initialize enhanced services as singletons for better performance
_cache_service_instance = None
_firewall_service_instance = None

async def get_cache_service_instance():
    """Get singleton cache service instance."""
    global _cache_service_instance
    if _cache_service_instance is None:
        _cache_service_instance = get_cache_service()
    return _cache_service_instance

async def get_firewall_service_instance():
    """Get singleton firewall service instance."""
    global _firewall_service_instance
    if _firewall_service_instance is None:
        _firewall_service_instance = get_firewall_service()
    return _firewall_service_instance

# Initialize monitoring middleware
monitoring_middleware = None
MonitoringSessionLocal = None

if LLMMonitoringMiddleware is not None:
    try:
        # Import dependencies for monitoring
        import redis.asyncio as redis_async
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker
        
        # Get monitoring database URL
        monitoring_db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://orchestrator_user:orchestrator_pass@postgres-orchestrator:5432/orchestrator_org_001")
        organization_id = os.getenv("ORGANIZATION_ID", "org_001")
        redis_monitoring_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        
        # Create async engine for monitoring database
        monitoring_engine = create_async_engine(monitoring_db_url, echo=False)
        MonitoringSessionLocal = sessionmaker(
            monitoring_engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Create Redis client for monitoring
        parsed_redis_url = urlparse(redis_monitoring_url)
        redis_monitoring_client = redis_async.Redis(
            host=parsed_redis_url.hostname or "localhost",
            port=parsed_redis_url.port or 6379,
            db=int(parsed_redis_url.path.lstrip('/')) if parsed_redis_url.path else 0,
            decode_responses=False
        )
        
        # Initialize monitoring middleware
        monitoring_middleware = LLMMonitoringMiddleware(
            redis_client=redis_monitoring_client,
            db_session=None,  # Will be set per request
            organization_id=organization_id
        )
        
        logger.info("Monitoring middleware initialized successfully")
        
    except Exception as e:
        logger.warning(f"Failed to initialize monitoring middleware: {e}")
        monitoring_middleware = None
        MonitoringSessionLocal = None

# Pydantic models
class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = "default"
    model: Optional[str] = None  # Model will be determined by routing service

# Enhanced response models (from orchestrator 2)
class LLMEvaluationScores(BaseModel):
    answer_correctness: float
    answer_relevance: float
    hallucination: float
    human_likeness: Optional[float] = None

class FirewallViolation(BaseModel):
    violation_type: str
    severity: Optional[str] = None
    findings: list = []
    redacted_content: Optional[str] = None

class FirewallScanSummary(BaseModel):
    scans_performed: list
    violations_found: list
    safe_to_process: bool
    text_length: int
    redacted_text: Optional[str] = None

class QueryResponse(BaseModel):
    domain: str
    task_type: str
    keywords: list
    response: str
    session_id: str
    from_cache: bool = False
    similarity: Optional[float] = None
    firewall_scan: Optional[FirewallScanSummary] = None
    violations: list = []
    content_filtered: bool = False
    evaluation_scores: Optional[LLMEvaluationScores] = None
    is_evaluable: bool = True

class CacheConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    ttl: Optional[int] = None
    similarity_threshold: Optional[float] = None

# Initialize FastAPI app
app = FastAPI(
    title="LLM Response API",
    description="A minimal FastAPI app that returns LLM responses for user queries",
    version="1.0.0"
)

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enhanced system instruction with domain classification (from orchestrator 2)
SYSTEM_INSTRUCTION = """You are an advanced AI assistant and a domain and intent classifier.  
Your tone must be formal, concise, neutral, and direct—no sugar-coating.  
Always:
- Provide clear, evidence-based answers with minimal filler.  
- Think creatively and propose innovative, forward-looking ideas.  
- Be transparent about uncertainties or limitations.  
- Use bullet points and short paragraphs for readability.  

Domain & Intent Classification + Response:
Input: a single JSON object  
{"query": "<user text>"}  
Task: infer (1) the broad knowledge DOMAIN of the query, (2) the TASK_TYPE (user's intent), (3) salient KEYWORDS, and (4) craft the assistant's RESPONSE.  
Output: return ONLY a valid JSON object with EXACTLY these keys:  
{"domain":"...","task_type":"...","keywords":["...",...],"response":"..."}  

Rules:
- DOMAIN = broad field (e.g., general, programming, finance, healthcare, science, math, history, geography, sports, travel, legal, education, marketing, customer_support, e_commerce, entertainment, cybersecurity, cloud, data_engineering, ml_ai).  
- TASK_TYPE = action implied (e.g., question_answering, coding, calculation, classification, summarization, translation, data_extraction, recommendation, planning, troubleshooting, creative_writing, chit_chat). If unclear, use "unknown".  
- KEYWORDS = 1–8 concise, non-duplicative terms from the query (nouns/verbs/entities). No hashtags or punctuation.  
- RESPONSE = your concise, direct answer to the user's query, in full sentences, without extra JSON or markup.  
- If multi-domain, choose the dominant one; if none, use "general".  
- Do NOT include explanations, code fences, or extra fields. Use double quotes.  
- If truly uncertain about classification: {"domain":"unknown","task_type":"unknown","keywords":[],"response":"<your answer here>"}"""

# LLM Cache integration - use enhanced service if available
async def get_cached_response(query: str, session_id: str = "default") -> Optional[dict]:
    """Get response from enhanced cache service using singleton instance"""
    if not ENABLE_CACHING:
        return None
    
    try:
        cache_service = await get_cache_service_instance()
        cached_result = await cache_service.get_cached_response(
            session_id=session_id,
            prompt=query,
            user_id="agent",
            organization_id=organization_id
        )
        if cached_result:
            logger.info(f"Enhanced cache hit: type={cached_result.get('cache_hit_type')} similarity={cached_result.get('similarity_score', 0):.3f}")
            return {
                "response": cached_result.get("response"),
                "from_cache": True,
                "similarity": cached_result.get("similarity_score", 1.0),
                "session_id": session_id,
                "cache_hit_type": cached_result.get("cache_hit_type", "unknown")
            }
        return None
    except Exception as e:
        logger.error(f"Enhanced cache service error: {e}")
        return None

async def store_cached_response(query: str, response: str, session_id: str = "default", ttl: int = 3600):
    """Store response in enhanced cache service with semantic indexing using singleton instance"""
    if not ENABLE_CACHING:
        return
    
    try:
        cache_service = await get_cache_service_instance()
        success = await cache_service.store_response(
            session_id=session_id,
            prompt=query,
            response=response,
            user_id="agent",
            organization_id=organization_id,
            metadata={"ttl": ttl, "source": "agent"}
        )
        if success:
            logger.info(f"Stored in enhanced cache with semantic indexing")
    except Exception as e:
        logger.error(f"Enhanced cache store error: {e}")

async def firewall_scan(text: str, request_span=None, domain: Optional[str] = None, task_type: Optional[str] = None) -> dict:
    """
    Enhanced firewall scanning with Phoenix tracing using Presidio-based service.
    Now includes domain-aware blocking for context-specific security rules.

    Args:
        text: Content to scan
        request_span: Optional tracing span
        domain: Domain classification for context-aware rules (e.g., "healthcare", "finance")
        task_type: Task type classification (e.g., "question_answering", "coding")

    Returns:
        Dict with comprehensive scan results including domain-aware blocking
    """
    if not ENABLE_FIREWALL:
        result = {"pii": {"contains_pii": False}, "secrets": {"contains_secrets": False}, "toxicity": {"contains_toxicity": False}}
        
        # Set firewall disabled attributes
        if TRACING_AVAILABLE and request_span:
            request_span.set_attribute("moolai.firewall.enabled", False)
            request_span.set_attribute("moolai.firewall.blocked", False)
        
        return result
    
    try:
        logger.info(f"Getting firewall service instance (domain: {domain}, task_type: {task_type})...")
        firewall_service = await get_firewall_service_instance()
        logger.info("Firewall service instance obtained, starting comprehensive scan with domain context...")
        # Use comprehensive scan with Presidio and domain awareness
        scan_result = await firewall_service.scan_comprehensive(
            text=text,
            user_id="agent",
            organization_id=organization_id,
            domain=domain,
            task_type=task_type
        )
        logger.info("Comprehensive scan completed successfully")
        logger.info(f"Raw firewall scan_result: {scan_result}")
        
        # Set tracing attributes if available
        if TRACING_AVAILABLE and request_span:
            request_span.set_attribute("moolai.firewall.enabled", True)
            request_span.set_attribute("moolai.firewall.enhanced", True)
            request_span.set_attribute("moolai.firewall.blocked", not scan_result.get("safe_to_process", True))
            request_span.set_attribute("moolai.firewall.violations", len(scan_result.get("violations", [])))
        
        # Convert to expected format by mapping contains_violation to expected keys
        pii_scan = scan_result.get("pii_scan", {"contains_violation": False})
        secrets_scan = scan_result.get("secrets_scan", {"contains_violation": False})
        toxicity_scan = scan_result.get("toxicity_scan", {"contains_violation": False})
        
        converted_result = {
            "pii": {"contains_pii": pii_scan.get("contains_violation", False)},
            "secrets": {"contains_secrets": secrets_scan.get("contains_violation", False)},
            "toxicity": {"contains_toxicity": toxicity_scan.get("contains_violation", False)},
            "enhanced": True,
            "safe_to_process": scan_result.get("safe_to_process", True),
            "redacted_text": scan_result.get("redacted_text", text),
            "domain": domain,
            "task_type": task_type,
            "domain_rule_applied": scan_result.get("allowlist_scan", {}).get("domain_rule", False)
        }
        logger.info(f"Converted firewall result: {converted_result}")
        return converted_result
    except Exception as e:
        import traceback
        logger.error(f"Enhanced firewall service error: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Firewall error: {str(e)}")

async def generate_llm_response(query: str, session_id: str = "default", user_id: str = "default_user", model: str = None) -> dict:
    """Generate LLM response with enhanced Phoenix OpenTelemetry observability and comprehensive tracing"""
    
    # Use default model if none specified
    if model is None:
        model = DEFAULT_USER_RESPONSE_MODEL
    
    # Create root span with vendor-prefixed attributes for comprehensive request tracing
    tracer = None
    if TRACING_AVAILABLE:
        try:
            tracer = trace.get_tracer(__name__)
        except Exception:
            tracer = None
    
    # Start comprehensive request span with vendor-prefixed attributes
    if tracer:
        with tracer.start_as_current_span("moolai.request.process") as request_span:
            # Set request-level attributes using vendor prefix - THIS IS NOW THE TRUE PARENT SPAN
            request_span.set_attribute("moolai.service_name", "main_response")  # KEY: Service attribution at parent level
            request_span.set_attribute("moolai.user_facing", True)  # Mark as user-facing for analytics filtering
            request_span.set_attribute("moolai.session_id", session_id)
            request_span.set_attribute("moolai.user_id", user_id)
            request_span.set_attribute("moolai.query.length", len(query))
            request_span.set_attribute("moolai.query.hash", hashlib.md5(query.encode()).hexdigest()[:8])
            request_span.set_attribute("moolai.model", model)  # Add model info to parent span
            
            return await _generate_llm_response_internal(query, session_id, user_id, model, request_span)
    else:
        return await _generate_llm_response_internal(query, session_id, user_id, model, None)

async def _generate_llm_response_internal(query: str, session_id: str, user_id: str, model: str, request_span) -> dict:
    """Internal LLM response generation with Phoenix tracing context"""
    
    # Extract organization_id - needed for various services
    # Use global organization_id from module level
    global organization_id
    if 'organization_id' not in globals():
        organization_id = os.getenv("ORGANIZATION_ID", "org_001")

    # Step 1: Domain Classification FIRST (needed for domain-aware firewall rules)
    logger.info(f"Starting domain classification for query: {query[:50]}...")
    domain = None
    task_type = None
    try:
        domain_service = get_domain_classification_service(organization_id)
        classification_result = await domain_service.classify_query(
            query=query,
            session_id=session_id,
            user_id=user_id
        )

        # Extract domain classification results for firewall context
        domain = classification_result["domain"]
        task_type = classification_result["task_type"]
        keywords = classification_result["keywords"]
        classification_tokens = classification_result["classification_tokens"]
        classification_cost = classification_result["classification_cost"]

        logger.info(f"Domain classified as: {domain}, task_type: {task_type}")
    except Exception as e:
        logger.warning(f"Domain classification failed, using defaults: {e}")
        domain = "general"
        task_type = "question_answering"
        keywords = []
        classification_tokens = 0
        classification_cost = 0.0

    # Step 2: Firewall scanning with domain context - NOW with domain awareness
    firewall_scan_result = None  # Initialize firewall scan result
    logger.info(f"Firewall check starting - ENABLE_FIREWALL={ENABLE_FIREWALL}, domain={domain}")
    if ENABLE_FIREWALL:
        logger.info(f"Running domain-aware firewall scan on query: {query[:50]}...")
        if TRACING_AVAILABLE:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("moolai.firewall.scan") as firewall_span:
                scan_result = await firewall_scan(query.strip(), request_span, domain=domain, task_type=task_type)
        else:
            scan_result = await firewall_scan(query.strip(), request_span, domain=domain, task_type=task_type)
        
        logger.info(f"Firewall scan results: PII={scan_result['pii']['contains_pii']}, Secrets={scan_result['secrets']['contains_secrets']}, Toxicity={scan_result['toxicity']['contains_toxicity']}, Safe={scan_result.get('safe_to_process', True)}")
        
        # Check if content should be blocked - use comprehensive safe_to_process flag
        should_block = (scan_result["pii"]["contains_pii"] or
                       scan_result["secrets"]["contains_secrets"] or
                       scan_result["toxicity"]["contains_toxicity"] or
                       not scan_result.get("safe_to_process", True))

        if should_block:
            # Log the blocked request
            logger.warning(f"FIREWALL BLOCKING REQUEST - PII: {scan_result['pii']['contains_pii']}, Secrets: {scan_result['secrets']['contains_secrets']}, Toxicity: {scan_result['toxicity']['contains_toxicity']}, Safe: {scan_result.get('safe_to_process', True)}")
            
            # Create firewall scan summary for blocked content
            violations_found = []
            if scan_result["pii"]["contains_pii"]:
                violations_found.append("pii_detected")
            if scan_result["secrets"]["contains_secrets"]:
                violations_found.append("secrets_detected")
            if scan_result["toxicity"]["contains_toxicity"]:
                violations_found.append("toxicity_detected")
            if not scan_result.get("safe_to_process", True):
                violations_found.append("blocklist_violation")
            
            firewall_scan_result = FirewallScanSummary(
                scans_performed=["pii", "secrets", "toxicity", "blocklist"],
                violations_found=violations_found,
                safe_to_process=False,
                text_length=len(query)
            )
            
            violations = [
                FirewallViolation(
                    violation_type=violation_type,
                    findings=[{"blocked": True, "reason": f"{violation_type} detected"}]
                ) for violation_type in violations_found
            ]
            
            # Store blocked prompts in database for analytics and dashboard visibility
            blocked_message_id = None
            try:
                chat_service = get_chat_service()
                
                # Store user message for blocked prompt
                user_metadata = {
                    "model": model,
                    "processing_time_ms": 0,  # No processing for blocked content
                    "firewall_blocked": True,
                    "violations": [v.violation_type for v in violations]
                }
                user_message = await chat_service.store_message(
                    session_id=session_id,
                    role="user",
                    content=query,
                    user_id=user_id,
                    metadata=user_metadata
                )
                
                # Store assistant blocked response
                blocked_response = "Your request was blocked by our security firewall due to sensitive content detection. Please rephrase your request without sensitive information."
                assistant_metadata = {
                    "model": model,
                    "tokens": 0,  # No tokens for blocked response
                    "processing_time_ms": 0,
                    "domain": "security",
                    "task_type": "content_filtering",
                    "keywords": ["blocked", "firewall", "violation"],
                    "firewall_blocked": True,
                    "violations": [v.violation_type for v in violations]
                }
                assistant_message = await chat_service.store_message(
                    session_id=session_id,
                    role="assistant", 
                    content=blocked_response,
                    user_id=user_id,
                    metadata=assistant_metadata
                )
                blocked_message_id = assistant_message.id
                logger.info(f"Stored blocked prompt in database with message ID: {blocked_message_id}")
                
                # Set message_id in Phoenix span for correlation
                if request_span:
                    request_span.set_attribute("moolai.message_id", str(blocked_message_id))
                    request_span.set_attribute("moolai.firewall.blocked", True)
                    request_span.set_attribute("moolai.firewall.violations", [v.violation_type for v in violations])
                            
            except Exception as e:
                logger.warning(f"Failed to store blocked prompt in database: {e}")
            
            # Return structured blocked response
            return {
                "domain": "security",
                "task_type": "content_filtering",
                "keywords": ["blocked", "firewall", "violation"],
                "response": "Your request was blocked by our security firewall due to sensitive content detection. Please rephrase your request without sensitive information.",
                "session_id": session_id,
                "message_id": blocked_message_id,  # Now includes message ID for blocked content
                "from_cache": False,
                "similarity": None,
                "firewall_scan": firewall_scan_result,
                "violations": violations,
                "content_filtered": True,
                "evaluation_scores": None,
                "is_evaluable": False
            }
        else:
            # Content passed firewall - create clean scan summary
            logger.info("Content passed firewall checks")
            firewall_scan_result = FirewallScanSummary(
                scans_performed=["pii", "secrets", "toxicity"],
                violations_found=[],
                safe_to_process=True,
                text_length=len(query)
            )
    else:
        logger.info("Firewall is disabled, skipping scan")
        # Set default scan result for when firewall is disabled
        scan_result = {"pii": {"contains_pii": False}, "secrets": {"contains_secrets": False}, "toxicity": {"contains_toxicity": False}}
        firewall_scan_result = FirewallScanSummary(
            scans_performed=["pii", "secrets", "toxicity"],
            violations_found=[],
            safe_to_process=True,
            text_length=len(query)
        )
    
    # Start monitoring if available (legacy - will be removed in Phase 4)
    request_context = None
    if monitoring_middleware and MonitoringSessionLocal:
        try:
            # Create database session for monitoring
            async with MonitoringSessionLocal() as db_session:
                monitoring_middleware.db_session = db_session
                request_context = await monitoring_middleware.track_request(
                    user_id=user_id,
                    agent_type="prompt_response",
                    prompt=query,
                    session_id=session_id
                )
        except Exception as e:
            logger.warning(f"Failed to start monitoring: {e}")
    
    # Cache lookup with enhanced tracing
    cache_hit = False
    cache_similarity = None
    if ENABLE_CACHING:
        if TRACING_AVAILABLE:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("moolai.cache.lookup") as cache_span:
                # Set cache lookup attributes
                cache_span.set_attribute("moolai.cache.enabled", True)
                cache_span.set_attribute("moolai.cache.session_id", session_id)
                
                cache_result = await get_cached_response(query, session_id)
                if cache_result and cache_result.get("from_cache"):
                    cache_hit = True
                    cache_similarity = cache_result.get("similarity")
                    logger.info(f"LLM Cache HIT for session {session_id} (similarity: {cache_result.get('similarity', 'exact')})")
                    
                    # Set vendor-prefixed cache attributes for Phoenix tracking
                    cache_span.set_attribute("moolai.cache.hit", True)
                    cache_span.set_attribute("moolai.cache.similarity", cache_similarity or 1.0)
                    cache_span.set_attribute("moolai.cache.key", cache_result.get("cache_key", "unknown"))
                    
                    # Also set on request span for top-level visibility
                    if request_span:
                        request_span.set_attribute("moolai.cache.hit", True)
                        request_span.set_attribute("moolai.cache.similarity", cache_similarity or 1.0)
                    
                    # Parse structured cache response and return early
                    cached_content = cache_result["response"]
                    try:
                        if cached_content.startswith('{"') and cached_content.endswith('}'):
                            # Parse structured cache response
                            parsed_cached = json.loads(cached_content)
                            domain = parsed_cached.get("domain", "unknown")
                            task_type = parsed_cached.get("task_type", "unknown")
                            keywords = parsed_cached.get("keywords", [])
                            answer = parsed_cached.get("response", cached_content)
                        else:
                            # Fallback for legacy cache entries
                            domain = "general"
                            task_type = "question_answering"
                            keywords = []
                            answer = cached_content
                    except json.JSONDecodeError:
                        domain = "general"
                        task_type = "question_answering"
                        keywords = []
                        answer = cached_content
                    
                    # Track response with monitoring
                    if monitoring_middleware and MonitoringSessionLocal and request_context:
                        try:
                            async with MonitoringSessionLocal() as db_session:
                                monitoring_middleware.db_session = db_session
                                await monitoring_middleware.track_response(
                                    request_context=request_context,
                                    response=answer,
                                    model=model,
                                    cache_hit=True,
                                    cache_similarity=cache_similarity
                                )
                        except Exception as e:
                            logger.warning(f"Failed to track cached response: {e}")
                    
                    # Store cached responses in database for analytics and dashboard visibility
                    cached_message_id = None
                    try:
                        chat_service = get_chat_service()
                        
                        # Store user message for cached response
                        user_metadata = {
                            "model": model,
                            "processing_time_ms": 0  # No processing time for cache hit
                        }
                        user_message = await chat_service.store_message(
                            session_id=session_id,
                            role="user",
                            content=query,
                            user_id=user_id,
                            metadata=user_metadata
                        )
                        
                        # Store assistant cached response
                        assistant_metadata = {
                            "model": model,
                            "tokens": 0,  # No new tokens for cached response
                            "processing_time_ms": 0,
                            "domain": domain,
                            "task_type": task_type,
                            "keywords": keywords,
                            "from_cache": True,
                            "cache_similarity": cache_similarity
                        }
                        assistant_message = await chat_service.store_message(
                            session_id=session_id,
                            role="assistant", 
                            content=answer,
                            user_id=user_id,
                            metadata=assistant_metadata
                        )
                        cached_message_id = assistant_message.id
                        logger.info(f"Stored cached response in database with message ID: {cached_message_id}")
                        
                        # Set message_id in Phoenix span for correlation
                        if request_span:
                            request_span.set_attribute("moolai.message_id", str(cached_message_id))
                            request_span.set_attribute("moolai.cache.stored", True)
                            
                    except Exception as e:
                        logger.warning(f"Failed to store cached response in database: {e}")
                    
                    return {
                        "domain": domain,
                        "task_type": task_type,
                        "keywords": keywords,
                        "response": answer,
                        "session_id": session_id,
                        "message_id": cached_message_id,  # Now includes message ID for cached responses
                        "from_cache": True,
                        "similarity": cache_result.get("similarity"),
                        "firewall_scan": None,
                        "violations": [],
                        "content_filtered": False,
                        "evaluation_scores": None,  # Cached responses don't get re-evaluated
                        "is_evaluable": False,
                        "tokens_used": 0,  # No new tokens used from cache
                        "cost": 0.0        # No cost for cached response
                    }
                else:
                    # Cache miss
                    cache_span.set_attribute("moolai.cache.hit", False)
                    cache_span.set_attribute("moolai.cache.similarity", 0.0)
                    
                    if request_span:
                        request_span.set_attribute("moolai.cache.hit", False)
                        request_span.set_attribute("moolai.cache.similarity", 0.0)
        else:
            cache_result = await get_cached_response(query, session_id)
            if cache_result and cache_result.get("from_cache"):
                cache_hit = True
                cache_similarity = cache_result.get("similarity")
                logger.info(f"LLM Cache HIT for session {session_id} (similarity: {cache_result.get('similarity', 'exact')})")
            
            # Parse structured cache response
            cached_content = cache_result["response"]
            try:
                if cached_content.startswith('{"') and cached_content.endswith('}'):
                    # Parse structured cache response
                    parsed_cached = json.loads(cached_content)
                    domain = parsed_cached.get("domain", "unknown")
                    task_type = parsed_cached.get("task_type", "unknown")
                    keywords = parsed_cached.get("keywords", [])
                    answer = parsed_cached.get("response", cached_content)
                else:
                    # Fallback for legacy cache entries
                    domain = "general"
                    task_type = "question_answering"
                    keywords = []
                    answer = cached_content
            except json.JSONDecodeError:
                domain = "general"
                task_type = "question_answering"
                keywords = []
                answer = cached_content
            
            # Track response with monitoring
            if monitoring_middleware and MonitoringSessionLocal and request_context:
                try:
                    async with MonitoringSessionLocal() as db_session:
                        monitoring_middleware.db_session = db_session
                        await monitoring_middleware.track_response(
                            request_context=request_context,
                            response=answer,
                            model=model,
                            cache_hit=True,
                            cache_similarity=cache_similarity
                        )
                except Exception as e:
                    logger.warning(f"Failed to track cached response: {e}")
            
            # Store cached responses in database for analytics and dashboard visibility
            cached_message_id = None
            try:
                chat_service = get_chat_service()
                
                # Store user message for cached response
                user_metadata = {
                    "model": model,
                    "processing_time_ms": 0  # No processing time for cache hit
                }
                user_message = await chat_service.store_message(
                    session_id=session_id,
                    role="user",
                    content=query,
                    user_id=user_id,
                    metadata=user_metadata
                )
                
                # Store assistant cached response
                assistant_metadata = {
                    "model": model,
                    "tokens": 0,  # No new tokens for cached response
                    "processing_time_ms": 0,
                    "domain": domain,
                    "task_type": task_type,
                    "keywords": keywords,
                    "from_cache": True,
                    "cache_similarity": cache_similarity,
                    # Provider tracking for cached responses
                    "provider_used": "cache",
                    "cost_estimate": 0.0,
                    "dynaroute_metadata": None
                }
                assistant_message = await chat_service.store_message(
                    session_id=session_id,
                    role="assistant", 
                    content=answer,
                    user_id=user_id,
                    metadata=assistant_metadata
                )
                cached_message_id = assistant_message.id
                logger.info(f"Stored cached response in database with message ID: {cached_message_id}")
                        
            except Exception as e:
                logger.warning(f"Failed to store cached response in database: {e}")
            
            return {
                "domain": domain,
                "task_type": task_type,
                "keywords": keywords,
                "response": answer,
                "session_id": session_id,
                "message_id": cached_message_id,  # Now includes message ID for cached responses
                "from_cache": True,
                "similarity": cache_result.get("similarity"),
                "firewall_scan": None,
                "violations": [],
                "content_filtered": False,
                "evaluation_scores": None,  # Cached responses don't get re-evaluated
                "is_evaluable": False,
                "tokens_used": 0,  # No new tokens used from cache
                "cost": 0.0,       # No cost for cached response
                "model": "cached"  # Cached responses don't use a specific model
            }
    
    # Generate fresh response from OpenAI with enhanced tracing
    logger.info(f"LLM Cache MISS - generating fresh response for session {session_id}")
    
    if TRACING_AVAILABLE:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("moolai.llm.call") as llm_span:
            # Set LLM call attributes with vendor prefix
            llm_span.set_attribute("moolai.llm.model", model)
            llm_span.set_attribute("moolai.llm.temperature", 0.2)
            llm_span.set_attribute("moolai.llm.max_tokens", 1000)
            llm_span.set_attribute("moolai.llm.cache_miss", True)
            
            if request_span:
                request_span.set_attribute("moolai.llm.model", model)
                request_span.set_attribute("moolai.llm.fresh_call", True)
            
            # Domain classification already completed before firewall scan
            # Using previously obtained classification results
            logger.info(f"Using pre-classified domain: {domain}, task_type: {task_type}")
            
            # Step 2: Get model configuration for user response
            routing_service = get_model_routing_service(organization_id)
            model_config = routing_service.get_model_for_call_type(
                call_type=CallType.USER_RESPONSE,
                domain=domain,
                override_model=model if model != "gpt-4o" else None  # Allow routing agent override
            )
            
            # Use routed model for user response
            response_model = model_config.model_name
            response_max_tokens = model_config.max_tokens
            response_temperature = model_config.temperature
            
            # Step 3: Generate user response (separate LLM call) - using DynaRoute
            try:
                # Try relative imports first (when run as package module)
                from ...services.dynaroute_service import get_dynaroute_service
            except ImportError:
                # Fallback to absolute imports (when run directly or in different context)
                try:
                    from app.services.dynaroute_service import get_dynaroute_service
                except ImportError:
                    # Last resort - add path and import
                    import sys
                    import os
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    app_dir = os.path.dirname(os.path.dirname(current_dir))
                    root_dir = os.path.dirname(app_dir)
                    if root_dir not in sys.path:
                        sys.path.insert(0, root_dir)
                    from app.services.dynaroute_service import get_dynaroute_service

            proxy = get_dynaroute_service()
            
            # Get conversation history for context
            chat_service = get_chat_service()
            conversation_history = await chat_service.get_conversation_history(session_id)
            logger.info(f"Retrieved {len(conversation_history)} previous messages for session {session_id}")
            
            # Build simple system instruction for user response (no domain classification)
            user_response_instruction = f"""You are an advanced AI assistant. Your tone must be formal, concise, neutral, and direct—no sugar-coating.
Always:
- Provide clear, evidence-based answers with minimal filler.  
- Think creatively and propose innovative, forward-looking ideas.  
- Be transparent about uncertainties or limitations.  
- Use bullet points and short paragraphs for readability.

The user's query has been classified as: Domain={domain}, Task Type={task_type}
Provide a helpful and accurate response to their query."""

            # Build messages array with conversation history + current query
            messages = [{"role": "system", "content": user_response_instruction}]
            messages.extend(conversation_history)  # Add conversation history
            messages.append({"role": "user", "content": query})  # Add current query (no JSON wrapping)
            
            logger.info(f"🚀 [MAIN-RESPONSE] Calling DynaRoute service for user response:")
            logger.info(f"   📝 Messages count: {len(messages)}")
            logger.info(f"   🎯 Model requested: {response_model}")
            logger.info(f"   🌡️  Temperature: {response_temperature}")
            logger.info(f"   📊 Max tokens: {response_max_tokens}")
            logger.info(f"   👤 User ID: {user_id}")
            logger.info(f"   🔧 Service: main_response")
            logger.info(f"   🎯 Operation: generate_user_response")

            response = await proxy.chat_completion(
                model=response_model,
                messages=messages,
                max_tokens=response_max_tokens,
                temperature=response_temperature,
                user_id=user_id,
                service_name="main_response",
                operation_name="generate_user_response"
                # No response_format needed for user response
            )

            logger.info(f"✅ [MAIN-RESPONSE] DynaRoute response received:")
            logger.info(f"   🔍 Response type: {type(response)}")
            logger.info(f"   🎯 Model used: {getattr(response, 'model', 'unknown')}")
            logger.info(f"   📊 Has usage info: {hasattr(response, 'usage')}")
            logger.info(f"   🎯 Has DynaRoute metadata: {hasattr(response, 'dynaroute_metadata')}")
            if hasattr(response, 'dynaroute_metadata'):
                logger.info(f"      - DynaRoute metadata: {response.dynaroute_metadata}")
            if hasattr(response, 'usage') and response.usage:
                logger.info(f"   📊 Token usage: {response.usage.__dict__ if hasattr(response.usage, '__dict__') else response.usage}")
            
            # Calculate cost for user response
            user_response_cost = 0.0
            if hasattr(response, 'usage') and response.usage:
                try:
                    # Import cost calculator dynamically
                    import sys
                    sys.path.append(os.path.join(os.path.dirname(__file__), '../../monitoring/utils'))
                    from cost_calculator import calculate_cost
                    
                    user_response_cost = calculate_cost(
                        model=response_model,
                        input_tokens=response.usage.prompt_tokens or 0,
                        output_tokens=response.usage.completion_tokens or 0
                    )
                    logger.info(f"User response cost: ${user_response_cost:.6f} for {response.usage.total_tokens} tokens")
                except Exception as e:
                    logger.warning(f"Could not calculate user response cost: {e}")
                    # Fallback calculation
                    user_response_cost = ((response.usage.prompt_tokens or 0) * 0.0000005 + 
                           (response.usage.completion_tokens or 0) * 0.0000015)
            
            # Total cost = classification cost + user response cost
            cost = classification_cost + user_response_cost
            
            # Set response attributes including cost
            if isinstance(response, dict) and 'usage' in response:
                # DynaRoute dict response
                usage = response['usage']
                llm_span.set_attribute("moolai.llm.input_tokens", usage.get('prompt_tokens', 0))
                llm_span.set_attribute("moolai.llm.output_tokens", usage.get('completion_tokens', 0))
                llm_span.set_attribute("moolai.llm.total_tokens", usage.get('total_tokens', 0))
            elif hasattr(response, 'usage') and response.usage:
                # OpenAI object response
                llm_span.set_attribute("moolai.llm.input_tokens", response.usage.prompt_tokens or 0)
                llm_span.set_attribute("moolai.llm.output_tokens", response.usage.completion_tokens or 0)
                llm_span.set_attribute("moolai.llm.total_tokens", response.usage.total_tokens or 0)
                llm_span.set_attribute("moolai.llm.cost", cost)
                llm_span.set_attribute("moolai.llm.classification_tokens", classification_tokens)
                llm_span.set_attribute("moolai.llm.classification_cost", classification_cost)
                llm_span.set_attribute("moolai.llm.user_response_model", response_model)
                
                if request_span:
                    request_span.set_attribute("moolai.tokens.input", response.usage.prompt_tokens or 0)
                    request_span.set_attribute("moolai.tokens.output", response.usage.completion_tokens or 0)
                    request_span.set_attribute("moolai.tokens.total", response.usage.total_tokens or 0)
                    request_span.set_attribute("moolai.cost", cost)
                    request_span.set_attribute("moolai.domain", domain)
                    request_span.set_attribute("moolai.task_type", task_type)
    else:
        # Step 1: Domain Classification (separate LLM call) - no tracing version
        domain_service = get_domain_classification_service(organization_id)
        classification_result = await domain_service.classify_query(
            query=query,
            session_id=session_id,
            user_id=user_id
        )
        
        # Extract domain classification results
        domain = classification_result["domain"]
        task_type = classification_result["task_type"] 
        keywords = classification_result["keywords"]
        classification_tokens = classification_result["classification_tokens"]
        classification_cost = classification_result["classification_cost"]
        
        # Step 2: Get model configuration for user response
        routing_service = get_model_routing_service(organization_id)
        model_config = routing_service.get_model_for_call_type(
            call_type=CallType.USER_RESPONSE,
            domain=domain,
            override_model=model if model != "gpt-4o" else None
        )
        
        # Use routed model for user response
        response_model = model_config.model_name
        response_max_tokens = model_config.max_tokens
        response_temperature = model_config.temperature
        
        # Step 3: Generate user response (separate LLM call) - using DynaRoute
        try:
            # Try relative imports first (when run as package module)
            from ...services.dynaroute_service import get_dynaroute_service
        except ImportError:
            # Fallback to absolute imports (when run directly or in different context)
            try:
                from app.services.dynaroute_service import get_dynaroute_service
            except ImportError:
                # Last resort - add path and import
                import sys
                import os
                current_dir = os.path.dirname(os.path.abspath(__file__))
                app_dir = os.path.dirname(os.path.dirname(current_dir))
                root_dir = os.path.dirname(app_dir)
                if root_dir not in sys.path:
                    sys.path.insert(0, root_dir)
                from app.services.dynaroute_service import get_dynaroute_service

        proxy = get_dynaroute_service()
        
        # Get conversation history for context
        chat_service = get_chat_service()
        conversation_history = await chat_service.get_conversation_history(session_id)
        logger.info(f"Retrieved {len(conversation_history)} previous messages for session {session_id}")
        
        # Build simple system instruction for user response
        user_response_instruction = f"""You are an advanced AI assistant. Your tone must be formal, concise, neutral, and direct—no sugar-coating.
Always:
- Provide clear, evidence-based answers with minimal filler.  
- Think creatively and propose innovative, forward-looking ideas.  
- Be transparent about uncertainties or limitations.  
- Use bullet points and short paragraphs for readability.

The user's query has been classified as: Domain={domain}, Task Type={task_type}
Provide a helpful and accurate response to their query."""
        
        # Build messages array with conversation history + current query
        messages = [{"role": "system", "content": user_response_instruction}]
        messages.extend(conversation_history)  # Add conversation history
        messages.append({"role": "user", "content": query})  # Add current query (no JSON wrapping)
        
        logger.debug(f"Sending {len(messages)} messages to OpenAI for user response (model: {response_model})")
        
        response = await proxy.chat_completion(
            model=response_model,
            messages=messages,
            max_tokens=response_max_tokens,
            temperature=response_temperature,
            user_id=user_id,
            service_name="main_response",
            operation_name="generate_user_response"
            # No response_format needed for user response
        )
        
        # Calculate cost for user response
        user_response_cost = 0.0
        if hasattr(response, 'usage') and response.usage:
            try:
                import sys
                sys.path.append(os.path.join(os.path.dirname(__file__), '../../monitoring/utils'))
                from cost_calculator import calculate_cost
                
                user_response_cost = calculate_cost(
                    model=response_model,
                    input_tokens=response.usage.prompt_tokens or 0,
                    output_tokens=response.usage.completion_tokens or 0
                )
            except Exception:
                # Fallback calculation
                user_response_cost = ((response.usage.prompt_tokens or 0) * 0.0000005 + 
                       (response.usage.completion_tokens or 0) * 0.0000015)
        
        # Total cost = classification cost + user response cost
        cost = classification_cost + user_response_cost
    
    # Get the user response - handle both OpenAI objects and dict responses from DynaRoute
    if isinstance(response, dict):
        # DynaRoute normalized response format
        answer = response['choices'][0]['message']['content']
        # Update the model to reflect the actual model used by DynaRoute
        if 'model' in response and response['model']:
            actual_model_used = response['model']
            logger.info(f"✅ [MAIN-RESPONSE] DynaRoute actual model: {actual_model_used}")
            # Update the model variable for metadata
            model = actual_model_used
        logger.info(f"✅ [MAIN-RESPONSE] DynaRoute response extracted: {answer[:100]}...")
    else:
        # Standard OpenAI response object
        answer = response.choices[0].message.content
        logger.info(f"✅ [MAIN-RESPONSE] OpenAI response extracted: {answer[:100]}...")
    
    # Domain classification results are already available from earlier
    # domain, task_type, keywords are already set from classification_result
    
    # Run LLM evaluation on the response - create child span for evaluation orchestration
    evaluation_scores = None
    try:
        # Create evaluation span as child of the main request span
        if TRACING_AVAILABLE:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("moolai.evaluation.orchestration") as eval_span:
                eval_span.set_attribute("moolai.evaluation.enabled", True)
                eval_span.set_attribute("moolai.evaluation.services", ["correctness", "relevance", "hallucination", "human_vs_ai"])
                
                # Run evaluation services in parallel for better performance
                # Each evaluation service will create its own child span via OpenAI proxy
                correctness_task = evaluate_answer_correctness(query, answer, user_id, session_id)
                relevance_task = evaluate_answer_relevance(query, answer, user_id, session_id)
                hallucination_task = evaluate_hallucination(query, answer, user_id, session_id)
                human_vs_ai_task = evaluate_human_vs_ai(query, answer, user_id, session_id)
                
                correctness_result, relevance_result, hallucination_result, human_vs_ai_result = await asyncio.gather(
                    correctness_task, relevance_task, hallucination_task, human_vs_ai_task,
                    return_exceptions=True
                )
        else:
            # Fallback without tracing
            correctness_task = evaluate_answer_correctness(query, answer, user_id, session_id)
            relevance_task = evaluate_answer_relevance(query, answer, user_id, session_id)
            hallucination_task = evaluate_hallucination(query, answer, user_id, session_id)
            human_vs_ai_task = evaluate_human_vs_ai(query, answer, user_id, session_id)
            
            correctness_result, relevance_result, hallucination_result, human_vs_ai_result = await asyncio.gather(
                correctness_task, relevance_task, hallucination_task, human_vs_ai_task,
                return_exceptions=True
            )
        
        # Extract scores from evaluation results
        correctness_score = correctness_result.get("score", 0.0) if isinstance(correctness_result, dict) else 0.0
        relevance_score = relevance_result.get("score", 0.0) if isinstance(relevance_result, dict) else 0.0
        hallucination_score = hallucination_result.get("score", 0.0) if isinstance(hallucination_result, dict) else 0.0
        human_likeness_score = human_vs_ai_result.get("score", 0.0) if isinstance(human_vs_ai_result, dict) else 0.0
        
        evaluation_scores = LLMEvaluationScores(
            answer_correctness=correctness_score,
            answer_relevance=relevance_score,
            hallucination=hallucination_score,
            human_likeness=human_likeness_score
        )
        logger.info(f"LLM evaluation completed: correctness={correctness_score:.2f}, relevance={relevance_score:.2f}, hallucination={hallucination_score:.2f}, human_likeness={human_likeness_score:.2f}")
        
    except Exception as e:
        logger.error(f"LLM evaluation failed: {e}")
        evaluation_scores = LLMEvaluationScores(
            answer_correctness=0.0,
            answer_relevance=0.0,
            hallucination=0.0
        )
    
    # Track response with monitoring
    if monitoring_middleware and MonitoringSessionLocal and request_context:
        try:
            async with MonitoringSessionLocal() as db_session:
                monitoring_middleware.db_session = db_session
                await monitoring_middleware.track_response(
                    request_context=request_context,
                    response=response,
                    model=model,
                    cache_hit=False,
                    cache_similarity=None
                )
        except Exception as e:
            logger.warning(f"Failed to track fresh response: {e}")
    
    # Store response in cache with structured data
    if ENABLE_CACHING:
        structured_response = json.dumps({
            "domain": domain,
            "task_type": task_type,
            "keywords": keywords,
            "response": answer
        })
        await store_cached_response(query, structured_response, session_id)
        logger.info(f"Stored structured response in enhanced cache for session {session_id}")
    
    # Store conversation messages in database for context memory
    assistant_message_id = None  # Initialize to ensure it's always defined
    try:
        chat_service = get_chat_service()
        
        # Store user message first
        user_metadata = {
            "model": model,
            "processing_time_ms": int((time.time() - time.time()) * 1000)  # Will be updated with actual time
        }
        user_message = await chat_service.store_message(
            session_id=session_id,
            role="user",
            content=query,  # Store original query, not JSON-wrapped
            user_id=user_id,
            metadata=user_metadata
        )
        user_message_id = user_message.id
        
        # Set message_id in Phoenix span for correlation with prompt tracking
        request_span.set_attribute("moolai.message_id", str(user_message_id))
        
        # Extract provider metadata from DynaRoute response
        logger.info(f"🔍 [MAIN-RESPONSE] Extracting provider metadata from response:")
        logger.info(f"🔍 [MAIN-RESPONSE-DEBUG] Response type: {type(response)}")
        if isinstance(response, dict):
            logger.info(f"🔍 [MAIN-RESPONSE-DEBUG] Response keys: {list(response.keys())}")
            logger.info(f"🔍 [MAIN-RESPONSE-DEBUG] Response ID: {response.get('id', 'NO_ID')}")
        logger.info(f"🔍 [MAIN-RESPONSE-DEBUG] Has dynaroute_metadata attr: {hasattr(response, 'dynaroute_metadata')}")

        provider_used = "openai"  # default fallback
        cost_estimate = None
        dynaroute_metadata = None

        if hasattr(response, 'dynaroute_metadata') or (isinstance(response, dict) and response.get('id', '').startswith('dynaroute-')):
            # DynaRoute was used - handle both object and dict responses
            provider_used = "dynaroute"
            if hasattr(response, 'dynaroute_metadata'):
                dynaroute_metadata = response.dynaroute_metadata
            else:
                # For dict responses, create metadata from available data
                dynaroute_metadata = {
                    "response_id": response.get('id'),
                    "model": response.get('model'),
                    "usage": response.get('usage', {}),
                    "source": "dynaroute_service"
                }
            logger.info(f"   🎯 DynaRoute was used!")
            logger.info(f"   📊 DynaRoute metadata: {dynaroute_metadata}")

            # Extract cost estimate from usage if available - handle both dict and object responses
            if isinstance(response, dict) and 'usage' in response:
                # DynaRoute dict response
                usage = response['usage']
                total_tokens = usage.get('total_tokens', 0)
                # Use actual DynaRoute cost if available, otherwise rough estimate
                if 'cost' in usage and 'total_cost' in usage['cost']:
                    cost_estimate = float(usage['cost']['total_cost'])
                    logger.info(f"   💰 DynaRoute actual cost: ${cost_estimate:.6f} (tokens: {total_tokens})")
                else:
                    # Rough cost estimate: DynaRoute is ~30% of OpenAI cost
                    openai_cost = total_tokens * 0.000002  # $0.002 per 1K tokens estimate
                    cost_estimate = openai_cost * 0.30
                    logger.info(f"   💰 DynaRoute estimated cost: ${cost_estimate:.6f} (tokens: {total_tokens})")
            elif hasattr(response, 'usage') and response.usage:
                # OpenAI object response
                total_tokens = response.usage.total_tokens or 0
                # Rough cost estimate: DynaRoute is ~30% of OpenAI cost
                openai_cost = total_tokens * 0.000002  # $0.002 per 1K tokens estimate
                cost_estimate = openai_cost * 0.30
                logger.info(f"   💰 DynaRoute cost estimate: ${cost_estimate:.6f} (tokens: {total_tokens})")
            else:
                logger.info(f"   ⚠️  No usage data available for cost calculation")
        elif isinstance(response, dict) and 'usage' in response:
            # OpenAI dict fallback
            usage = response['usage']
            total_tokens = usage.get('total_tokens', 0)
            cost_estimate = total_tokens * 0.000002  # OpenAI cost estimate
            logger.info(f"   🔄 OpenAI fallback was used (dict response)")
            logger.info(f"   💰 OpenAI cost estimate: ${cost_estimate:.6f} (tokens: {total_tokens})")
        elif hasattr(response, 'usage') and response.usage:
            # OpenAI object fallback
            total_tokens = response.usage.total_tokens or 0
            cost_estimate = total_tokens * 0.000002  # OpenAI cost estimate
            logger.info(f"   🔄 OpenAI fallback was used")
            logger.info(f"   💰 OpenAI cost estimate: ${cost_estimate:.6f} (tokens: {total_tokens})")
        else:
            logger.info(f"   ⚠️  No usage data available - cannot determine provider or cost")

        logger.info(f"   📋 Final provider metadata:")
        logger.info(f"      🏭 Provider: {provider_used}")
        logger.info(f"      💰 Cost: ${cost_estimate:.6f}" if cost_estimate else "      💰 Cost: N/A")
        logger.info(f"      🎯 Has DynaRoute metadata: {dynaroute_metadata is not None}")

        # Store assistant response
        assistant_metadata = {
            "model": model,
            "tokens": total_tokens if 'total_tokens' in locals() else None,
            "processing_time_ms": int((time.time() - time.time()) * 1000),  # Will be calculated properly
            "domain": domain,
            "task_type": task_type,
            "keywords": keywords,
            # Provider tracking
            "provider_used": provider_used,
            "cost_estimate": cost_estimate,
            "dynaroute_metadata": dynaroute_metadata
        }
        assistant_message = await chat_service.store_message(
            session_id=session_id,
            role="assistant", 
            content=answer,
            user_id=user_id,
            metadata=assistant_metadata
        )
        assistant_message_id = assistant_message.id
        logger.info(f"DEBUG: Stored assistant message with database ID: {assistant_message_id}", extra={
            "session_id": session_id,
            "message_id": assistant_message_id,
            "service": "main_response"
        })
        
        logger.info(f"Stored conversation messages for session {session_id}")
        
        # Store evaluation scores to database if evaluations were successful
        if evaluation_scores and evaluation_scores.answer_correctness > 0:
            try:
                await chat_service.store_llm_evaluation_scores(
                    session_id=session_id,
                    role="assistant",  # The assistant message we just stored
                    answer_correctness=evaluation_scores.answer_correctness,
                    answer_relevance=evaluation_scores.answer_relevance, 
                    hallucination_score=evaluation_scores.hallucination,
                    coherence_score=evaluation_scores.human_likeness,  # Map human_likeness to coherence
                    evaluation_model=model,
                    user_id=user_id
                )
                logger.info(f"Stored LLM evaluation scores for session {session_id}")
            except Exception as eval_e:
                logger.error(f"Failed to store evaluation scores for session {session_id}: {eval_e}")
        
    except Exception as e:
        logger.error(f"Failed to store conversation messages for session {session_id}: {e}")
        # Don't break the flow if message storage fails
    
    # Build comprehensive structured response
    result = {
        "domain": domain,
        "task_type": task_type,
        "keywords": keywords,
        "response": answer,
        "session_id": session_id,
        "message_id": assistant_message_id,  # Database message ID for feedback
        "from_cache": False,
        "similarity": None,
        "firewall_scan": firewall_scan_result,  # Set from firewall processing
        "violations": [],
        "content_filtered": False,
        "evaluation_scores": evaluation_scores,
        "is_evaluable": True,
        "model": response_model if 'response_model' in locals() else model  # Include model used
    }
    
    logger.info(f"DEBUG: Final result contains message_id: {result.get('message_id')}", extra={
        "session_id": session_id,
        "result_message_id": result.get("message_id"),
        "service": "main_response"
    })
    
    # Add usage and cost information from both calls (classification + user response)
    if hasattr(response, 'usage') and response.usage:
        # User response tokens
        user_response_tokens = response.usage.total_tokens or 0
        user_response_prompt_tokens = response.usage.prompt_tokens or 0
        user_response_completion_tokens = response.usage.completion_tokens or 0
        
        # Total tokens = classification + user response
        result["tokens_used"] = classification_tokens + user_response_tokens
        result["prompt_tokens"] = user_response_prompt_tokens  # User response only (classification is separate)
        result["completion_tokens"] = user_response_completion_tokens  # User response only
        result["cost"] = cost  # Total cost (classification + user response)
        
        # Detailed breakdown for monitoring
        result["classification_tokens"] = classification_tokens
        result["classification_cost"] = classification_cost
        result["user_response_tokens"] = user_response_tokens
        result["user_response_cost"] = cost - classification_cost if 'classification_cost' in locals() else 0.0
        result["user_response_model"] = response_model if 'response_model' in locals() else model
    
    # Broadcast prompt update to WebSocket subscribers
    try:
        # Import broadcast function dynamically to avoid circular imports
        # Use absolute import since this module is loaded with sys.path manipulation
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(os.path.dirname(current_dir))
        if app_dir not in sys.path:
            sys.path.insert(0, app_dir)
        from app.api.routes_websocket import broadcast_prompts_update
        
        # Extract organization ID from user_id or session_id (default to org_001)
        organization_id = "org_001"  # Default organization
        if "_" in user_id:
            org_part = user_id.split("_")[0]
            if org_part.startswith("org"):
                organization_id = org_part
        
        # Prepare broadcast data - match the structure expected by UserPromptsTracker
        broadcast_data = {
            "message_id": result.get("message_id"),
            "user_id": user_id,
            "username": user_id.split("@")[0] if "@" in user_id else user_id,  # Extract username from email if present
            "full_name": user_id,  # Fallback to user_id if no proper name available
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt_text": query,
            "response_text": answer,
            "total_duration_ms": result.get("latency_ms"),
            "cache_hit": result.get("from_cache", False),
            "similarity_score": result.get("similarity"),
            "total_tokens": result.get("tokens_used"),
            "prompt_tokens": result.get("prompt_tokens"),
            "completion_tokens": result.get("completion_tokens"),
            "total_cost": result.get("cost"),
            "model": result.get("user_response_model", result.get("model")),
            "was_blocked": result.get("content_filtered", False),
            "block_reason": None,  # Could be extracted from firewall_scan if needed
            "evaluation_scores": {}
        }
        
        # Add evaluation scores if available
        if evaluation_scores:
            broadcast_data["evaluation_scores"] = {
                "answer_correctness": {
                    "score": evaluation_scores.answer_correctness,
                    "reasoning": "Automated evaluation"
                },
                "answer_relevance": {
                    "score": evaluation_scores.answer_relevance,
                    "reasoning": "Automated evaluation"
                },
                "hallucination": {
                    "score": evaluation_scores.hallucination,
                    "reasoning": "Automated evaluation"
                }
            }
            if hasattr(evaluation_scores, 'human_likeness'):
                broadcast_data["evaluation_scores"]["human_vs_ai"] = {
                    "score": evaluation_scores.human_likeness,
                    "reasoning": "Automated evaluation"
                }
        
        # Broadcast to WebSocket subscribers asynchronously
        asyncio.create_task(broadcast_prompts_update(organization_id, broadcast_data))
        logger.info(f"Scheduled prompt broadcast for organization {organization_id}")
        
    except Exception as e:
        logger.warning(f"Failed to broadcast prompt update: {e}")
        # Don't break the main flow if broadcasting fails
    
    return result

@app.get("/respond")
# Phoenix/OpenTelemetry tracing handled automatically
async def get_response(
    query: str = Query(..., description="User query to get LLM response for"),
    session_id: str = Query("default", description="Session ID for caching"),
    user_id: str = Query("default_user", description="User ID for monitoring"),
    model: str = Query("gpt-4o", description="LLM model to use")
):
    """
    Get LLM response for a user query with caching support and monitoring.
    
    Args:
        query: The user's question or prompt
        session_id: Session ID for cache isolation
        user_id: User ID for monitoring
        
    Returns:
        JSON response with the LLM's answer and cache metadata
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query parameter cannot be empty")
    
    # Enhanced firewall check with tracing
    firewall_blocked = False
    firewall_reasons = None
    if ENABLE_FIREWALL:
        # Pass request span context to firewall scan for comprehensive tracing
        current_span = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
            except Exception:
                pass
        
        scan = await firewall_scan(query.strip(), current_span, domain=None, task_type=None)
        if scan["pii"]["contains_pii"] or scan["secrets"]["contains_secrets"] or scan["toxicity"]["contains_toxicity"]:
            firewall_blocked = True
            firewall_reasons = scan
            
            # Track blocked request with monitoring
            if monitoring_middleware and MonitoringSessionLocal:
                try:
                    async with MonitoringSessionLocal() as db_session:
                        monitoring_middleware.db_session = db_session
                        request_context = await monitoring_middleware.track_request(
                            user_id=user_id,
                            agent_type="prompt_response",
                            prompt=query,
                            session_id=session_id
                        )
                        await monitoring_middleware.track_response(
                            request_context=request_context,
                            response="Request blocked by firewall",
                            model=model,
                            error=None,
                            cache_hit=False,
                            cache_similarity=None,
                            firewall_blocked=True,
                            firewall_reasons=scan
                        )
                except Exception as e:
                    logger.warning(f"Failed to track blocked request: {e}")
            
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Content blocked by firewall",
                    "scan_results": scan
                }
            )
    
    try:
        result = await asyncio.wait_for(
            generate_llm_response(query.strip(), session_id, user_id, model),
            timeout=35.0  # Slightly longer timeout to account for cache calls
        )
        return result
        
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=408,
            content={"error": "Request timeout - the service took too long to respond"}
        )
    except Exception as e:
        logger.error(f"Error in get_response: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {str(e)}"}
        )

@app.post("/respond", response_model=QueryResponse)
# Phoenix/OpenTelemetry tracing handled automatically
async def post_response(request: QueryRequest):
    """
    Get LLM response for a user query (POST version with JSON body).
    
    Args:
        request: JSON body containing the query and optional session_id
        
    Returns:
        JSON response with the LLM's answer and cache metadata
    """
    query = request.query
    session_id = request.session_id or "default"
    model = request.model or "gpt-4o"
    
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # Enhanced firewall check with tracing
    if ENABLE_FIREWALL:
        # Pass request span context to firewall scan for comprehensive tracing
        current_span = None
        if TRACING_AVAILABLE:
            try:
                current_span = trace.get_current_span()
            except Exception:
                pass
        
        scan = await firewall_scan(query.strip(), current_span, domain=None, task_type=None)
        if scan["pii"]["contains_pii"] or scan["secrets"]["contains_secrets"] or scan["toxicity"]["contains_toxicity"]:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Content blocked by firewall",
                    "scan_results": scan
                }
            )
    
    try:
        result = await asyncio.wait_for(
            generate_llm_response(query.strip(), session_id, model=model),
            timeout=35.0  # Slightly longer timeout to account for cache calls
        )
        
        return QueryResponse(
            domain=result.get("domain", "unknown"),
            task_type=result.get("task_type", "unknown"),
            keywords=result.get("keywords", []),
            response=result.get("response", result.get("answer", "")),
            session_id=result["session_id"],
            from_cache=result["from_cache"],
            similarity=result["similarity"],
            firewall_scan=result.get("firewall_scan"),
            violations=result.get("violations", []),
            content_filtered=result.get("content_filtered", False),
            evaluation_scores=result.get("evaluation_scores"),
            is_evaluable=result.get("is_evaluable", True)
        )
        
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=408,
            content={"error": "Request timeout - the service took too long to respond"}
        )
    except Exception as e:
        logger.error(f"Error in post_response: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {str(e)}"}
        )

@app.get("/health")
async def health_check():
    """Health check endpoint with cache service status"""
    cache_status = "unknown"
    if ENABLE_CACHING:
        try:
            cache_service = await get_cache_service_instance()
            cache_status = "connected"
        except Exception as e:
            logger.error(f"Cache service health check failed: {e}")
            cache_status = "error"
    else:
        cache_status = "disabled"
    
    return {
        "status": "healthy",
        "cache_service": cache_status,
        "caching_enabled": ENABLE_CACHING
    }

# Cache management endpoints
@app.get("/cache/health")
async def cache_health():
    """Check cache service health"""
    if not ENABLE_CACHING:
        return {"cache_available": False, "message": "Caching is disabled"}
    
    try:
        cache_service = await get_cache_service_instance()
        return {
            "cache_available": True,
            "cache_service": "enhanced",
            "cache_type": "semantic_similarity"
        }
    except Exception as e:
        return {
            "cache_available": False,
            "cache_service": "enhanced",
            "error": str(e)
        }

@app.get("/cache/config")
async def get_cache_config():
    """Get cache service configuration"""
    if not ENABLE_CACHING:
        return {"error": "Caching is disabled"}
    
    try:
        # Return enhanced cache configuration
        return {
            "enabled": ENABLE_CACHING,
            "cache_type": "Enhanced",
            "features": ["semantic_similarity", "domain_classification", "presidio_integration"],
            "status": "active"
        }
    except Exception as e:
        return {"error": f"Cache service unavailable: {str(e)}"}

@app.post("/cache/config")
async def update_cache_config(config: CacheConfigUpdate):
    """Update cache service configuration"""
    if not ENABLE_CACHING:
        return {"error": "Caching is disabled"}
    
    try:
        # Update cache configuration if supported
        updated_config = {"message": "Cache config update not supported in local mode"}
        if config.enabled is not None:
            updated_config["enabled"] = config.enabled
        if config.ttl is not None:
            updated_config["ttl"] = config.ttl
        if config.similarity_threshold is not None:
            updated_config["similarity_threshold"] = config.similarity_threshold
        return updated_config
    except Exception as e:
        return {"error": f"Cache service unavailable: {str(e)}"}

@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache service statistics"""
    if not ENABLE_CACHING:
        return {"error": "Caching is disabled"}
    
    try:
        # Return enhanced cache stats
        cache_service = await get_cache_service_instance()
        return {"cache_type": "enhanced", "features": ["semantic_similarity", "presidio_integration"], "status": "active"}
    except Exception as e:
        return {"error": f"Cache service unavailable: {str(e)}"}

@app.delete("/cache/keys")
async def clear_cache():
    """Clear all cache entries"""
    if not ENABLE_CACHING:
        return {"error": "Caching is disabled"}
    
    try:
        cache_service = await get_cache_service_instance()
        # Enhanced cache service should implement its own clear method
        return {"message": "Cache clear requested (enhanced service handles internally)"}
    except Exception as e:
        return {"error": f"Cache service unavailable: {str(e)}"}

# Evaluation endpoints
@app.post("/evaluate/correctness")
async def evaluate_response_correctness(request: QueryRequest):
    """Evaluate answer correctness for a query-response pair"""
    try:
        # First get the response
        response_data = await generate_llm_response(request.query, request.session_id, model=request.model)
        answer = response_data["answer"]
        
        # Then evaluate it
        evaluation = await evaluate_answer_correctness(request.query, answer, session_id=request.session_id)
        
        return {
            "query": request.query,
            "answer": answer,
            "evaluation": evaluation,
            "session_id": request.session_id
        }
    except Exception as e:
        logger.error(f"Error in correctness evaluation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/evaluate/relevance")
async def evaluate_response_relevance(request: QueryRequest):
    """Evaluate answer relevance for a query-response pair"""
    try:
        # First get the response
        response_data = await generate_llm_response(request.query, request.session_id, model=request.model)
        answer = response_data["answer"]
        
        # Then evaluate it
        evaluation = await evaluate_answer_relevance(request.query, answer, session_id=request.session_id)
        
        return {
            "query": request.query,
            "answer": answer,
            "evaluation": evaluation,
            "session_id": request.session_id
        }
    except Exception as e:
        logger.error(f"Error in relevance evaluation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/evaluate/comprehensive")
async def evaluate_response_comprehensive(request: QueryRequest):
    """Run comprehensive evaluation on a query-response pair"""
    try:
        # First get the response
        response_data = await generate_llm_response(request.query, request.session_id, model=request.model)
        answer = response_data["answer"]
        
        # Run all evaluations in parallel including human vs AI
        evaluations = await asyncio.gather(
            evaluate_answer_correctness(request.query, answer, session_id=request.session_id),
            evaluate_answer_relevance(request.query, answer, session_id=request.session_id),
            evaluate_goal_accuracy(request.query, answer, session_id=request.session_id),
            evaluate_hallucination(request.query, answer, session_id=request.session_id),
            evaluate_summarization(request.query, answer, session_id=request.session_id),
            evaluate_human_vs_ai(request.query, answer, session_id=request.session_id)
        )
        
        return {
            "query": request.query,
            "answer": answer,
            "evaluations": {
                "correctness": evaluations[0],
                "relevance": evaluations[1],
                "goal_accuracy": evaluations[2],
                "hallucination": evaluations[3],
                "summarization": evaluations[4],
                "human_vs_ai": evaluations[5]
            },
            "session_id": request.session_id
        }
    except Exception as e:
        logger.error(f"Error in comprehensive evaluation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/evaluate/human_vs_ai")
async def evaluate_human_vs_ai_endpoint(request: QueryRequest):
    """Evaluate how human-like the AI response is"""
    try:
        # First get the response
        response_data = await generate_llm_response(request.query, request.session_id, model=request.model)
        answer = response_data.get("response", response_data.get("answer", ""))
        
        # Run human vs AI evaluation
        evaluation = await evaluate_human_vs_ai(request.query, answer, session_id=request.session_id)
        
        return {
            "query": request.query,
            "answer": answer,
            "human_vs_ai_evaluation": evaluation,
            "session_id": request.session_id
        }
    except Exception as e:
        logger.error(f"Error in human vs AI evaluation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

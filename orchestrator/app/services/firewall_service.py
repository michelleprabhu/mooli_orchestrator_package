"""
Enhanced Firewall Service with Presidio Integration
===================================================

Integrates PII detection and anonymization capabilities using Microsoft Presidio
with existing regex-based security scanning. Provides comprehensive firewall
functionality including allowlist checking and violation blocking.
"""

import os
import json
import re
import math
import time
import asyncio
import string
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

# Core dependencies
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from ..core.logging_config import get_logger
from ..db.database import get_db
from ..models.firewall_log import FirewallLog

logger = get_logger(__name__)


class PresidioEngine:
    """Enhanced PII detection and anonymization using Microsoft Presidio."""
    
    def __init__(self):
        self.analyzer = None
        self.anonymizer = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
    
    async def _ensure_initialized(self):
        """Initialize Presidio engines with custom patterns."""
        if self._initialized:
            return
            
        async with self._init_lock:
            if self._initialized:
                return
                
            logger.info("Initializing Presidio engines...")
            
            try:
                # Ensure spaCy model is available
                try:
                    import importlib
                    importlib.import_module("en_core_web_sm")
                except ImportError:
                    logger.warning("Downloading spaCy model...")
                    from spacy.cli import download
                    download("en_core_web_sm")
                
                # Configure NLP engine
                provider = NlpEngineProvider(
                    nlp_configuration={
                        "nlp_engine_name": "spacy",
                        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]
                    }
                )
                nlp_engine = provider.create_engine()
                
                # Setup recognizer registry with custom patterns
                registry = RecognizerRegistry()
                registry.load_predefined_recognizers()
                
                # Enhanced SSN pattern
                ssn_pattern = Pattern(
                    name="US_SSN_PATTERN",
                    regex=r"\b(?!000|666|9\d\d)\d{3}[- ]?(?!00)\d{2}[- ]?(?!0000)\d{4}\b",
                    score=0.9,
                )
                registry.add_recognizer(PatternRecognizer(
                    supported_entity="US_SSN",
                    patterns=[ssn_pattern],
                    context=["ssn", "social security", "social-security", "social sec"]
                ))
                
                # Enhanced phone number pattern (E.164)
                phone_pattern = Pattern(
                    name="E164_PHONE", 
                    regex=r"\b\+?[1-9]\d{7,14}\b", 
                    score=0.6
                )
                registry.add_recognizer(PatternRecognizer(
                    supported_entity="PHONE_NUMBER",
                    patterns=[phone_pattern],
                    context=["phone", "mobile", "cell", "contact", "call"]
                ))
                
                # Create analyzer and anonymizer
                self.analyzer = AnalyzerEngine(
                    nlp_engine=nlp_engine, 
                    registry=registry, 
                    supported_languages=["en"]
                )
                self.anonymizer = AnonymizerEngine()
                
                self._initialized = True
                logger.info("Presidio engines initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize Presidio engines: {e}")
                # Set fallback values to prevent None errors
                self.analyzer = None
                self.anonymizer = None
                self._initialized = True  # Mark as initialized to prevent retries
                logger.warning("Presidio initialization failed - firewall will use fallback mode")
    
    async def analyze_pii(
        self, 
        text: str, 
        entities: Optional[List[str]] = None,
        score_threshold: float = 0.30
    ) -> Dict[str, Any]:
        """
        Analyze text for PII using Presidio analyzer.
        
        Args:
            text: Text to analyze
            entities: List of entity types to detect
            score_threshold: Minimum confidence score
            
        Returns:
            Dict containing PII analysis results
        """
        await self._ensure_initialized()
        
        if entities is None:
            entities = ["EMAIL_ADDRESS", "US_SSN", "PHONE_NUMBER", "CREDIT_CARD", "IP_ADDRESS"]
        
        # Check if analyzer is available (fallback mode if initialization failed)
        if self.analyzer is None:
            logger.warning("Presidio analyzer not available - returning fallback PII results")
            return {
                "contains_pii": False,
                "pii_entities": [],
                "confidence_scores": [],
                "detected_types": [],
                "anonymized_text": text,
                "fallback_mode": True
            }
        
        try:
            results = self.analyzer.analyze(
                text=text,
                language="en",
                entities=entities,
                score_threshold=score_threshold
            )
            
            # Filter and format results
            filtered_results = [r for r in results if r.entity_type in entities and r.score >= score_threshold]
            
            findings = [{
                "entity_type": r.entity_type,
                "score": float(round(r.score, 3)),
                "start": r.start,
                "end": r.end,
                "text": text[r.start:r.end]
            } for r in filtered_results]
            
            # Sort and deduplicate findings
            findings = sorted(findings, key=lambda x: (x["start"], -(x["end"] - x["start"])))
            dedup = []
            for f in findings:
                if not any(f["start"] >= d["start"] and f["end"] <= d["end"] for d in dedup):
                    dedup.append(f)
            
            max_confidence = max([f.get("score", 0.0) for f in dedup], default=0.0)
            
            # Create redaction spans
            spans = [(f["start"], f["end"]) for f in dedup]
            redacted_text = self._create_redacted_text(text, spans)
            
            return {
                "contains_pii": bool(dedup),
                "findings": dedup,
                "confidence": max_confidence,
                "redacted_text": redacted_text,
                "spans": spans
            }
            
        except Exception as e:
            logger.error(f"PII analysis failed: {e}")
            return {
                "contains_pii": False,
                "findings": [],
                "confidence": 0.0,
                "redacted_text": text,
                "spans": [],
                "error": str(e)
            }
    
    async def anonymize_pii(
        self,
        text: str,
        analyzer_results: Optional[List] = None,
        operators: Optional[Dict[str, OperatorConfig]] = None
    ) -> Dict[str, Any]:
        """
        Anonymize PII in text using Presidio anonymizer.
        
        Args:
            text: Text to anonymize
            analyzer_results: Pre-computed analyzer results
            operators: Custom anonymization operators
            
        Returns:
            Dict containing anonymized results
        """
        await self._ensure_initialized()
        
        # Check if anonymizer is available (fallback mode if initialization failed)
        if self.anonymizer is None:
            logger.warning("Presidio anonymizer not available - returning original text")
            return {
                "anonymized_text": text,
                "items": [],
                "fallback_mode": True
            }
        
        try:
            # Use default operators if not provided
            if operators is None:
                operators = {
                    "EMAIL_ADDRESS": OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 4, "from_end": True}),
                    "PHONE_NUMBER": OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 4, "from_end": True}),
                    "US_SSN": OperatorConfig("replace", {"new_value": "***-**-****"}),
                    "CREDIT_CARD": OperatorConfig("mask", {"masking_char": "*", "chars_to_mask": 12, "from_end": True}),
                    "IP_ADDRESS": OperatorConfig("replace", {"new_value": "XXX.XXX.XXX.XXX"}),
                    "DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"})
                }
            
            # Get analyzer results if not provided
            if analyzer_results is None:
                pii_analysis = await self.analyze_pii(text)
                # Convert findings to analyzer result format
                from presidio_analyzer import RecognizerResult
                analyzer_results = []
                for finding in pii_analysis.get("findings", []):
                    analyzer_results.append(RecognizerResult(
                        entity_type=finding["entity_type"],
                        start=finding["start"],
                        end=finding["end"],
                        score=finding["score"]
                    ))
            
            # Perform anonymization
            anonymized_result = self.anonymizer.anonymize(
                text=text,
                analyzer_results=analyzer_results,
                operators=operators
            )
            
            return {
                "anonymized_text": anonymized_result.text,
                "items": [
                    {
                        "start": item.start,
                        "end": item.end,
                        "entity_type": item.entity_type,
                        "text": item.text,
                        "operator": item.operator
                    } for item in anonymized_result.items
                ]
            }
            
        except Exception as e:
            logger.error(f"PII anonymization failed: {e}")
            return {
                "anonymized_text": text,
                "items": [],
                "error": str(e)
            }
    
    def _create_redacted_text(self, text: str, spans: List[Tuple[int, int]]) -> str:
        """Create redacted version of text by masking specified spans."""
        if not spans:
            return text
            
        # Merge overlapping spans
        merged_spans = self._merge_spans(spans)
        
        # Build redacted text
        result = []
        prev_end = 0
        
        for start, end in merged_spans:
            # Add text before this span
            result.append(text[prev_end:start])
            # Add masked characters
            result.append("*" * (end - start))
            prev_end = end
        
        # Add remaining text
        result.append(text[prev_end:])
        
        return "".join(result)
    
    def _merge_spans(self, spans: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Merge overlapping spans."""
        if not spans:
            return []
            
        spans = sorted(spans)
        merged = [spans[0]]
        
        for start, end in spans[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        
        return merged


class EnhancedFirewallService:
    """Enhanced firewall service with Presidio integration and comprehensive security scanning."""

    def __init__(self):
        try:
            self.presidio = PresidioEngine()
        except Exception as e:
            logger.error(f"Failed to initialize PresidioEngine: {e}")
            self.presidio = None
        self._environment = os.getenv("ENVIRONMENT", "production").lower()

        # Configuration from environment
        self.firewall_enabled = os.getenv("FIREWALL_ENABLED", "true").lower() == "true"
        self.block_on_violation = os.getenv("FIREWALL_BLOCK_ON_VIOLATION", "true").lower() == "true"
        self.allowlist_topics = self._parse_allowlist_topics(os.getenv("FIREWALL_ALLOWLIST_TOPICS", ""))

        # Enhanced secret patterns from server.py
        self.SECRET_PATTERNS = [
            ("AWS Access Key ID", re.compile(r"(?<![A-Z0-9])(AKIA|ASIA|AIDA|AGPA|ANPA|AROA|AIPA)[A-Z0-9]{16}(?![A-Z0-9])"), 0),
            ("AWS Secret Access Key", re.compile(r"(?i)\baws[_-]?secret[_-]?access[_-]?key\b\s*[:=]\s*([A-Za-z0-9/\+=_-]{40})"), 1),
            ("GitHub Token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"), 0),
            ("Slack Token", re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b"), 0),
            ("Google API Key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), 0),
            ("OpenAI API Key", re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{20,}\b"), 0),
            ("Stripe Live Key", re.compile(r"\b(?:sk_live|rk_live)_[A-Za-z0-9]{24,}\b"), 0),
            ("Twilio Account SID", re.compile(r"\bAC[0-9a-fA-F]{32}\b"), 0),
            ("Twilio Auth Token", re.compile(r"\b[0-9a-fA-F]{32}\b"), 0),
            ("Private Key Block", re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"), 0),
        ]

        # Suspect keys for field-based secret detection
        self.SUSPECT_KEYS = {
            "value", "secret", "token", "key", "api_key", "access_key",
            "client_secret", "private_key", "password", "credential"
        }

        # Translation table for tokenization
        self._table = str.maketrans({c: " " for c in string.punctuation})

        logger.info(f"Enhanced Firewall Service initialized | enabled={self.firewall_enabled} | block_on_violation={self.block_on_violation}")
    
    def _parse_allowlist_topics(self, topics_str: str) -> List[str]:
        """Parse allowlist topics from environment variable."""
        if not topics_str:
            return []
        return [t.strip() for t in topics_str.split(",") if t.strip()]
    
    async def scan_comprehensive(
        self,
        text: str,
        user_id: Optional[str] = None,
        scan_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        domain: Optional[str] = None,
        task_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perform comprehensive security scan including PII, secrets, and toxicity with domain-aware rules.

        Args:
            text: Content to scan
            user_id: User ID for tracking
            scan_id: Custom scan ID
            organization_id: Organization ID for multi-tenant support
            domain: Domain classification for context-aware rules (e.g., "healthcare", "finance")
            task_type: Task type classification (e.g., "question_answering", "coding")

        Returns:
            Comprehensive scan results with domain-aware blocking
        """
        start_time = time.time()
        scan_id = scan_id or f"comprehensive_{int(time.time())}"
        
        if not self.firewall_enabled:
            return {
                "scan_id": scan_id,
                "firewall_enabled": False,
                "safe_to_process": True,
                "violations": [],
                "redacted_text": text,
                "scan_time_ms": 0
            }
        
        try:
            # Run all scans in parallel (pass domain context to allowlist scan)
            pii_task = self.scan_pii(text)
            secrets_task = self.scan_secrets(text)
            toxicity_task = self.scan_toxicity(text)
            allowlist_task = self.scan_allowlist(text, self.allowlist_topics, blocked=None, domain=domain, task_type=task_type)
            
            pii_result, secrets_result, toxicity_result, allowlist_result = await asyncio.gather(
                pii_task, secrets_task, toxicity_task, allowlist_task,
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(pii_result, Exception):
                pii_result = {"contains_violation": False, "error": str(pii_result)}
            if isinstance(secrets_result, Exception):
                secrets_result = {"contains_violation": False, "error": str(secrets_result)}
            if isinstance(toxicity_result, Exception):
                toxicity_result = {"contains_violation": False, "error": str(toxicity_result)}
            if isinstance(allowlist_result, Exception):
                allowlist_result = {"contains_violation": False, "error": str(allowlist_result)}
            
            # Aggregate results
            violations = []
            if pii_result.get("contains_violation"):
                violations.append("pii")
            if secrets_result.get("contains_violation"):
                violations.append("secrets")
            if toxicity_result.get("contains_violation"):
                violations.append("toxicity")
            if allowlist_result.get("contains_violation"):
                violations.append("allowlist")
            
            # Determine if safe to process
            safe_to_process = len(violations) == 0
            if not safe_to_process and not self.block_on_violation:
                safe_to_process = True  # Allow processing despite violations
            
            # Get redacted text (prefer PII redaction as it's most comprehensive)
            redacted_text = text
            if pii_result.get("redacted_text"):
                redacted_text = pii_result["redacted_text"]
            elif secrets_result.get("redacted_text"):
                redacted_text = secrets_result["redacted_text"]
            
            scan_time_ms = int((time.time() - start_time) * 1000)
            
            comprehensive_result = {
                "scan_id": scan_id,
                "firewall_enabled": self.firewall_enabled,
                "block_on_violation": self.block_on_violation,
                "safe_to_process": safe_to_process,
                "violations": violations,
                "redacted_text": redacted_text,
                "scan_time_ms": scan_time_ms,
                "timestamp": datetime.utcnow(),
                
                # Individual scan results
                "pii_scan": pii_result,
                "secrets_scan": secrets_result,
                "toxicity_scan": toxicity_result,
                "allowlist_scan": allowlist_result,
                
                # Summary
                "summary": {
                    "total_violations": len(violations),
                    "highest_risk": self._determine_highest_risk([pii_result, secrets_result, toxicity_result, allowlist_result]),
                    "domain": domain,
                    "task_type": task_type
                }
            }
            
            # Log the scan result
            await self._log_firewall_scan(comprehensive_result, user_id, organization_id)
            
            return comprehensive_result
            
        except Exception as e:
            logger.error(f"Comprehensive firewall scan failed: {e}")
            scan_time_ms = int((time.time() - start_time) * 1000)
            
            error_result = {
                "scan_id": scan_id,
                "firewall_enabled": self.firewall_enabled,
                "safe_to_process": False,
                "violations": ["system_error"],
                "redacted_text": text,
                "scan_time_ms": scan_time_ms,
                "error": str(e)
            }
            
            await self._log_firewall_scan(error_result, user_id, organization_id)
            return error_result
    
    async def scan_pii(self, text: str) -> Dict[str, Any]:
        """Scan text for PII using enhanced Presidio analysis."""
        try:
            # Check if presidio is available
            if self.presidio is None:
                logger.warning("Presidio engine not available - returning fallback PII results")
                return {
                    "scan_type": "pii",
                    "contains_violation": False,
                    "findings": [],
                    "confidence": 0.0,
                    "redacted_text": text,
                    "error": "Presidio engine not initialized"
                }
            
            result = await self.presidio.analyze_pii(text)
            return {
                "scan_type": "pii",
                "contains_violation": result["contains_pii"],
                "findings": result["findings"],
                "confidence": result["confidence"],
                "redacted_text": result["redacted_text"],
                "error": result.get("error")
            }
        except Exception as e:
            logger.error(f"PII scan failed: {e}")
            return {
                "scan_type": "pii",
                "contains_violation": False,
                "findings": [],
                "confidence": 0.0,
                "redacted_text": text,
                "error": str(e)
            }
    
    async def scan_secrets(self, text: str) -> Dict[str, Any]:
        """Scan text for secrets using regex patterns and entropy analysis."""
        try:
            findings = self._detect_secrets_regex(text)
            
            # Create redacted text
            spans = [(f["start"], f["end"]) for f in findings]
            redacted_text = self.presidio._create_redacted_text(text, spans) if self.presidio and hasattr(self.presidio, '_create_redacted_text') else text
            
            return {
                "scan_type": "secrets",
                "contains_violation": bool(findings),
                "findings": findings,
                "redacted_text": redacted_text
            }
        except Exception as e:
            logger.error(f"Secrets scan failed: {e}")
            return {
                "scan_type": "secrets",
                "contains_violation": False,
                "findings": [],
                "redacted_text": text,
                "error": str(e)
            }
    
    async def scan_toxicity(self, text: str) -> Dict[str, Any]:
        """Scan text for toxic content using better-profanity."""
        try:
            # Initialize better-profanity
            from better_profanity import profanity
            profanity.load_censor_words()
            
            # Custom toxic words
            custom_words = {
                "hate", "hateful", "disgusting", "idiot", "stupid", "dumb", "moron", "loser",
                "trash", "garbage", "worthless", "ugly"
            }
            profanity.add_censor_words(list(custom_words))
            
            contains_toxicity = profanity.contains_profanity(text)
            
            return {
                "scan_type": "toxicity",
                "contains_violation": contains_toxicity,
                "flagged": contains_toxicity
            }
        except Exception as e:
            logger.error(f"Toxicity scan failed: {e}")
            return {
                "scan_type": "toxicity",
                "contains_violation": False,
                "flagged": False,
                "error": str(e)
            }
    
    async def scan_allowlist(self, text: str, topics: List[str], blocked: Optional[List[str]] = None, domain: Optional[str] = None, task_type: Optional[str] = None) -> Dict[str, Any]:
        """Check if text matches allowlist topics and blocklist items, including domain-aware database rules."""
        try:
            lowered = (text or "").lower()

            # Load database rules with domain awareness
            db_allow_rules = []
            db_block_rules = []
            domain_allow_rules = []
            domain_pattern_block_rules = []
            domain_blanket_block_rules = []

            try:
                # Import here to avoid circular imports
                from ..models.firewall_rules import FirewallRule, RuleType
                from sqlalchemy import select, or_, and_, func

                async for db in get_db():
                    # Get general rules (no domain scope)
                    general_allow_query = select(FirewallRule).where(
                        and_(
                            FirewallRule.rule_type == RuleType.ALLOW,
                            or_(
                                FirewallRule.domain_scope.is_(None),
                                FirewallRule.domain_scope == ""
                            )
                        )
                    ).order_by(FirewallRule.priority.desc())

                    general_block_query = select(FirewallRule).where(
                        and_(
                            FirewallRule.rule_type == RuleType.BLOCK,
                            or_(
                                FirewallRule.domain_scope.is_(None),
                                FirewallRule.domain_scope == ""
                            )
                        )
                    ).order_by(FirewallRule.priority.desc())

                    general_allow_result = await db.execute(general_allow_query)
                    general_block_result = await db.execute(general_block_query)

                    general_allow_rules = general_allow_result.scalars().all()
                    general_block_rules = general_block_result.scalars().all()

                    db_allow_rules = [rule.pattern for rule in general_allow_rules]
                    db_block_rules = [rule.pattern for rule in general_block_rules]

                    # Get domain-specific rules if domain is provided
                    if domain:
                        # Rules that match the specific domain or have it in applies_to_domains
                        # Using PostgreSQL JSONB contains operator @>
                        domain_allow_query = select(FirewallRule).where(
                            and_(
                                FirewallRule.rule_type == RuleType.ALLOW,
                                or_(
                                    func.lower(FirewallRule.domain_scope) == domain.lower(),
                                    FirewallRule.applies_to_domains.op('@>')([domain])  # PostgreSQL JSONB contains
                                )
                            )
                        ).order_by(FirewallRule.priority.desc())

                        domain_block_query = select(FirewallRule).where(
                            and_(
                                FirewallRule.rule_type == RuleType.BLOCK,
                                or_(
                                    func.lower(FirewallRule.domain_scope) == domain.lower(),
                                    FirewallRule.applies_to_domains.op('@>')([domain])  # PostgreSQL JSONB contains
                                )
                            )
                        ).order_by(FirewallRule.priority.desc())

                        domain_allow_result = await db.execute(domain_allow_query)
                        domain_block_result = await db.execute(domain_block_query)

                        domain_allow_rules_obj = domain_allow_result.scalars().all()
                        domain_block_rules_obj = domain_block_result.scalars().all()

                        # Separate domain rules into blanket blocking and pattern-based blocking using rule_category
                        domain_blanket_block_rules = [rule for rule in domain_block_rules_obj if rule.rule_category == "blanket_domain"]
                        domain_pattern_block_rules = [rule.pattern for rule in domain_block_rules_obj if rule.rule_category == "keyword" or (rule.rule_category is None and rule.pattern and rule.pattern.strip() != "")]
                        domain_allow_rules = [rule.pattern for rule in domain_allow_rules_obj]

                        logger.info(f"Loaded domain-specific rules for '{domain}': {len(domain_allow_rules)} allow, {len(domain_pattern_block_rules)} pattern-block, {len(domain_blanket_block_rules)} blanket-block")

                    logger.info(f"Loaded general rules: {len(db_allow_rules)} allow, {len(db_block_rules)} block")
                    break  # Only need one iteration
            except Exception as e:
                logger.warning(f"Failed to load database firewall rules: {e}")

            # Combine rules with domain-specific rules taking precedence
            # Domain-specific rules are evaluated first due to higher priority
            if domain:
                # 1. Check for blanket domain blocking first (highest priority)
                if domain_blanket_block_rules:
                    logger.info(f"🚫 BLANKET DOMAIN BLOCK: Blocking all '{domain}' domain content due to blanket rule")
                    return {
                        "scan_type": "allowlist",
                        "contains_violation": True,
                        "allowed": False,
                        "matched_topic": None,
                        "blocked_match": f"domain:{domain}",
                        "domain_rule": True,
                        "domain": domain,
                        "block_type": "blanket_domain"
                    }

                # 2. Apply domain-specific pattern block rules
                for b in domain_pattern_block_rules:
                    if (b or "").lower() in lowered:
                        logger.info(f"🚫 PATTERN DOMAIN BLOCK: Blocking pattern '{b}' in domain '{domain}'")
                        return {
                            "scan_type": "allowlist",
                            "contains_violation": True,
                            "allowed": False,
                            "matched_topic": None,
                            "blocked_match": b,
                            "domain_rule": True,
                            "domain": domain,
                            "block_type": "pattern_domain"
                        }

            # Then apply general block rules (environment + database)
            all_blocked = (blocked or []) + db_block_rules
            for b in all_blocked:
                if (b or "").lower() in lowered:
                    return {
                        "scan_type": "allowlist",
                        "contains_violation": True,
                        "allowed": False,
                        "matched_topic": None,
                        "blocked_match": b,
                        "domain_rule": False
                    }

            # Check domain-specific allow rules if applicable
            if domain and domain_allow_rules:
                for topic in domain_allow_rules:
                    if (topic or "").lower() in lowered:
                        return {
                            "scan_type": "allowlist",
                            "contains_violation": False,
                            "allowed": True,
                            "matched_topic": topic,
                            "blocked_match": None,
                            "domain_rule": True,
                            "domain": domain,
                            "safe_to_process": True
                        }

            # Combine environment and general database allowlist
            all_topics = (topics or []) + db_allow_rules

            # Then check allowlist (environment + database)
            matched_topic = None
            for topic in all_topics:
                if (topic or "").lower() in lowered:
                    matched_topic = topic
                    break

            # If no allowlist rules exist, default to allowing content (blocklist-only mode)
            # If allowlist rules exist, content must match one to be allowed (allowlist mode)
            if not all_topics and not domain_allow_rules:
                # No allowlist rules: allow everything that's not explicitly blocked
                allowed = True
                logger.info(f"No allowlist rules found - allowing content in blocklist-only mode (domain: {domain})")
            else:
                # Allowlist rules exist: content must match one to be allowed
                allowed = bool(matched_topic)
                logger.info(f"Allowlist rules found - using allowlist mode, matched: {matched_topic} (domain: {domain})")

            return {
                "scan_type": "allowlist",
                "contains_violation": not allowed,
                "allowed": allowed,
                "matched_topic": matched_topic,
                "blocked_match": None,
                "safe_to_process": allowed,
                "domain": domain,
                "domain_rule": False
            }
        except Exception as e:
            logger.error(f"Allowlist scan failed: {e}")
            return {
                "scan_type": "allowlist",
                "contains_violation": True,  # Fail closed for allowlist
                "allowed": False,
                "matched_topic": None,
                "blocked_match": None,
                "error": str(e)
            }
    
    def _detect_secrets_regex(self, text: str, entropy_threshold: float = 3.5) -> List[Dict[str, Any]]:
        """Detect secrets using regex patterns and entropy analysis."""
        findings = []

        # Use enhanced SECRET_PATTERNS from server.py
        for name, pattern, grp in self.SECRET_PATTERNS:
            for match in pattern.finditer(text):
                full_match = match.group(grp) if (grp and (match.lastindex or 0) >= grp) else match.group(0)
                # Normalize before entropy calculation to include hyphens/underscores
                entropy = self._calculate_entropy(re.sub(r'[^A-Za-z0-9/\+=]', '', full_match))

                findings.append({
                    "detector": name,
                    "redacted": self._redact_secret(full_match),
                    "entropy": round(entropy, 3),
                    "start": match.start(),
                    "end": match.end()
                })

        # Broadened high-entropy string detection to include - and _
        for match in re.finditer(r"\b[A-Za-z0-9/\+=_-]{20,}\b", text):
            s = match.group(0)
            s_norm = re.sub(r"[^A-Za-z0-9/\+=]", "", s)
            entropy = self._calculate_entropy(s_norm)

            # Check if already detected
            already_detected = any(d["start"] <= match.start() <= d["end"] for d in findings)

            if entropy >= entropy_threshold and not already_detected:
                findings.append({
                    "detector": "High-Entropy String",
                    "redacted": self._redact_secret(s),
                    "entropy": round(entropy, 3),
                    "start": match.start(),
                    "end": match.end()
                })

        # Sort and deduplicate
        findings.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
        dedup = []
        for f in findings:
            if not any(f["start"] >= d["start"] and f["end"] <= d["end"] for d in dedup):
                dedup.append(f)

        return dedup
    
    def _calculate_entropy(self, text: str) -> float:
        """Calculate Shannon entropy of text."""
        if not text:
            return 0.0

        # Use frequency counting similar to server.py
        freq = {ch: text.count(ch) for ch in set(text)}
        return -sum((c/len(text))*math.log2(c/len(text)) for c in freq.values())
    
    def _redact_secret(self, secret: str) -> str:
        """Redact secret by showing first 4 and last 4 characters."""
        if not secret:
            return ""
        if len(secret) <= 8:
            return "*" * len(secret)
        return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]
    
    def _determine_highest_risk(self, scan_results: List[Dict[str, Any]]) -> str:
        """Determine highest risk level from scan results."""
        risk_levels = ["low", "medium", "high", "critical"]
        max_risk = 0
        
        for result in scan_results:
            if result.get("contains_violation"):
                # Simple risk assessment based on scan type
                scan_type = result.get("scan_type", "")
                if scan_type in ["secrets", "pii"]:
                    max_risk = max(max_risk, 3)  # critical
                elif scan_type == "toxicity":
                    max_risk = max(max_risk, 2)  # high
                else:
                    max_risk = max(max_risk, 1)  # medium
        
        return risk_levels[max_risk]
    
    async def _log_firewall_scan(
        self,
        result: Dict[str, Any],
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ):
        """Log firewall scan result to database."""
        try:
            from uuid import uuid4
            async for db in get_db():
                # Extract block type information from allowlist scan
                allowlist_scan = result.get("allowlist_scan", {})
                block_type = allowlist_scan.get("block_type")

                log_entry = FirewallLog(
                    log_id=f"fwlog_{uuid4().hex[:8]}_{organization_id or 'org_001'}",
                    organization_id=organization_id or "org_001",
                    user_id=user_id or "anonymous",
                    request_id=result.get("scan_id"),
                    event_type="blocked" if not result.get("safe_to_process", True) else "allowed",
                    severity="medium" if not result.get("safe_to_process", True) else "low",
                    rule_category="domain_firewall" if allowlist_scan.get("domain_rule") else "general",
                    block_type=block_type,
                    action_taken="block" if not result.get("safe_to_process", True) else "allow",
                    reason=f"Violations: {', '.join(result.get('violations', []))}" if result.get('violations') else "Content allowed",
                    blocked_match=allowlist_scan.get("blocked_match"),
                    rule_type=allowlist_scan.get("rule_type"),
                    processing_time_ms=result.get("scan_time_ms", 0),
                    detected_entities=result.get("pii_scan", {}).get("findings", [])
                )
                db.add(log_entry)
                await db.commit()
                break
        except Exception as e:
            logger.error(f"Failed to log firewall scan: {e}")
    
    async def anonymize_text(self, text: str) -> Dict[str, Any]:
        """Anonymize PII in text using Presidio anonymizer."""
        if self.presidio is None:
            logger.warning("Presidio engine not available - returning original text")
            return {
                "anonymized_text": text,
                "items": [],
                "fallback_mode": True
            }
        return await self.presidio.anonymize_pii(text)

    def _allow_local(self, text: str, topics: Optional[List[str]], blocked: Optional[List[str]] = None) -> Dict[str, Any]:
        """Local allowlist/blocklist check implementation."""
        lowered = (text or "").lower()

        # First check blocklist
        if blocked:
            for b in blocked:
                if (b or "").lower() in lowered:
                    return {"allowed": False, "blocked_match": b}

        # Then check allowlist
        matched = None
        for t in (topics or []):
            if (t or "").lower() in lowered:
                matched = t
                break

        return {"allowed": bool(matched), "matched_topic": matched}

    def _simple_tokens(self, text: str) -> List[str]:
        """Simple tokenization using punctuation translation."""
        return (text or "").translate(self._table).lower().split()

    def is_enabled(self) -> bool:
        """Check if firewall is enabled."""
        return self.firewall_enabled


# Global service instance
_firewall_service = None

def get_firewall_service() -> EnhancedFirewallService:
    """Get or create the global firewall service instance."""
    global _firewall_service
    if _firewall_service is None:
        _firewall_service = EnhancedFirewallService()
    return _firewall_service
"""
Firewall and Security Scanning API Router
=========================================

Provides endpoints for security scanning including PII detection, 
secrets detection, and toxicity detection using Enhanced Firewall Service.
"""

import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
import logging

# Import the enhanced firewall service
from ..services.firewall_service import get_firewall_service, EnhancedFirewallService
# Import database and models
from ..db.database import get_db
from ..models.firewall_rules import FirewallRule, RuleType
# Import logging
from ..core.logging_config import get_logger

router = APIRouter(prefix="/api/v1/firewall", tags=["firewall", "security"])


class ScanRequest(BaseModel):
    """Request model for security scanning"""
    content: str = Field(..., description="Content to scan for security issues")
    user_id: Optional[str] = Field(None, description="User ID for tracking")
    scan_id: Optional[str] = Field(None, description="Custom scan ID")


class ScanResult(BaseModel):
    """Base result model for security scans"""
    scan_id: str
    content_length: int
    scan_type: str
    risk_level: str  # "low", "medium", "high", "critical"
    issues_found: int
    scan_time_ms: int
    timestamp: datetime


class PIIScanResult(ScanResult):
    """Result model for PII scanning"""
    detected_pii: List[Dict[str, Any]]
    pii_types: List[str]
    confidence_score: float


class SecretsScanResult(ScanResult):
    """Result model for secrets scanning"""
    detected_secrets: List[Dict[str, Any]]
    secret_types: List[str]
    entropy_analysis: Dict[str, float]


class ToxicityScanResult(ScanResult):
    """Result model for toxicity scanning"""
    toxicity_score: float
    detected_categories: List[str]
    flagged_phrases: List[Dict[str, Any]]


class AllowlistRequest(BaseModel):
    """Request model for allowlist scanning"""
    text: str = Field(..., description="Text to scan against allowlist rules")
    topics: Optional[List[str]] = Field(None, description="Allowed topics/patterns")
    blocked: Optional[List[str]] = Field(None, description="Blocked patterns")
    user_id: Optional[str] = Field(None, description="User ID for tracking")
    scan_id: Optional[str] = Field(None, description="Custom scan ID")


class FirewallConfigRequest(BaseModel):
    """Request model for firewall configuration updates"""
    pii_detection_enabled: Optional[bool] = Field(None, description="Enable/disable PII detection")
    secrets_detection_enabled: Optional[bool] = Field(None, description="Enable/disable secrets detection")
    toxicity_detection_enabled: Optional[bool] = Field(None, description="Enable/disable toxicity detection")
    allowlist_enabled: Optional[bool] = Field(None, description="Enable/disable allowlist checking")
    blocklist_enabled: Optional[bool] = Field(None, description="Enable/disable blocklist checking")


class FirewallRuleRequest(BaseModel):
    """Request model for creating firewall rules"""
    rule_type: str = Field(..., description="Rule type: 'allow' or 'block'", pattern="^(allow|block)$")
    pattern: Optional[str] = Field(None, description="Pattern to match (optional for blanket domain rules)", max_length=500)
    description: Optional[str] = Field(None, description="Description of the rule")
    domain_scope: Optional[str] = Field(None, description="Domain for context-aware rule (e.g., 'healthcare', 'finance')")
    applies_to_domains: Optional[List[str]] = Field(None, description="List of domains this rule applies to")
    priority: Optional[int] = Field(0, description="Rule priority (higher = evaluated first)")
    rule_category: Optional[str] = Field(None, description="Rule category: 'blanket_domain' or 'keyword'", pattern="^(blanket_domain|keyword)$")


class FirewallRuleResponse(BaseModel):
    """Response model for firewall rules"""
    id: str
    org_id: str
    rule_type: str
    pattern: Optional[str]
    description: Optional[str]
    domain_scope: Optional[str]
    applies_to_domains: Optional[List[str]]
    priority: int
    rule_category: Optional[str]
    created_at: datetime
    updated_at: datetime


class DomainRuleTestRequest(BaseModel):
    """Request model for testing domain-specific rules"""
    text: str = Field(..., description="Text to test against rules")
    domain: str = Field(..., description="Domain context for the test")
    task_type: Optional[str] = Field(None, description="Task type for additional context")


def get_firewall() -> EnhancedFirewallService:
    """Dependency to get enhanced firewall service instance"""
    try:
        firewall = get_firewall_service()
        return firewall
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Enhanced firewall service initialization failed: {str(e)}")


# Legacy patterns and functions removed - now using Enhanced Firewall Service with Presidio


@router.post("/scan/pii", response_model=PIIScanResult)
async def scan_pii(
    request: ScanRequest,
    firewall: EnhancedFirewallService = Depends(get_firewall)
):
    """
    Scan content for Personally Identifiable Information (PII) using Enhanced Firewall Service.
    
    Uses Microsoft Presidio for advanced PII detection including:
    - Email addresses
    - Social Security Numbers
    - Phone numbers
    - Credit card numbers
    - IP addresses
    - Driver's license numbers
    - And many more entity types
    
    Args:
        request: Content to scan for PII
        firewall: Enhanced firewall service instance
        
    Returns:
        PIIScanResult: Detailed PII scan results with Presidio confidence scores
    """
    start_time = time.time()
    scan_id = request.scan_id or f"pii_scan_{int(time.time())}"
    
    try:
        # Use enhanced firewall service for PII detection
        scan_result = await firewall.scan_pii(request.content)
        
        # Extract data from enhanced service result
        detected_pii = scan_result.get("detected_entities", [])
        pii_types = list(set(item.get("entity_type", "unknown") for item in detected_pii))
        confidence_score = scan_result.get("average_confidence", 0.0)
        
        # Map enhanced service risk to API risk levels
        risk_mapping = {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}
        risk_level = risk_mapping.get(scan_result.get("risk_level", "low"), "low")
        
        scan_time_ms = int((time.time() - start_time) * 1000)
        
        # Format detected PII for API response
        formatted_pii = []
        for entity in detected_pii:
            formatted_pii.append({
                "type": entity.get("entity_type", "unknown"),
                "description": f"PII entity: {entity.get('entity_type', 'unknown')}",
                "value": entity.get("text", ""),
                "start_pos": entity.get("start", 0),
                "end_pos": entity.get("end", 0),
                "confidence": entity.get("score", 0.0)
            })
        
        return PIIScanResult(
            scan_id=scan_id,
            content_length=len(request.content),
            scan_type="pii",
            risk_level=risk_level,
            issues_found=len(formatted_pii),
            scan_time_ms=scan_time_ms,
            timestamp=datetime.now(),
            detected_pii=formatted_pii,
            pii_types=pii_types,
            confidence_score=confidence_score
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhanced PII scan failed: {str(e)}")


@router.post("/scan/secrets", response_model=SecretsScanResult)
async def scan_secrets(
    request: ScanRequest,
    firewall: EnhancedFirewallService = Depends(get_firewall)
):
    """
    Scan content for secrets and sensitive information using Enhanced Firewall Service.
    
    Detects:
    - API keys
    - AWS access keys
    - GitHub tokens
    - JWT tokens
    - Passwords
    - Private keys
    
    Also performs entropy analysis to detect potential secrets.
    
    Args:
        request: Content to scan for secrets
        firewall: Enhanced firewall service instance
        
    Returns:
        SecretsScanResult: Detailed secrets scan results with enhanced detection
    """
    start_time = time.time()
    scan_id = request.scan_id or f"secrets_scan_{int(time.time())}"
    
    try:
        # Use enhanced firewall service for secrets detection
        scan_result = await firewall.scan_secrets(request.content)
        
        # Extract data from enhanced service result
        detected_secrets = scan_result.get("detected_secrets", [])
        secret_types = list(set(item.get("type", "unknown") for item in detected_secrets))
        entropy_analysis = scan_result.get("entropy_analysis", {})
        
        # Map enhanced service risk to API risk levels
        risk_mapping = {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}
        risk_level = risk_mapping.get(scan_result.get("risk_level", "low"), "low")
        
        scan_time_ms = int((time.time() - start_time) * 1000)
        
        return SecretsScanResult(
            scan_id=scan_id,
            content_length=len(request.content),
            scan_type="secrets",
            risk_level=risk_level,
            issues_found=len(detected_secrets),
            scan_time_ms=scan_time_ms,
            timestamp=datetime.now(),
            detected_secrets=detected_secrets,
            secret_types=secret_types,
            entropy_analysis=entropy_analysis
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhanced secrets scan failed: {str(e)}")


@router.post("/scan/toxicity", response_model=ToxicityScanResult)
async def scan_toxicity(
    request: ScanRequest,
    firewall: EnhancedFirewallService = Depends(get_firewall)
):
    """
    Scan content for toxic, harmful, or inappropriate content using Enhanced Firewall Service.
    
    Uses better-profanity for enhanced detection of:
    - Hate speech
    - Harassment
    - Violence
    - Profanity
    - Discrimination
    
    Args:
        request: Content to scan for toxicity
        firewall: Enhanced firewall service instance
        
    Returns:
        ToxicityScanResult: Detailed toxicity scan results with enhanced detection
    """
    start_time = time.time()
    scan_id = request.scan_id or f"toxicity_scan_{int(time.time())}"
    
    try:
        # Use enhanced firewall service for toxicity detection
        scan_result = await firewall.scan_toxicity(request.content)
        
        # Extract data from enhanced service result
        toxicity_score = scan_result.get("toxicity_score", 0.0)
        detected_categories = scan_result.get("categories", [])
        flagged_phrases = scan_result.get("flagged_content", [])
        
        # Map enhanced service risk to API risk levels
        risk_mapping = {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}
        risk_level = risk_mapping.get(scan_result.get("risk_level", "low"), "low")
        
        scan_time_ms = int((time.time() - start_time) * 1000)
        
        return ToxicityScanResult(
            scan_id=scan_id,
            content_length=len(request.content),
            scan_type="toxicity",
            risk_level=risk_level,
            issues_found=len(flagged_phrases),
            scan_time_ms=scan_time_ms,
            timestamp=datetime.now(),
            toxicity_score=toxicity_score,
            detected_categories=detected_categories,
            flagged_phrases=flagged_phrases
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhanced toxicity scan failed: {str(e)}")


@router.post("/scan/comprehensive")
async def comprehensive_scan(
    request: ScanRequest,
    domain: Optional[str] = Query(None, description="Domain context for domain-aware rules"),
    task_type: Optional[str] = Query(None, description="Task type for additional context"),
    firewall: EnhancedFirewallService = Depends(get_firewall),
    db: AsyncSession = Depends(get_db)
):
    """
    Perform a comprehensive security scan using Enhanced Firewall Service.

    Includes PII, secrets, toxicity detection, and domain-aware blocklist checking in a single optimized scan.

    Args:
        request: Content to scan
        domain: Optional domain context for domain-aware rules
        task_type: Optional task type for additional context
        firewall: Enhanced firewall service instance
        db: Database session for blocklist checking

    Returns:
        Combined results from all enhanced scan types including domain-aware blocklist check
    """
    start_time = time.time()
    scan_id = request.scan_id or f"comprehensive_scan_{int(time.time())}"

    try:
        # Use enhanced firewall service comprehensive scan with domain context
        scan_result = await firewall.scan_comprehensive(
            text=request.content,
            user_id=request.user_id,
            scan_id=scan_id,
            domain=domain,
            task_type=task_type
        )

        # Perform blocklist check against database rules
        blocklist_result = await _check_blocklist(request.content, db)

        # Extract overall data from enhanced service result
        overall_risk = scan_result.get("overall_risk_level", "low")
        total_issues = scan_result.get("total_violations", 0)

        # Increase risk level if blocklist violations found
        if blocklist_result["blocked"]:
            total_issues += len(blocklist_result["matched_rules"])
            if overall_risk == "low":
                overall_risk = "medium"
            elif overall_risk == "medium":
                overall_risk = "high"

        scan_time_ms = int((time.time() - start_time) * 1000)

        return {
            "scan_id": scan_id,
            "scan_type": "comprehensive",
            "content_length": len(request.content),
            "overall_risk_level": overall_risk,
            "total_issues_found": total_issues,
            "scan_time_ms": scan_time_ms,
            "timestamp": datetime.now(),

            # Enhanced service results
            "scan_results": scan_result,

            # Blocklist results
            "blocklist_check": blocklist_result,

            # Summary
            "summary": {
                "pii_detected": scan_result.get("pii_detected", False),
                "secrets_detected": scan_result.get("secrets_detected", False),
                "toxicity_detected": scan_result.get("toxicity_detected", False),
                "blocklist_violated": blocklist_result["blocked"],
                "highest_risk_category": overall_risk,
                "action_taken": scan_result.get("action", "analyzed"),
                "passed_firewall": scan_result.get("allowed", True) and not blocklist_result["blocked"]
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enhanced comprehensive scan failed: {str(e)}")


@router.post("/scan/allow")
async def scan_allow(
    request: AllowlistRequest,
    firewall: EnhancedFirewallService = Depends(get_firewall),
    db: AsyncSession = Depends(get_db)
):
    """
    Scan content against allowlist and blocklist patterns.

    This endpoint replicates the /scan/allow functionality from server.py,
    checking content against allowed topics and blocked patterns.

    Args:
        request: Allowlist scan request with text, topics, and blocked patterns
        firewall: Enhanced firewall service instance
        db: Database session for rule checking

    Returns:
        Allowlist scan results with matched topics and blocked patterns
    """
    logger = get_logger(__name__)
    start_time = time.time()
    scan_id = request.scan_id or f"allow_scan_{int(time.time())}"

    try:
        text = request.text or ""

        # Perform local allowlist/blocklist check
        local_result = await _allow_local(text, request.topics, request.blocked, db)

        # Extract results
        allowed = local_result.get("allowed", False)
        matched_topic = local_result.get("matched_topic")
        blocked_match = local_result.get("blocked_match")

        scan_time_ms = int((time.time() - start_time) * 1000)

        return {
            "scan_id": scan_id,
            "scan_type": "allowlist",
            "content_length": len(text),
            "scan_time_ms": scan_time_ms,
            "timestamp": datetime.now(),
            "endpoint": "allow",
            "local": local_result,
            "allowed": bool(allowed),
            "matched_topic": matched_topic,
            "blocked_match": blocked_match,
            "strategy": {
                "use_llm": False,  # Currently using local check only
                "confidence": 1.0 if allowed else 0.0
            }
        }

    except Exception as e:
        logger.error(f"Allowlist scan failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Allowlist scan failed: {str(e)}")


@router.put("/config")
async def update_firewall_config(
    config: FirewallConfigRequest,
    firewall: EnhancedFirewallService = Depends(get_firewall)
):
    """
    Update firewall configuration to enable/disable various scanning features.

    Args:
        config: Configuration updates for firewall features
        firewall: Enhanced firewall service instance

    Returns:
        Updated configuration status
    """
    logger = get_logger(__name__)

    try:
        # Update configuration (this would ideally be stored in database/config)
        updated_config = {}

        if config.pii_detection_enabled is not None:
            updated_config["pii_detection_enabled"] = config.pii_detection_enabled

        if config.secrets_detection_enabled is not None:
            updated_config["secrets_detection_enabled"] = config.secrets_detection_enabled

        if config.toxicity_detection_enabled is not None:
            updated_config["toxicity_detection_enabled"] = config.toxicity_detection_enabled

        if config.allowlist_enabled is not None:
            updated_config["allowlist_enabled"] = config.allowlist_enabled

        if config.blocklist_enabled is not None:
            updated_config["blocklist_enabled"] = config.blocklist_enabled

        logger.info(f"Firewall configuration updated: {updated_config}")

        return {
            "status": "success",
            "message": "Firewall configuration updated successfully",
            "updated_config": updated_config,
            "timestamp": datetime.now()
        }

    except Exception as e:
        logger.error(f"Failed to update firewall configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


@router.get("/rules")
async def get_firewall_rules(
    rule_type: Optional[str] = Query(None, description="Filter by rule type: 'allow' or 'block'"),
    limit: int = Query(100, description="Maximum number of rules to return"),
    offset: int = Query(0, description="Number of rules to skip"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve firewall rules from database.

    Args:
        rule_type: Optional filter by rule type
        limit: Maximum number of rules to return
        offset: Number of rules to skip for pagination
        db: Database session

    Returns:
        List of firewall rules
    """
    logger = get_logger(__name__)

    try:
        # Build query
        query = select(FirewallRule)

        if rule_type:
            if rule_type not in ["allow", "block"]:
                raise HTTPException(status_code=400, detail="rule_type must be 'allow' or 'block'")
            query = query.where(FirewallRule.rule_type == RuleType(rule_type))

        # Add pagination
        query = query.offset(offset).limit(limit)

        # Execute query
        result = await db.execute(query)
        rules = result.scalars().all()

        # Convert to response format with domain fields
        rules_data = [
            FirewallRuleResponse(
                id=rule.id,
                org_id=rule.org_id,
                rule_type=rule.rule_type.value,
                pattern=rule.pattern,
                description=rule.description,
                domain_scope=rule.domain_scope,
                applies_to_domains=rule.applies_to_domains,
                priority=rule.priority,
                rule_category=rule.rule_category,
                created_at=rule.created_at,
                updated_at=rule.updated_at
            )
            for rule in rules
        ]

        return {
            "rules": rules_data,
            "total": len(rules_data),
            "offset": offset,
            "limit": limit
        }

    except Exception as e:
        logger.error(f"Failed to get firewall rules: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get firewall rules: {str(e)}")


@router.post("/rules")
async def create_firewall_rule(
    rule_request: FirewallRuleRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new firewall rule.

    Args:
        rule_request: Firewall rule creation request
        db: Database session

    Returns:
        Created firewall rule
    """
    logger = get_logger(__name__)

    try:
        # Generate unique rule ID
        rule_id = f"rule_{uuid4().hex[:8]}_org_001"  # Using default org for now

        # Validate rule based on category
        if rule_request.rule_category == "blanket_domain":
            if not rule_request.domain_scope and not rule_request.applies_to_domains:
                raise HTTPException(status_code=400, detail="Blanket domain rules must specify domain_scope or applies_to_domains")
            # For blanket domain rules, pattern should be empty or a placeholder
            pattern = rule_request.pattern or ""
        elif rule_request.rule_category == "keyword":
            if not rule_request.pattern:
                raise HTTPException(status_code=400, detail="Keyword rules must specify a pattern")
            pattern = rule_request.pattern
        else:
            # Legacy rules or unspecified category
            if not rule_request.pattern:
                raise HTTPException(status_code=400, detail="Pattern is required for legacy rules")
            pattern = rule_request.pattern

        # Create new rule with domain support
        new_rule = FirewallRule(
            id=rule_id,
            org_id="org_001",  # Using default org for now
            rule_type=RuleType(rule_request.rule_type),
            pattern=pattern,
            description=rule_request.description,
            domain_scope=rule_request.domain_scope,
            applies_to_domains=rule_request.applies_to_domains,
            priority=rule_request.priority or 0,
            rule_category=rule_request.rule_category
        )

        # Add to database
        db.add(new_rule)
        await db.commit()
        await db.refresh(new_rule)

        logger.info(f"Created firewall rule: {rule_id}")

        return FirewallRuleResponse(
            id=new_rule.id,
            org_id=new_rule.org_id,
            rule_type=new_rule.rule_type.value,
            pattern=new_rule.pattern,
            description=new_rule.description,
            domain_scope=new_rule.domain_scope,
            applies_to_domains=new_rule.applies_to_domains,
            priority=new_rule.priority,
            rule_category=new_rule.rule_category,
            created_at=new_rule.created_at,
            updated_at=new_rule.updated_at
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create firewall rule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create firewall rule: {str(e)}")


@router.delete("/rules/{rule_id}")
async def delete_firewall_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a firewall rule.

    Args:
        rule_id: ID of the rule to delete
        db: Database session

    Returns:
        Deletion confirmation
    """
    logger = get_logger(__name__)

    try:
        logger.info(f"DELETE request received for rule_id: {rule_id}")

        # Check if rule exists
        query = select(FirewallRule).where(FirewallRule.id == rule_id)
        result = await db.execute(query)
        rule = result.scalar_one_or_none()

        if not rule:
            logger.warning(f"Rule not found for deletion: {rule_id}")
            raise HTTPException(status_code=404, detail=f"Firewall rule not found: {rule_id}")

        logger.info(f"Rule found: {rule.pattern} ({rule.rule_type.value})")

        # Delete rule
        delete_query = delete(FirewallRule).where(FirewallRule.id == rule_id)
        delete_result = await db.execute(delete_query)
        rows_affected = delete_result.rowcount
        await db.commit()

        logger.info(f"Deleted firewall rule: {rule_id}, rows_affected: {rows_affected}")

        # Verify deletion by checking if rule still exists
        verify_query = select(FirewallRule).where(FirewallRule.id == rule_id)
        verify_result = await db.execute(verify_query)
        remaining_rule = verify_result.scalar_one_or_none()

        if remaining_rule:
            logger.error(f"Rule still exists after deletion: {rule_id}")
        else:
            logger.info(f"Deletion verified: rule {rule_id} no longer exists in database")

        return {
            "status": "success",
            "message": f"Firewall rule {rule_id} deleted successfully",
            "deleted_rule_id": rule_id,
            "rows_affected": rows_affected,
            "timestamp": datetime.now()
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete firewall rule {rule_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete firewall rule: {str(e)}")


@router.get("/domain-rules")
async def get_domain_rules(
    domain: Optional[str] = Query(None, description="Filter by domain scope"),
    rule_type: Optional[str] = Query(None, description="Filter by rule type: 'allow' or 'block'"),
    limit: int = Query(100, description="Maximum number of rules to return"),
    offset: int = Query(0, description="Number of rules to skip"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve domain-specific firewall rules from database.

    This endpoint is designed for the UI to display and manage domain-specific rules
    in the same way as the existing allow/block list functionality.

    Args:
        domain: Optional filter by domain scope
        rule_type: Optional filter by rule type
        limit: Maximum number of rules to return
        offset: Number of rules to skip for pagination
        db: Database session

    Returns:
        List of domain-specific firewall rules
    """
    logger = get_logger(__name__)

    try:
        from sqlalchemy import or_, and_

        # Build query for domain rules
        query = select(FirewallRule)

        # Filter by domain if specified
        if domain:
            # Using PostgreSQL JSONB contains operator @>
            query = query.where(
                or_(
                    FirewallRule.domain_scope == domain,
                    FirewallRule.applies_to_domains.op('@>')([domain])  # PostgreSQL JSONB contains
                )
            )
        else:
            # Get all rules that have domain scope
            query = query.where(
                or_(
                    FirewallRule.domain_scope.isnot(None),
                    FirewallRule.applies_to_domains.isnot(None)
                )
            )

        # Filter by rule type if specified
        if rule_type:
            if rule_type not in ["allow", "block"]:
                raise HTTPException(status_code=400, detail="rule_type must be 'allow' or 'block'")
            query = query.where(FirewallRule.rule_type == RuleType(rule_type))

        # Order by priority (highest first) and then by creation date
        query = query.order_by(FirewallRule.priority.desc(), FirewallRule.created_at.desc())

        # Add pagination
        query = query.offset(offset).limit(limit)

        # Execute query
        result = await db.execute(query)
        rules = result.scalars().all()

        # Convert to response format
        rules_data = [
            {
                "id": rule.id,
                "org_id": rule.org_id,
                "rule_type": rule.rule_type.value,
                "pattern": rule.pattern,
                "description": rule.description,
                "domain_scope": rule.domain_scope,
                "applies_to_domains": rule.applies_to_domains,
                "priority": rule.priority,
                "rule_category": rule.rule_category,
                "created_at": rule.created_at.isoformat(),
                "updated_at": rule.updated_at.isoformat()
            }
            for rule in rules
        ]

        return {
            "rules": rules_data,
            "total": len(rules_data),
            "offset": offset,
            "limit": limit,
            "domain_filter": domain
        }

    except Exception as e:
        logger.error(f"Failed to get domain rules: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get domain rules: {str(e)}")


@router.post("/domain-rules")
async def create_domain_rule(
    rule_request: FirewallRuleRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new domain-specific firewall rule.

    This endpoint allows the UI to create domain-specific rules similar to
    how allow/block list rules are created.

    Args:
        rule_request: Domain-specific firewall rule creation request
        db: Database session

    Returns:
        Created domain-specific firewall rule
    """
    logger = get_logger(__name__)

    # Validate that domain information is provided
    if not rule_request.domain_scope and not rule_request.applies_to_domains:
        raise HTTPException(
            status_code=400,
            detail="Domain-specific rules must have either domain_scope or applies_to_domains"
        )

    try:
        # Generate unique rule ID
        rule_id = f"rule_{uuid4().hex[:8]}_org_001"

        # Validate rule based on category (same logic as regular rules)
        if rule_request.rule_category == "blanket_domain":
            pattern = rule_request.pattern or ""
        elif rule_request.rule_category == "keyword":
            if not rule_request.pattern:
                raise HTTPException(status_code=400, detail="Keyword rules must specify a pattern")
            pattern = rule_request.pattern
        else:
            # Legacy domain rules
            pattern = rule_request.pattern or ""

        # Create new domain rule
        new_rule = FirewallRule(
            id=rule_id,
            org_id="org_001",  # Using default org for now
            rule_type=RuleType(rule_request.rule_type),
            pattern=pattern,
            description=rule_request.description,
            domain_scope=rule_request.domain_scope,
            applies_to_domains=rule_request.applies_to_domains,
            priority=rule_request.priority or 50,  # Default priority for domain rules
            rule_category=rule_request.rule_category
        )

        # Add to database
        db.add(new_rule)
        await db.commit()
        await db.refresh(new_rule)

        logger.info(f"Created domain-specific firewall rule: {rule_id} for domain: {rule_request.domain_scope or rule_request.applies_to_domains}")

        return {
            "id": new_rule.id,
            "org_id": new_rule.org_id,
            "rule_type": new_rule.rule_type.value,
            "pattern": new_rule.pattern,
            "description": new_rule.description,
            "domain_scope": new_rule.domain_scope,
            "applies_to_domains": new_rule.applies_to_domains,
            "priority": new_rule.priority,
            "rule_category": new_rule.rule_category,
            "created_at": new_rule.created_at.isoformat(),
            "updated_at": new_rule.updated_at.isoformat()
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create domain rule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create domain rule: {str(e)}")


@router.post("/test-domain-rule")
async def test_domain_rule(
    request: DomainRuleTestRequest,
    firewall: EnhancedFirewallService = Depends(get_firewall),
    db: AsyncSession = Depends(get_db)
):
    """
    Test text against domain-specific firewall rules.

    This endpoint allows the UI to test how domain-specific rules will behave
    for given text and domain context, similar to the existing test functionality.

    Args:
        request: Test request with text, domain, and optional task type
        firewall: Enhanced firewall service instance
        db: Database session

    Returns:
        Test results showing which domain rules would be triggered
    """
    logger = get_logger(__name__)

    try:
        # Run firewall scan with domain context
        scan_result = await firewall.scan_comprehensive(
            text=request.text,
            domain=request.domain,
            task_type=request.task_type
        )

        # Extract domain-specific rule information from allowlist scan
        allowlist_scan = scan_result.get("allowlist_scan", {})
        domain_rule_applied = allowlist_scan.get("domain_rule", False)

        return {
            "test_text": request.text,
            "domain": request.domain,
            "task_type": request.task_type,
            "safe_to_process": scan_result.get("safe_to_process", True),
            "domain_rule_applied": domain_rule_applied,
            "matched_pattern": allowlist_scan.get("matched_topic") or allowlist_scan.get("blocked_match"),
            "rule_type": "block" if allowlist_scan.get("blocked_match") else "allow" if allowlist_scan.get("matched_topic") else None,
            "violations": scan_result.get("violations", []),
            "summary": scan_result.get("summary", {})
        }

    except Exception as e:
        logger.error(f"Failed to test domain rule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to test domain rule: {str(e)}")


@router.get("/health")
async def firewall_health_check(firewall: EnhancedFirewallService = Depends(get_firewall)):
    """
    Check Enhanced Firewall Service health and capability.

    Args:
        firewall: Enhanced firewall service instance

    Returns:
        Health status and enhanced service capabilities
    """
    try:
        # Test service initialization
        await firewall.presidio._ensure_initialized()

        return {
            "status": "healthy",
            "service_type": "enhanced_firewall_with_presidio",
            "available_scans": ["pii", "secrets", "toxicity", "comprehensive", "allowlist"],
            "features": {
                "presidio_pii_detection": True,
                "entropy_analysis": True,
                "better_profanity": True,
                "firewall_logging": True,
                "comprehensive_analysis": True,
                "allowlist_blocklist": True,
                "database_rules": True
            },
            "supported_entities": [
                "EMAIL_ADDRESS", "US_SSN", "PHONE_NUMBER", "CREDIT_CARD",
                "IP_ADDRESS", "PERSON", "LOCATION", "ORGANIZATION"
            ],
            "timestamp": datetime.now()
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service_type": "enhanced_firewall_with_presidio",
            "error": str(e),
            "timestamp": datetime.now()
        }


# Helper functions

async def _allow_local(text: str, topics: Optional[List[str]], blocked: Optional[List[str]], db: AsyncSession) -> Dict[str, Any]:
    """
    Local allowlist/blocklist checking function adapted from server.py.

    Args:
        text: Text to check
        topics: Allowed topics/patterns
        blocked: Blocked patterns
        db: Database session for additional rule checking

    Returns:
        Dictionary with allowed status and matched patterns
    """
    lowered = (text or "").lower()

    # First check explicit blocked patterns
    if blocked:
        for b in blocked:
            if (b or "").lower() in lowered:
                return {"allowed": False, "blocked_match": b}

    # Check database blocklist rules
    blocklist_result = await _check_blocklist(text, db)
    if blocklist_result["blocked"]:
        return {
            "allowed": False,
            "blocked_match": blocklist_result["matched_rules"][0]["pattern"] if blocklist_result["matched_rules"] else "database_rule"
        }

    # Then check allowlist topics
    matched = None
    if topics:
        for t in topics:
            if (t or "").lower() in lowered:
                matched = t
                break

    # Check database allowlist rules if no explicit topics matched
    if not matched:
        allowlist_result = await _check_allowlist(text, db)
        if allowlist_result["allowed"]:
            matched = allowlist_result["matched_rules"][0]["pattern"] if allowlist_result["matched_rules"] else "database_rule"

    return {"allowed": bool(matched), "matched_topic": matched}


async def _check_blocklist(text: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Check text against database blocklist rules.

    Args:
        text: Text to check
        db: Database session

    Returns:
        Dictionary with blocked status and matched rules
    """
    try:
        # Get all block rules
        query = select(FirewallRule).where(FirewallRule.rule_type == RuleType.BLOCK)
        result = await db.execute(query)
        block_rules = result.scalars().all()

        lowered_text = text.lower()
        matched_rules = []

        for rule in block_rules:
            if rule.pattern.lower() in lowered_text:
                matched_rules.append({
                    "id": rule.id,
                    "pattern": rule.pattern,
                    "description": rule.description
                })

        return {
            "blocked": len(matched_rules) > 0,
            "matched_rules": matched_rules
        }

    except Exception as e:
        # Log error but don't fail the scan
        logger = get_logger(__name__)
        logger.error(f"Error checking blocklist: {str(e)}")
        return {"blocked": False, "matched_rules": []}


async def _check_allowlist(text: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Check text against database allowlist rules.

    Args:
        text: Text to check
        db: Database session

    Returns:
        Dictionary with allowed status and matched rules
    """
    try:
        # Get all allow rules
        query = select(FirewallRule).where(FirewallRule.rule_type == RuleType.ALLOW)
        result = await db.execute(query)
        allow_rules = result.scalars().all()

        lowered_text = text.lower()
        matched_rules = []

        for rule in allow_rules:
            if rule.pattern.lower() in lowered_text:
                matched_rules.append({
                    "id": rule.id,
                    "pattern": rule.pattern,
                    "description": rule.description
                })

        return {
            "allowed": len(matched_rules) > 0,
            "matched_rules": matched_rules
        }

    except Exception as e:
        # Log error but don't fail the scan
        logger = get_logger(__name__)
        logger.error(f"Error checking allowlist: {str(e)}")
        return {"allowed": False, "matched_rules": []}
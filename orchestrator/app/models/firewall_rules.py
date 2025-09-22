"""Firewall rules model for orchestrator service."""

from sqlalchemy import Column, String, DateTime, Text, Enum, Integer
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from ..db.database import Base
import enum


class RuleType(enum.Enum):
	"""Enumeration for firewall rule types."""
	ALLOW = "allow"
	BLOCK = "block"


class FirewallRule(Base):
	"""Firewall rules table for managing allow/block patterns with domain-aware capabilities."""
	__tablename__ = "firewall_rules"

	# Primary key
	id = Column(String(255), primary_key=True)  # Format: "rule_001_org_001"

	# Organization reference
	org_id = Column(String(255), nullable=False, index=True)  # References organization

	# Rule configuration
	rule_type = Column(Enum(RuleType), nullable=False)  # "allow" or "block"
	pattern = Column(String(500), nullable=False)  # The pattern to match
	description = Column(Text)  # Optional description of the rule

	# Domain-specific fields for context-aware blocking
	domain_scope = Column(String(100), nullable=True, index=True)  # Single domain (e.g., "healthcare", "finance")
	applies_to_domains = Column(JSONB, nullable=True)  # Multi-domain array (e.g., ["finance", "banking"])
	priority = Column(Integer, default=0, nullable=False, index=True)  # Rule evaluation order (higher = first)
	rule_category = Column(String(50), nullable=True, index=True)  # "blanket_domain", "keyword", or None for legacy

	# Timestamps
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

	def __repr__(self):
		domain_info = f", domain='{self.domain_scope}'" if self.domain_scope else ""
		return f"<FirewallRule(id={self.id}, type='{self.rule_type}', pattern='{self.pattern}'{domain_info}, priority={self.priority})>"
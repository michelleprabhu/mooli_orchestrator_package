"""Activity log model for controller service."""

from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
from datetime import datetime
import uuid
from ..db.database import Base


class ActivityLog(Base):
	"""Activity and audit log table for controller service."""
	__tablename__ = "activity_logs"
	
	# Primary key
	log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	
	# References
	organization_id = Column(String(255), ForeignKey("organizations.organization_id"), index=True)
	user_id = Column(String(255), ForeignKey("users.user_id"), index=True)
	orchestrator_id = Column(String(255), ForeignKey("orchestrators.orchestrator_id"), index=True)
	
	# Activity identification
	activity_type = Column(String(100), nullable=False, index=True)  # "login", "create_org", "deploy_orchestrator", etc.
	activity_category = Column(String(50), nullable=False)  # "auth", "admin", "deployment", "billing", etc.
	action = Column(String(100), nullable=False)  # "create", "update", "delete", "view", "execute"
	
	# Activity details
	resource_type = Column(String(100))  # "user", "organization", "orchestrator", "config"
	resource_id = Column(String(255))  # ID of the affected resource
	resource_name = Column(String(255))  # Human-readable name of the resource
	
	# Event metadata
	event_source = Column(String(100))  # "web", "api", "system", "webhook", "cli"
	event_status = Column(String(50), default="success")  # "success", "failure", "partial", "warning"
	
	# Request information
	request_id = Column(String(100), index=True)  # Unique request identifier
	session_id = Column(String(100), index=True)  # User session identifier
	endpoint = Column(String(255))  # API endpoint or page accessed
	method = Column(String(10))  # HTTP method (GET, POST, etc.)
	
	# Network and client information
	ip_address = Column(String(45))  # IPv4 or IPv6 address
	user_agent = Column(String(500))  # Browser/client user agent
	location = Column(JSON, default={})  # Geolocation data (country, city, etc.)
	
	# Activity content and changes
	description = Column(Text, nullable=False)  # Human-readable description
	details = Column(JSON, default={})  # Structured activity details
	changes = Column(JSON, default={})  # Before/after values for updates
	event_metadata = Column(JSON, default={})  # Additional contextual information
	
	# Security and risk assessment
	risk_level = Column(String(20), default="low")  # "low", "medium", "high", "critical"
	security_flags = Column(JSON, default=[])  # Security-related flags
	requires_review = Column(Boolean, default=False)  # Requires admin review
	
	# Performance metrics
	response_time_ms = Column(Integer)  # Response time for the operation
	processing_time_ms = Column(Integer)  # Server processing time
	
	# Administrative and compliance
	retention_days = Column(Integer, default=365)  # How long to keep this log
	archived = Column(Boolean, default=False)
	compliance_tags = Column(JSON, default=[])  # GDPR, SOX, HIPAA, etc.
	
	# Timestamps
	timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
	expires_at = Column(DateTime)  # When this log entry expires
	
	# Review and investigation
	reviewed = Column(Boolean, default=False)
	reviewed_by = Column(String(255), ForeignKey("users.user_id"))
	reviewed_at = Column(DateTime)
	investigation_notes = Column(Text)
	
	def __repr__(self):
		return f"<ActivityLog(log_id={self.log_id}, activity_type='{self.activity_type}', action='{self.action}')>"
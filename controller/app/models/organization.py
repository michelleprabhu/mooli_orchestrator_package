"""Orchestrator Instance model for controller service - aligned with orchestrator approach."""

from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
from datetime import datetime
import uuid
from ..db.database import Base


class Organization(Base):
	"""Organization table - represents organizations managed by the controller."""
	__tablename__ = "organizations"
	
	organization_id = Column(String(255), primary_key=True)
	name = Column(String(255), nullable=False)
	location = Column(String(100), default="unknown")
	is_active = Column(Boolean, default=True)
	is_independent = Column(Boolean, default=False)  # Independence mode
	settings = Column(JSON, default={})
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
	
	def __repr__(self):
		return f"<Organization(organization_id={self.organization_id}, name='{self.name}', is_active={self.is_active})>"


class OrchestratorInstance(Base):
	"""Orchestrator instance table - each instance represents one organization."""
	__tablename__ = "orchestrator_instances"
	
	# Primary identification (matches orchestrator's ORGANIZATION_ID)
	orchestrator_id = Column(String(255), primary_key=True)  # Format: "org_001"
	organization_name = Column(String(255), nullable=False, index=True)  # e.g., "Acme Corp"
	location = Column(String(100), default="unknown")  # e.g., "us-east-1", "on-prem"
	
	# Status and health (aligned with orchestrator's status tracking)
	status = Column(String(50), default="inactive")  # active, inactive, error, starting
	last_seen = Column(DateTime)
	health_status = Column(String(50), default="unknown")  # healthy, degraded, unhealthy
	
	# Features (matching orchestrator's config structure)
	features = Column(JSON, default={})  # {"cache": {"enabled": true}, "firewall": {"enabled": false}}
	session_config = Column(JSON, default={})  # {"timeout_seconds": 1800, "max_concurrent_sessions": 1000}
	
	# Independence and privacy settings (new controller-only features)
	is_independent = Column(Boolean, default=False)  # Orchestrator runs independently
	privacy_mode = Column(Boolean, default=False)  # Orchestrator hides details from controller
	
	# Connection information
	internal_url = Column(String(500))  # e.g., "http://orchestrator-org-001:8000"
	database_url = Column(String(500))  # Orchestrator's database connection
	redis_url = Column(String(500))  # Orchestrator's Redis connection
	
	# System information
	container_id = Column(String(255))
	image_name = Column(String(255))
	environment_variables = Column(JSON, default={})
	
	# Monitoring and observability
	phoenix_endpoint = Column(String(500))  # Phoenix monitoring endpoint
	monitoring_enabled = Column(Boolean, default=True)
	
	# Contact information (optional)
	admin_email = Column(String(255))
	support_email = Column(String(255))
	website = Column(String(255))
	
	# Timestamps
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
	last_activity = Column(DateTime)
	
	def __repr__(self):
		return f"<OrchestratorInstance(orchestrator_id={self.orchestrator_id}, name='{self.organization_name}', status={self.status})>"
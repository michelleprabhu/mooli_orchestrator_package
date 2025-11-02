"""Unified Organization model for controller service - simplified schema."""

from sqlalchemy import Column, String, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from ..db.database import Base


class Organization(Base):
	"""Unified organization table - represents organizations and their orchestrator instances."""
	__tablename__ = "organizations"
	
	# Primary identifiers
	org_id = Column(String(255), primary_key=True)
	org_name = Column(String(255), nullable=False)
	
	# Orchestrator connection info
	orchestrator_id = Column(String(255), unique=True)
	
	# Status tracking
	status = Column(String(50), default="inactive")  # active, inactive, error
	last_seen = Column(DateTime)
	connected_at = Column(DateTime)
	
	# Keepalive tracking
	keepalive_enabled = Column(Boolean, default=True)  # Does this org send keepalives?
	
	# Metadata
	location = Column(String(255))
	ip_address = Column(String(50))
	features = Column(JSONB, default={})
	
	# Contact information (optional)
	admin_email = Column(String(255))
	support_email = Column(String(255))
	website = Column(String(255))
	
	# Timestamps
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
	
	def __repr__(self):
		return f"<Organization(org_id={self.org_id}, name='{self.org_name}', status={self.status})>"
	
	def to_dict(self):
		"""Convert to dictionary for API responses."""
		return {
			"org_id": self.org_id,
			"org_name": self.org_name,
			"orchestrator_id": self.orchestrator_id,
			"status": self.status,
			"last_seen": self.last_seen.isoformat() if self.last_seen else None,
			"connected_at": self.connected_at.isoformat() if self.connected_at else None,
			"keepalive_enabled": self.keepalive_enabled,
			"location": self.location,
			"ip_address": self.ip_address,
			"features": self.features,
			"admin_email": self.admin_email,
			"support_email": self.support_email,
			"website": self.website,
			"created_at": self.created_at.isoformat() if self.created_at else None,
			"updated_at": self.updated_at.isoformat() if self.updated_at else None,
		}


class OrgStatistics(Base):
	"""Organization statistics table - counters only, no raw data."""
	__tablename__ = "org_statistics"
	
	org_id = Column(String(255), primary_key=True)
	
	# Prompt counters by domain
	total_prompts = Column(Integer, default=0)
	prompts_by_domain = Column(JSONB, default={})  # {"finance": 150, "legal": 200, ...}
	
	# Message counters
	total_recommendations = Column(Integer, default=0)
	total_monitoring_messages = Column(Integer, default=0)
	
	# Summary counters
	total_sessions = Column(Integer, default=0)
	total_errors = Column(Integer, default=0)
	
	# Last activity timestamps
	last_prompt_at = Column(DateTime)
	last_recommendation_at = Column(DateTime)
	last_monitoring_at = Column(DateTime)
	
	# Timestamps
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
	
	def __repr__(self):
		return f"<OrgStatistics(org_id={self.org_id}, total_prompts={self.total_prompts}, total_recommendations={self.total_recommendations})>"
	
	def to_dict(self):
		"""Convert to dictionary for API responses."""
		return {
			"org_id": self.org_id,
			"total_prompts": self.total_prompts,
			"prompts_by_domain": self.prompts_by_domain,
			"total_recommendations": self.total_recommendations,
			"total_monitoring_messages": self.total_monitoring_messages,
			"total_sessions": self.total_sessions,
			"total_errors": self.total_errors,
			"last_prompt_at": self.last_prompt_at.isoformat() if self.last_prompt_at else None,
			"last_recommendation_at": self.last_recommendation_at.isoformat() if self.last_recommendation_at else None,
			"last_monitoring_at": self.last_monitoring_at.isoformat() if self.last_monitoring_at else None,
			"created_at": self.created_at.isoformat() if self.created_at else None,
			"updated_at": self.updated_at.isoformat() if self.updated_at else None,
		}


# Backward compatibility aliases (for gradual migration)
OrchestratorInstance = Organization  # Alias for old code
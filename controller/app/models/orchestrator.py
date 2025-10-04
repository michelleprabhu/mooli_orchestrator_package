"""Orchestrator connection tracking model for controller service."""

from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
from datetime import datetime
import uuid
from ..db.database import Base


class OrchestratorConnection(Base):
	"""Track WebSocket connections to orchestrator instances."""
	__tablename__ = "orchestrator_connections"
	
	# Primary key
	connection_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
	
	# Reference to orchestrator instance
	orchestrator_id = Column(String(255), ForeignKey("orchestrator_instances.orchestrator_id"), nullable=False)
	
	# Connection details
	connection_type = Column(String(50), default="websocket")  # websocket, http, grpc
	connection_status = Column(String(50), default="pending")  # pending, active, failed, disconnected
	
	# WebSocket specific
	ws_endpoint = Column(String(500))  # WebSocket endpoint URL
	last_heartbeat = Column(DateTime)
	heartbeat_interval = Column(Integer, default=30)  # seconds
	
	# Connection metadata
	client_ip = Column(String(45))  # IPv4 or IPv6
	user_agent = Column(String(500))
	connection_metadata = Column(JSON, default={})
	
	# Error tracking
	connection_error = Column(Text)
	error_count = Column(Integer, default=0)
	last_error = Column(DateTime)
	
	# Timestamps
	connected_at = Column(DateTime, default=datetime.utcnow)
	disconnected_at = Column(DateTime)
	last_tested = Column(DateTime)
	
	def __repr__(self):
		return f"<OrchestratorConnection(orchestrator={self.orchestrator_id}, type={self.connection_type}, status={self.connection_status})>"
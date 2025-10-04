from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from ..db.database import Base

class OrchestratorMessage(Base):
    __tablename__ = "orchestrator_messages"
    
    id = Column(String(255), primary_key=True)
    orchestrator_id = Column(String(255), nullable=False, index=True)
    message_type = Column(String(50), nullable=False)  # "recommendation" or "monitoring"
    content = Column(Text, nullable=False)
    message_metadata = Column(JSON, default={})
    status = Column(String(50), default="pending")  # "pending", "accepted", "dismissed"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "orchestrator_id": self.orchestrator_id,
            "message_type": self.message_type,
            "content": self.content,
            "message_metadata": self.message_metadata,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

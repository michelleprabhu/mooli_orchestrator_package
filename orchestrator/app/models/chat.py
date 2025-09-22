"""
SQLAlchemy 2.0 ORM models for chat and message management.
Integrates domain classification and human evaluation capabilities.
"""

from datetime import datetime
from typing import List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, Float, func, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..db.database import Base


class Chat(Base):
    """
    Chat model representing a conversation session.
    Supports multi-tenant isolation and real-time communication.
    """
    __tablename__ = "chats"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Multi-tenant support
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationship to messages
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at"
    )
    
    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, session_id='{self.session_id}', org='{self.organization_id}')>"


class Message(Base):
    """
    Message model with domain classification and firewall scanning.
    Enhanced with evaluation capabilities and audit trail.
    """
    __tablename__ = "messages"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Domain classification fields (from orchestrator 2)
    domain: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    task_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    keywords: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # JSON array of keywords
    
    # Firewall scanning results (enhanced from orchestrator 2)
    firewall_scan_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Multi-tenant support
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # LLM processing metadata
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(nullable=True)
    processing_time_ms: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Provider tracking (DynaRoute integration)
    provider_used: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True, default="openai")
    cost_estimate: Mapped[Optional[float]] = mapped_column(nullable=True)
    dynaroute_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")
    
    # Human evaluations relationship
    human_evaluations: Mapped[List["HumanEvaluation"]] = relationship(
        "HumanEvaluation",
        back_populates="message",
        cascade="all, delete-orphan"
    )
    
    # LLM evaluation scores relationship
    llm_evaluations: Mapped[List["LLMEvaluationScore"]] = relationship(
        "LLMEvaluationScore",
        back_populates="message",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, chat_id={self.chat_id}, role='{self.role}', domain='{self.domain}')>"


class HumanEvaluation(Base):
    """
    Human evaluation model for collecting user feedback on AI responses.
    Supports star ratings and qualitative feedback.
    """
    
    __tablename__ = "human_evaluations"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Multi-tenant support
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    
    # Star ratings (1-5) for each metric
    answer_correctness: Mapped[float] = mapped_column(Float, nullable=False)
    answer_relevance: Mapped[float] = mapped_column(Float, nullable=False)
    hallucination_score: Mapped[float] = mapped_column(Float, nullable=False)
    
    # Overall satisfaction rating
    overall_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Qualitative feedback
    feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Evaluation metadata
    evaluation_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationship to message
    message: Mapped["Message"] = relationship("Message", back_populates="human_evaluations")
    
    def __repr__(self) -> str:
        return f"<HumanEvaluation(id={self.id}, message_id={self.message_id}, overall={self.overall_rating})>"


class LLMEvaluationScore(Base):
    """
    Automated LLM evaluation scores for AI responses.
    Provides objective metrics for response quality assessment.
    """
    
    __tablename__ = "llm_evaluation_scores"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Multi-tenant support
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Evaluation metrics (0.0 to 1.0)
    answer_correctness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    answer_relevance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hallucination_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Additional evaluation metrics
    coherence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Evaluation metadata
    evaluation_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    evaluation_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    evaluation_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    # Relationship to message
    message: Mapped["Message"] = relationship("Message", back_populates="llm_evaluations")
    
    def __repr__(self) -> str:
        return f"<LLMEvaluationScore(id={self.id}, message_id={self.message_id}, correctness={self.answer_correctness})>"
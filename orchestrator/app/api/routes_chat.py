"""
Chat API Router
===============

Provides REST API endpoints for chat conversation management.
Integrates with the ChatService for persistent conversation storage.
"""

import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..services.chat_service import get_chat_service
from ..db.database import db_manager
from ..models.chat import Chat, Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chats", tags=["chat"])


# Request/Response Models
class CreateChatRequest(BaseModel):
    """Request model for creating a new chat."""
    session_id: str
    user_id: str = "default_user"
    title: Optional[str] = None


class CreateMessageRequest(BaseModel):
    """Request model for creating a message."""
    role: str  # 'user', 'assistant', 'system'
    content: str
    metadata: Optional[Dict[str, Any]] = None


class MessageResponse(BaseModel):
    """Response model for message data."""
    id: int
    chat_id: int
    role: str
    content: str
    domain: Optional[str] = None
    task_type: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    """Response model for chat data."""
    id: int
    session_id: str
    organization_id: str
    user_id: Optional[str]
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int
    
    class Config:
        from_attributes = True


class ChatWithMessagesResponse(BaseModel):
    """Response model for chat with messages."""
    id: int
    session_id: str
    organization_id: str
    user_id: Optional[str]
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]
    
    class Config:
        from_attributes = True


class ConversationHistoryResponse(BaseModel):
    """Response model for conversation history formatted for LLM context."""
    session_id: str
    message_count: int
    messages: List[Dict[str, str]]  # OpenAI format: [{"role": "user", "content": "..."}]


async def get_orchestrator_db():
    """Get orchestrator database session."""
    async for session in db_manager.get_session():
        yield session


@router.post("/", response_model=ChatResponse)
async def create_chat(
    request: CreateChatRequest,
    chat_service = Depends(get_chat_service)
):
    """
    Create a new chat conversation.
    
    Args:
        request: Chat creation request with session_id, user_id, and optional title
        
    Returns:
        Created chat information
    """
    try:
        chat = await chat_service.get_or_create_chat(
            session_id=request.session_id,
            user_id=request.user_id,
            chat_title=request.title
        )
        
        # Get message count
        message_count = await chat_service.get_message_count(request.session_id)
        
        return ChatResponse(
            id=chat.id,
            session_id=chat.session_id,
            organization_id=chat.organization_id,
            user_id=chat.user_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            message_count=message_count
        )
        
    except Exception as e:
        logger.error(f"Failed to create chat: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create chat: {str(e)}")


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(
    session_id: str,
    limit: int = Query(50, description="Maximum number of messages to return"),
    chat_service = Depends(get_chat_service),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """
    Get messages for a specific chat session.
    
    Args:
        session_id: Chat session identifier
        limit: Maximum number of messages to return (default: 50)
        
    Returns:
        List of messages in the conversation
    """
    try:
        chat = await chat_service.get_chat_by_session(session_id)
        if not chat:
            raise HTTPException(status_code=404, detail=f"Chat not found for session: {session_id}")
        
        # Get messages from database
        from sqlalchemy import select, desc
        stmt = (
            select(Message)
            .where(Message.chat_id == chat.id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        result = await db.execute(stmt)
        messages = result.scalars().all()
        
        return [
            MessageResponse(
                id=msg.id,
                chat_id=msg.chat_id,
                role=msg.role,
                content=msg.content,
                domain=msg.domain,
                task_type=msg.task_type,
                model_used=msg.model_used,
                tokens_used=msg.tokens_used,
                processing_time_ms=msg.processing_time_ms,
                created_at=msg.created_at
            )
            for msg in messages
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chat messages for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")


@router.get("/{session_id}/history", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    session_id: str,
    limit: int = Query(20, description="Maximum number of messages for LLM context"),
    chat_service = Depends(get_chat_service)
):
    """
    Get conversation history formatted for LLM context.
    
    Args:
        session_id: Chat session identifier
        limit: Maximum number of messages for context (default: 20)
        
    Returns:
        Conversation history in OpenAI format
    """
    try:
        history = await chat_service.get_conversation_history(session_id, limit)
        message_count = await chat_service.get_message_count(session_id)
        
        return ConversationHistoryResponse(
            session_id=session_id,
            message_count=message_count,
            messages=history
        )
        
    except Exception as e:
        logger.error(f"Failed to get conversation history for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def create_message(
    session_id: str,
    request: CreateMessageRequest,
    user_id: str = Query("default_user", description="User ID for message attribution"),
    chat_service = Depends(get_chat_service)
):
    """
    Create a message in a chat conversation.
    
    Args:
        session_id: Chat session identifier
        request: Message creation request
        user_id: User ID for message attribution
        
    Returns:
        Created message information
    """
    # Log business operation initiation
    start_time = time.time()
    logger.info(f"Chat message creation started", extra={
        "session_id": session_id,
        "user_id": user_id,
        "role": request.role,
        "content_length": len(request.content),
        "has_metadata": request.metadata is not None,
        "service": "chat_api"
    })

    try:
        message = await chat_service.store_message(
            session_id=session_id,
            role=request.role,
            content=request.content,
            user_id=user_id,
            metadata=request.metadata
        )
        
        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Log successful business operation completion with metrics
        logger.info(f"Chat message created successfully", extra={
            "session_id": session_id,
            "user_id": user_id,
            "message_id": message.id,
            "chat_id": message.chat_id,
            "role": message.role,
            "content_length": len(message.content),
            "processing_time_ms": processing_time_ms,
            "model_used": message.model_used,
            "tokens_used": message.tokens_used,
            "domain": message.domain,
            "task_type": message.task_type,
            "service": "chat_api"
        })

        return MessageResponse(
            id=message.id,
            chat_id=message.chat_id,
            role=message.role,
            content=message.content,
            domain=message.domain,
            task_type=message.task_type,
            model_used=message.model_used,
            tokens_used=message.tokens_used,
            processing_time_ms=message.processing_time_ms,
            created_at=message.created_at
        )
        
    except Exception as e:
        logger.error(f"Failed to create message for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create message: {str(e)}")


@router.get("/", response_model=List[ChatResponse])
async def list_user_chats(
    user_id: str = Query("default_user", description="User ID to filter chats"),
    limit: int = Query(50, description="Maximum number of chats to return"),
    chat_service = Depends(get_chat_service)
):
    """
    List chats for a specific user.
    
    Args:
        user_id: User ID to filter chats
        limit: Maximum number of chats to return
        
    Returns:
        List of user's chats
    """
    try:
        chats = await chat_service.get_user_chats(user_id, limit)
        
        # Get message counts for each chat
        chat_responses = []
        for chat in chats:
            message_count = await chat_service.get_message_count(chat.session_id)
            chat_responses.append(ChatResponse(
                id=chat.id,
                session_id=chat.session_id,
                organization_id=chat.organization_id,
                user_id=chat.user_id,
                title=chat.title,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
                message_count=message_count
            ))
        
        return chat_responses
        
    except Exception as e:
        logger.error(f"Failed to list chats for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list chats: {str(e)}")


@router.get("/{session_id}", response_model=ChatWithMessagesResponse)
async def get_chat_with_messages(
    session_id: str,
    include_messages: bool = Query(True, description="Include messages in response"),
    message_limit: int = Query(50, description="Maximum number of messages to include"),
    chat_service = Depends(get_chat_service),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """
    Get a specific chat with its messages.
    
    Args:
        session_id: Chat session identifier
        include_messages: Whether to include messages in the response
        message_limit: Maximum number of messages to include
        
    Returns:
        Chat information with messages
    """
    try:
        chat = await chat_service.get_chat_by_session(session_id)
        if not chat:
            raise HTTPException(status_code=404, detail=f"Chat not found for session: {session_id}")
        
        messages = []
        if include_messages:
            # Get messages from database
            from sqlalchemy import select
            stmt = (
                select(Message)
                .where(Message.chat_id == chat.id)
                .order_by(Message.created_at)
                .limit(message_limit)
            )
            result = await db.execute(stmt)
            db_messages = result.scalars().all()
            
            messages = [
                MessageResponse(
                    id=msg.id,
                    chat_id=msg.chat_id,
                    role=msg.role,
                    content=msg.content,
                    domain=msg.domain,
                    task_type=msg.task_type,
                    model_used=msg.model_used,
                    tokens_used=msg.tokens_used,
                    processing_time_ms=msg.processing_time_ms,
                    created_at=msg.created_at
                )
                for msg in db_messages
            ]
        
        return ChatWithMessagesResponse(
            id=chat.id,
            session_id=chat.session_id,
            organization_id=chat.organization_id,
            user_id=chat.user_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            messages=messages
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chat with messages for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get chat: {str(e)}")
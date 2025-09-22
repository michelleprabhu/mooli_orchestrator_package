"""
Chat Service for Conversation History Management
==============================================

Handles database operations for chat conversations and message history.
Integrates with the existing Chat and Message models for persistent conversation storage.
"""

import os
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, func
from sqlalchemy.orm import selectinload

from ..models.chat import Chat, Message
from ..db.database import get_db
from ..core.logging_config import get_logger, audit_logger

logger = get_logger(__name__)


class ChatService:
	"""Service for managing chat conversations and message history."""
	
	def __init__(self):
		self.organization_id = os.getenv("ORGANIZATION_ID", "org_001")
		self.max_history_messages = 20  # Development limit - last 20 messages
		logger.info(f"ChatService initialized for organization: {self.organization_id}")
	
	async def get_or_create_chat(
		self, 
		session_id: str, 
		user_id: str = "default_user",
		chat_title: Optional[str] = None
	) -> Chat:
		"""Get existing chat by session_id or create a new one."""
		try:
			async for db in get_db():
				# First try to find existing chat
				stmt = select(Chat).where(
					and_(
						Chat.session_id == session_id,
						Chat.organization_id == self.organization_id
					)
				)
				result = await db.execute(stmt)
				existing_chat = result.scalar_one_or_none()
				
				if existing_chat:
					logger.debug(f"Found existing chat: {existing_chat.id} for session: {session_id}")
					return existing_chat
				
				# Create new chat if none exists
				new_chat = Chat(
					session_id=session_id,
					organization_id=self.organization_id,
					user_id=user_id,
					title=chat_title or f"Chat {session_id[:8]}",
					created_at=datetime.now(timezone.utc),
					updated_at=datetime.now(timezone.utc)
				)
				
				db.add(new_chat)
				await db.commit()
				await db.refresh(new_chat)
				
				# Audit chat creation
				audit_logger.log_database_operation(
					operation="CREATE",
					table="chats",
					record_id=new_chat.id,
					user_id=user_id,
					changes={
						"session_id": session_id,
						"organization_id": self.organization_id,
						"title": new_chat.title
					}
				)
				
				logger.info(f"Created new chat: {new_chat.id} for session: {session_id}")
				return new_chat
				
		except Exception as e:
			logger.error(f"Failed to get or create chat for session {session_id}: {e}")
			raise
	
	async def get_conversation_history(
		self, 
		session_id: str,
		limit: Optional[int] = None
	) -> List[Dict[str, str]]:
		"""
		Get conversation history for a session formatted for OpenAI.
		
		Returns:
			List of message dicts with 'role' and 'content' keys, ready for OpenAI API.
			Limited to last 20 messages by default for development.
		"""
		try:
			message_limit = limit or self.max_history_messages
			
			async for db in get_db():
				# Get chat and recent messages in one query
				stmt = (
					select(Chat)
					.options(selectinload(Chat.messages))
					.where(
						and_(
							Chat.session_id == session_id,
							Chat.organization_id == self.organization_id
						)
					)
				)
				result = await db.execute(stmt)
				chat = result.scalar_one_or_none()
				
				if not chat:
					logger.debug(f"No chat found for session: {session_id}")
					return []
				
				# Get the most recent messages, ordered by creation time
				stmt = (
					select(Message)
					.where(Message.chat_id == chat.id)
					.order_by(desc(Message.created_at))
					.limit(message_limit)
				)
				result = await db.execute(stmt)
				recent_messages = result.scalars().all()
				
				# Reverse to get chronological order (oldest first)
				messages = list(reversed(recent_messages))
				
				# Format for OpenAI API
				formatted_messages = []
				for msg in messages:
					formatted_messages.append({
						"role": msg.role,
						"content": msg.content
					})
				
				logger.debug(f"Retrieved {len(formatted_messages)} messages for session: {session_id}")
				return formatted_messages
				
		except Exception as e:
			logger.error(f"Failed to get conversation history for session {session_id}: {e}")
			return []  # Return empty list on error to avoid breaking LLM calls
	
	async def store_message(
		self,
		session_id: str,
		role: str,  # 'user', 'assistant', 'system'
		content: str,
		user_id: str = "default_user",
		metadata: Optional[Dict] = None
	) -> Message:
		"""Store a message in the conversation history."""
		logger.info(f"💾 [CHAT-SERVICE] Storing message in database:")
		logger.info(f"   📝 Session ID: {session_id}")
		logger.info(f"   👤 User ID: {user_id}")
		logger.info(f"   🎭 Role: {role}")
		logger.info(f"   📏 Content length: {len(content)}")
		logger.info(f"   🔧 Metadata provided: {metadata is not None}")

		if metadata:
			logger.info(f"   📊 Metadata details:")
			logger.info(f"      🎯 Model: {metadata.get('model', 'not specified')}")
			logger.info(f"      🏭 Provider: {metadata.get('provider_used', 'not specified')}")
			logger.info(f"      💰 Cost: {metadata.get('cost_estimate', 'not specified')}")
			logger.info(f"      🎯 DynaRoute metadata: {metadata.get('dynaroute_metadata', 'none')}")

		try:
			# Get or create the chat first
			chat = await self.get_or_create_chat(session_id, user_id)
			logger.info(f"   💬 Chat ID: {chat.id}")

			async for db in get_db():
				# Create the message
				message = Message(
					chat_id=chat.id,
					role=role,
					content=content,
					organization_id=self.organization_id,
					model_used=metadata.get("model") if metadata else None,
					tokens_used=metadata.get("tokens") if metadata else None,
					processing_time_ms=metadata.get("processing_time_ms") if metadata else None,
					# Provider tracking
					provider_used=metadata.get("provider_used", "openai") if metadata else "openai",
					cost_estimate=metadata.get("cost_estimate") if metadata else None,
					dynaroute_metadata=metadata.get("dynaroute_metadata") if metadata else None,
					created_at=datetime.now(timezone.utc),
					updated_at=datetime.now(timezone.utc)
				)

				logger.info(f"   🏭 Provider being stored: {message.provider_used}")
				logger.info(f"   💰 Cost being stored: {message.cost_estimate}")
				logger.info(f"   🎯 DynaRoute metadata being stored: {message.dynaroute_metadata is not None}")
				if message.dynaroute_metadata:
					logger.info(f"      - DynaRoute metadata content: {message.dynaroute_metadata}")
				
				db.add(message)
				
				# Update chat's updated_at timestamp
				chat.updated_at = datetime.now(timezone.utc)
				
				await db.commit()
				await db.refresh(message)

				# Log successful database storage
				logger.info(f"   ✅ Message stored successfully:")
				logger.info(f"      📊 Message ID: {message.id}")
				logger.info(f"      🏭 Final provider_used: {message.provider_used}")
				logger.info(f"      💰 Final cost_estimate: {message.cost_estimate}")
				logger.info(f"      🎯 Final DynaRoute metadata stored: {message.dynaroute_metadata is not None}")

				# Audit message creation
				audit_logger.log_database_operation(
					operation="CREATE",
					table="messages",
					record_id=message.id,
					user_id=user_id,
					changes={
						"chat_id": chat.id,
						"role": role,
						"content_length": len(content),
						"organization_id": self.organization_id,
						"model_used": metadata.get("model") if metadata else None,
						"tokens_used": metadata.get("tokens") if metadata else None,
						"provider_used": metadata.get("provider_used", "openai") if metadata else "openai",
						"cost_estimate": metadata.get("cost_estimate") if metadata else None
					}
				)
				
				logger.debug(f"Stored {role} message in chat {chat.id}: {content[:50]}...")
				return message
				
		except Exception as e:
			logger.error(f"Failed to store message for session {session_id}: {e}")
			raise
	
	async def get_chat_by_session(self, session_id: str) -> Optional[Chat]:
		"""Get chat record by session_id."""
		try:
			async for db in get_db():
				stmt = select(Chat).where(
					and_(
						Chat.session_id == session_id,
						Chat.organization_id == self.organization_id
					)
				)
				result = await db.execute(stmt)
				return result.scalar_one_or_none()
		except Exception as e:
			logger.error(f"Failed to get chat by session {session_id}: {e}")
			return None
	
	async def get_user_chats(
		self, 
		user_id: str,
		limit: int = 50
	) -> List[Chat]:
		"""Get all chats for a user, ordered by most recent."""
		try:
			async for db in get_db():
				stmt = (
					select(Chat)
					.where(
						and_(
							Chat.user_id == user_id,
							Chat.organization_id == self.organization_id
						)
					)
					.order_by(desc(Chat.updated_at))
					.limit(limit)
				)
				result = await db.execute(stmt)
				return list(result.scalars().all())
		except Exception as e:
			logger.error(f"Failed to get chats for user {user_id}: {e}")
			return []
	
	async def get_message_count(self, session_id: str) -> int:
		"""Get total message count for a conversation."""
		try:
			async for db in get_db():
				# Get chat first
				chat = await self.get_chat_by_session(session_id)
				if not chat:
					return 0
				
				stmt = select(func.count(Message.id)).where(Message.chat_id == chat.id)
				result = await db.execute(stmt)
				return result.scalar() or 0
		except Exception as e:
			logger.error(f"Failed to get message count for session {session_id}: {e}")
			return 0
	
	async def store_llm_evaluation_scores(
		self,
		session_id: str,
		role: str,
		answer_correctness: float,
		answer_relevance: float,
		hallucination_score: float,
		coherence_score: float = None,
		evaluation_model: str = None,
		user_id: str = None
	):
		"""Store LLM evaluation scores for the most recent message in a session."""
		try:
			async for db in get_db():
				# Get the chat
				chat = await self.get_chat_by_session(session_id)
				if not chat:
					logger.warning(f"No chat found for session {session_id}")
					return
				
				# Get the most recent message with the specified role
				stmt = (
					select(Message)
					.where(
						and_(
							Message.chat_id == chat.id,
							Message.role == role
						)
					)
					.order_by(desc(Message.created_at))
					.limit(1)
				)
				result = await db.execute(stmt)
				message = result.scalar_one_or_none()
				
				if not message:
					logger.warning(f"No {role} message found for session {session_id}")
					return
				
				# Import the LLMEvaluationScore model
				from ..models.chat import LLMEvaluationScore
				
				# Create evaluation score record
				evaluation_score = LLMEvaluationScore(
					message_id=message.id,
					organization_id=self.organization_id,
					answer_correctness=answer_correctness,
					answer_relevance=answer_relevance,
					hallucination_score=hallucination_score,
					coherence_score=coherence_score,
					evaluation_model=evaluation_model
				)
				
				db.add(evaluation_score)
				await db.commit()
				
				logger.info(f"Stored LLM evaluation scores for message {message.id}")
				
		except Exception as e:
			logger.error(f"Failed to store LLM evaluation scores for session {session_id}: {e}")
			raise


# Global service instance
_chat_service = None

def get_chat_service() -> ChatService:
	"""Get or create the global chat service instance."""
	global _chat_service
	if _chat_service is None:
		_chat_service = ChatService()
	return _chat_service
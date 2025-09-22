"""
Feedback service for handling human and LLM evaluations.
Integrates with existing evaluation services and database models.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db.database import get_db
from ..models.chat import Message, HumanEvaluation, LLMEvaluationScore
from ..core.logging_config import get_logger, audit_logger
from .Evaluation.answer_correctness import evaluate_answer_correctness
from .Evaluation.answer_relevance import evaluate_answer_relevance
from .Evaluation.hallucination import evaluate_hallucination

logger = get_logger(__name__)


class FeedbackService:
	"""Service for handling feedback submissions and evaluations."""
	
	def __init__(self):
		"""Initialize feedback service."""
		pass
	
	async def submit_feedback(
		self,
		organization_id: str,
		user_id: str,
		conversation_id: str,
		message_id: str,
		human_feedback: List[Dict[str, Any]],
		llm_feedback: List[Dict[str, Any]],
		client_info: Dict[str, Any]
	) -> Dict[str, Any]:
		"""
		Submit feedback with both human and LLM evaluations.
		
		Args:
			organization_id: Organization identifier
			user_id: User identifier
			conversation_id: Chat/conversation identifier
			message_id: Specific message being evaluated
			human_feedback: List of human evaluation scores
			llm_feedback: List of LLM evaluation scores
			client_info: Client metadata (user agent, screen dimensions)
		
		Returns:
			Dictionary with submission results
		"""
		# Log feedback submission initiation
		logger.info(f"Feedback submission started", extra={
			"message_id": message_id,
			"organization_id": organization_id,
			"user_id": user_id,
			"conversation_id": conversation_id,
			"human_metrics": len(human_feedback),
			"llm_metrics": len(llm_feedback),
			"service": "feedback_service"
		})

		try:
			async for db in get_db():
				# Verify message exists and belongs to organization
				# Handle special cases for cached responses or invalid IDs
				if message_id in ["null", "undefined", None] or not message_id:
					logger.warning(f"Feedback submission attempted for cached/invalid message", extra={
						"message_id": message_id,
						"organization_id": organization_id,
						"user_id": user_id,
						"service": "feedback_service"
					})
					raise ValueError("Cannot submit feedback for cached responses or invalid message IDs")
				
				try:
					message_id_int = int(message_id)
				except ValueError:
					logger.error(f"Invalid message ID format", extra={
						"message_id": message_id,
						"message_id_type": type(message_id).__name__,
						"organization_id": organization_id,
						"user_id": user_id,
						"service": "feedback_service"
					})
					raise ValueError(f"Invalid message ID format: {message_id}. Expected integer.")
				
				stmt = select(Message).where(
					Message.id == message_id_int,
					Message.organization_id == organization_id
				)
				result = await db.execute(stmt)
				message = result.scalar_one_or_none()
				
				if not message:
					logger.error(f"Message not found for feedback submission", extra={
						"message_id": message_id,
						"message_id_int": message_id_int,
						"organization_id": organization_id,
						"user_id": user_id,
						"service": "feedback_service"
					})
					raise ValueError(f"Message {message_id} not found for organization {organization_id}")
				
				logger.debug(f"Message verified for feedback submission", extra={
					"message_id": message_id,
					"organization_id": organization_id,
					"message_content_length": len(message.content),
					"service": "feedback_service"
				})
				
				# Store human evaluation inline
				# Extract the 3 required metrics from feedback
				metrics = {item["metric"]: item["score"] for item in human_feedback}
				
				# Validate required metrics
				required_metrics = ["Answer Correctness", "Answer Relevance", "Hallucination"]
				for metric in required_metrics:
					if metric not in metrics:
						raise ValueError(f"Missing required metric: {metric}")
				
				# Create human evaluation record
				human_eval = HumanEvaluation(
					message_id=int(message_id),
					session_id=conversation_id,
					organization_id=organization_id,
					user_id=user_id,
					answer_correctness=float(metrics["Answer Correctness"]),
					answer_relevance=float(metrics["Answer Relevance"]),
					hallucination_score=float(metrics["Hallucination"]),
					overall_rating=sum(metrics.values()) / len(metrics),  # Average rating
					feedback_text=None,  # Could be extended to include text feedback
					evaluation_context=None  # Could include client_info
				)
				
				db.add(human_eval)
				await db.commit()
				await db.refresh(human_eval)
				human_eval_id = human_eval.id
				
				# Audit human evaluation creation
				audit_logger.log_database_operation(
					operation="CREATE",
					table="human_evaluations",
					record_id=human_eval_id,
					user_id=user_id,
					changes={
						"message_id": message_id,
						"organization_id": organization_id,
						"metrics_submitted": len(human_feedback),
						"human_metrics": {item["metric"]: item["score"] for item in human_feedback}
					}
				)
				
				# Process LLM evaluations inline
				llm_eval_id = None
				if llm_feedback:
					# Extract the 3 required metrics from LLM feedback
					llm_metrics = {item["metric"]: item["score"] for item in llm_feedback}
					
					# Create LLM evaluation record
					llm_eval = LLMEvaluationScore(
						message_id=int(message_id),
						organization_id=organization_id,
						answer_correctness=float(llm_metrics.get("Answer Correctness", 0.0)),
						answer_relevance=float(llm_metrics.get("Answer Relevance", 0.0)),
						hallucination_score=float(llm_metrics.get("Hallucination", 0.0)),
						evaluation_model="feedback_widget",
						evaluation_version="1.0"
					)
					
					db.add(llm_eval)
					await db.commit()
					await db.refresh(llm_eval)
					llm_eval_id = llm_eval.id
				
				# Audit LLM evaluation creation (if successful)
				if llm_eval_id:
					audit_logger.log_database_operation(
						operation="CREATE",
						table="llm_evaluation_scores",
						record_id=llm_eval_id,
						user_id="system",
						changes={
							"message_id": message_id,
							"organization_id": organization_id,
							"evaluation_type": "automated_llm",
							"metrics_evaluated": ["answer_correctness", "answer_relevance", "hallucination"]
						}
					)
				
				await db.commit()
				
				logger.info(
					f"Feedback submitted for message {message_id}",
					extra={
						"organization_id": organization_id,
						"user_id": user_id,
						"human_eval_id": human_eval_id,
						"llm_eval_id": llm_eval_id,
						"client_info": client_info
					}
				)
				
				# Send real-time WebSocket notifications
				try:
					from ..api.routes_websocket import broadcast_feedback_notification, broadcast_evaluation_runs_update
					
					# Notify user about feedback submission
					await broadcast_feedback_notification(
						user_id=user_id,
						message_id=message_id,
						feedback_type="human_submitted",
						feedback_data={
							"human_evaluation_id": human_eval_id,
							"metrics_count": len(human_feedback),
							"evaluation_status": "completed"
						}
					)
					
					# Notify user about LLM evaluation completion
					if llm_eval_id:
						await broadcast_feedback_notification(
							user_id=user_id,
							message_id=message_id,
							feedback_type="llm_completed",
							feedback_data={
								"llm_evaluation_id": llm_eval_id,
								"evaluation_status": "completed"
							}
						)
					
					# Update organization monitoring dashboard with new evaluation data
					new_evaluation_data = {
						"type": "new_evaluation",
						"message_id": message_id,
						"human_evaluation_id": human_eval_id,
						"llm_evaluation_id": llm_eval_id,
						"user_id": user_id,
						"timestamp": datetime.utcnow().isoformat()
					}
					await broadcast_evaluation_runs_update(organization_id, new_evaluation_data)
					
				except Exception as ws_error:
					# Don't fail the feedback submission if WebSocket notification fails
					logger.warning(f"Failed to send WebSocket notifications: {str(ws_error)}")
					pass
				
				return {
					"success": True,
					"human_evaluation_id": human_eval_id,
					"llm_evaluation_id": llm_eval_id,
					"message": "Feedback submitted successfully"
				}
				
		except Exception as e:
			logger.error(
				f"Failed to submit feedback for message {message_id}: {str(e)}",
				extra={
					"organization_id": organization_id,
					"user_id": user_id,
					"error": str(e)
				}
			)
			raise
	
	async def _get_message(
		self, 
		db: AsyncSession, 
		message_id: str, 
		organization_id: str
	) -> Optional[Message]:
		"""Get message by ID and verify organization ownership."""
		try:
			message_id_int = int(message_id)
		except ValueError:
			return None
		
		stmt = select(Message).where(
			Message.id == message_id_int,
			Message.organization_id == organization_id
		)
		result = await db.execute(stmt)
		return result.scalar_one_or_none()
	
	async def _store_human_evaluation(
		self,
		db: AsyncSession,
		message_id: str,
		organization_id: str,
		user_id: str,
		session_id: str,
		human_feedback: List[Dict[str, Any]]
	) -> int:
		"""Store human evaluation scores in database."""
		
		# Extract the 3 required metrics from feedback
		metrics = {item["metric"]: item["score"] for item in human_feedback}
		
		# Validate required metrics
		required_metrics = ["Answer Correctness", "Answer Relevance", "Hallucination"]
		for metric in required_metrics:
			if metric not in metrics:
				raise ValueError(f"Missing required metric: {metric}")
		
		# Create human evaluation record
		human_eval = HumanEvaluation(
			message_id=int(message_id),
			session_id=session_id,
			organization_id=organization_id,
			user_id=user_id,
			answer_correctness=float(metrics["Answer Correctness"]),
			answer_relevance=float(metrics["Answer Relevance"]),
			hallucination_score=float(metrics["Hallucination"]),
			overall_rating=sum(metrics.values()) / len(metrics),  # Average rating
			feedback_text=None,  # Could be extended to include text feedback
			evaluation_context={
				"submission_time": datetime.utcnow().isoformat(),
				"metrics_count": len(human_feedback)
			}
		)
		
		db.add(human_eval)
		await db.flush()
		return human_eval.id
	
	async def _process_llm_evaluations(
		self,
		db: AsyncSession,
		message: Message,
		organization_id: str,
		llm_feedback: List[Dict[str, Any]]
	) -> int:
		"""Process LLM evaluations using existing evaluation services."""
		
		# Extract context for evaluation
		question = "User query"  # Default fallback
		answer = message.content
		
		# Try to get the question from chat history
		if message.chat and message.chat.messages:
			chat_messages = sorted(message.chat.messages, key=lambda m: m.created_at)
			user_messages = [m for m in chat_messages if m.role == "user" and m.created_at < message.created_at]
			if user_messages:
				question = user_messages[-1].content
		
		# Log LLM evaluation initiation
		logger.info(f"LLM evaluation started", extra={
			"message_id": message.id,
			"organization_id": organization_id,
			"question_length": len(question),
			"answer_length": len(answer),
			"evaluation_types": ["answer_correctness", "answer_relevance", "hallucination"],
			"service": "feedback_service"
		})

		evaluation_start_time = datetime.utcnow()
		try:
			# Run evaluations concurrently
			eval_tasks = [
				evaluate_answer_correctness(question, answer),
				evaluate_answer_relevance(question, answer),
				evaluate_hallucination(question, answer)
			]
			
			correctness_result, relevance_result, hallucination_result = await asyncio.gather(*eval_tasks)
			evaluation_duration = (datetime.utcnow() - evaluation_start_time).total_seconds() * 1000
			
			# Log successful LLM evaluation completion
			logger.info(f"LLM evaluation completed", extra={
				"message_id": message.id,
				"organization_id": organization_id,
				"correctness_score": correctness_result.get("score", 0.0),
				"relevance_score": relevance_result.get("score", 0.0),
				"hallucination_score": hallucination_result.get("score", 0.0),
				"evaluation_duration_ms": evaluation_duration,
				"service": "feedback_service"
			})
			
			# Create LLM evaluation record
			llm_eval = LLMEvaluationScore(
				message_id=message.id,
				organization_id=organization_id,
				answer_correctness=correctness_result.get("score", 0.0),
				answer_relevance=relevance_result.get("score", 0.0),
				hallucination_score=hallucination_result.get("score", 0.0),
				coherence_score=None,  # Could be added later
				completeness_score=None,  # Could be added later
				evaluation_model="gpt-4",  # Default model used by evaluators
				evaluation_version="1.0",
				evaluation_context={
					"question": question,
					"answer": answer,
					"evaluation_time": datetime.utcnow().isoformat(),
					"evaluators": {
						"correctness": correctness_result,
						"relevance": relevance_result,
						"hallucination": hallucination_result
					}
				}
			)
			
			db.add(llm_eval)
			await db.flush()
			return llm_eval.id
			
		except Exception as e:
			evaluation_duration = (datetime.utcnow() - evaluation_start_time).total_seconds() * 1000
			
			# Log detailed error information
			logger.error(f"LLM evaluation failed", extra={
				"message_id": message.id,
				"organization_id": organization_id,
				"error": str(e),
				"error_type": type(e).__name__,
				"evaluation_duration_ms": evaluation_duration,
				"question_length": len(question),
				"answer_length": len(answer),
				"service": "feedback_service"
			})
			
			# Create a record with null scores to indicate evaluation failure
			llm_eval = LLMEvaluationScore(
				message_id=message.id,
				organization_id=organization_id,
				evaluation_model="gpt-4",
				evaluation_version="1.0",
				evaluation_context={
					"error": str(e),
					"error_type": type(e).__name__,
					"evaluation_time": datetime.utcnow().isoformat(),
					"failed_after_ms": evaluation_duration
				}
			)
			db.add(llm_eval)
			await db.flush()
			return llm_eval.id
	
	async def get_message_evaluations(
		self,
		message_id: str,
		organization_id: str
	) -> Dict[str, Any]:
		"""Get all evaluations for a specific message."""
		try:
			# Handle special cases for cached responses or invalid IDs
			if message_id in ["null", "undefined", None] or not message_id:
				logger.warning(f"Evaluation retrieval attempted for cached/invalid message", extra={
					"message_id": message_id,
					"organization_id": organization_id,
					"service": "feedback_service"
				})
				raise ValueError("Cannot retrieve evaluations for cached responses or invalid message IDs")
			
			try:
				message_id_int = int(message_id)
			except ValueError:
				logger.error(f"Invalid message ID format in get_evaluations", extra={
					"message_id": message_id,
					"message_id_type": type(message_id).__name__,
					"organization_id": organization_id,
					"service": "feedback_service"
				})
				raise ValueError(f"Invalid message ID format: {message_id}. Expected integer.")
			
			async for db in get_db():
				
				# Get human evaluations
				human_stmt = select(HumanEvaluation).where(
					HumanEvaluation.message_id == message_id_int,
					HumanEvaluation.organization_id == organization_id
				)
				human_result = await db.execute(human_stmt)
				human_evals = human_result.scalars().all()
				
				# Get LLM evaluations
				llm_stmt = select(LLMEvaluationScore).where(
					LLMEvaluationScore.message_id == message_id_int,
					LLMEvaluationScore.organization_id == organization_id
				)
				llm_result = await db.execute(llm_stmt)
				llm_evals = llm_result.scalars().all()
				
				return {
					"message_id": message_id,
					"human_evaluations": [
						{
							"id": eval.id,
							"answer_correctness": eval.answer_correctness,
							"answer_relevance": eval.answer_relevance,
							"hallucination_score": eval.hallucination_score,
							"overall_rating": eval.overall_rating,
							"user_id": eval.user_id,
							"created_at": eval.created_at.isoformat()
						}
						for eval in human_evals
					],
					"llm_evaluations": [
						{
							"id": eval.id,
							"answer_correctness": eval.answer_correctness,
							"answer_relevance": eval.answer_relevance,
							"hallucination_score": eval.hallucination_score,
							"evaluation_model": eval.evaluation_model,
							"created_at": eval.created_at.isoformat()
						}
						for eval in llm_evals
					]
				}
				
		except Exception as e:
			logger.error(f"Failed to get evaluations for message {message_id}: {str(e)}")
			raise


# Singleton instance
feedback_service = FeedbackService()
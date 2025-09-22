"""
API routes for feedback and evaluation management.
"""

from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field, validator

from ..services.feedback_service import feedback_service
from ..core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


# Pydantic models for request/response
class FeedbackItem(BaseModel):
	"""Individual feedback item with metric and score."""
	metric: str = Field(..., description="Metric name (Answer Correctness, Answer Relevance, Hallucination)")
	score: float = Field(..., ge=1.0, le=5.0, description="Score from 1.0 to 5.0")


class ClientInfo(BaseModel):
	"""Client information for tracking."""
	ua: str = Field(..., description="User agent string")
	width: int = Field(..., gt=0, description="Screen width")
	height: int = Field(..., gt=0, description="Screen height")


class FeedbackSubmissionRequest(BaseModel):
	"""Request model for feedback submission."""
	conversationId: str = Field(..., description="Conversation/chat ID")
	messageId: str = Field(..., description="Message ID being evaluated")
	organizationId: str = Field(..., description="Organization ID")
	userId: str = Field(..., description="User ID submitting feedback")
	human: List[FeedbackItem] = Field(..., min_items=3, max_items=3, description="Human evaluation scores")
	llm: List[FeedbackItem] = Field(..., min_items=3, max_items=3, description="LLM evaluation scores")
	timestamp: str = Field(..., description="ISO8601 timestamp of submission")
	client: ClientInfo = Field(..., description="Client information")
	
	@validator('human', 'llm')
	def validate_metrics(cls, v):
		"""Validate that required metrics are present."""
		required_metrics = {"Answer Correctness", "Answer Relevance", "Hallucination"}
		provided_metrics = {item.metric for item in v}
		
		if required_metrics != provided_metrics:
			missing = required_metrics - provided_metrics
			extra = provided_metrics - required_metrics
			error_msg = []
			if missing:
				error_msg.append(f"Missing metrics: {missing}")
			if extra:
				error_msg.append(f"Extra metrics: {extra}")
			raise ValueError("; ".join(error_msg))
		
		return v


class FeedbackResponse(BaseModel):
	"""Response model for feedback submission."""
	success: bool
	human_evaluation_id: int
	llm_evaluation_id: int
	message: str


class EvaluationHistoryResponse(BaseModel):
	"""Response model for evaluation history."""
	message_id: str
	human_evaluations: List[Dict[str, Any]]
	llm_evaluations: List[Dict[str, Any]]


@router.post("/", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackSubmissionRequest):
	"""
	Submit feedback with human and LLM evaluations.
	
	This endpoint processes feedback submissions containing both human ratings
	and triggers LLM evaluations for the specified message.
	"""
	try:
		# Convert FeedbackItem objects to dictionaries
		human_feedback = [
			{"metric": item.metric, "score": item.score} 
			for item in request.human
		]
		llm_feedback = [
			{"metric": item.metric, "score": item.score} 
			for item in request.llm
		]
		client_info = {
			"user_agent": request.client.ua,
			"screen_width": request.client.width,
			"screen_height": request.client.height,
			"submission_timestamp": request.timestamp
		}
		
		result = await feedback_service.submit_feedback(
			organization_id=request.organizationId,
			user_id=request.userId,
			conversation_id=request.conversationId,
			message_id=request.messageId,
			human_feedback=human_feedback,
			llm_feedback=llm_feedback,
			client_info=client_info
		)
		
		return FeedbackResponse(**result)
		
	except ValueError as e:
		logger.warning(f"Invalid feedback submission: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail={"error": "invalid_feedback", "message": str(e)}
		)
	except Exception as e:
		logger.error(f"Feedback submission failed: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail={"error": "submission_failed", "message": "Failed to submit feedback"}
		)


@router.get("/message/{message_id}", response_model=EvaluationHistoryResponse)
async def get_message_evaluations(
	message_id: str,
	organization_id: str
):
	"""
	Get all evaluations for a specific message.
	
	Returns both human and LLM evaluations for the specified message.
	"""
	try:
		result = await feedback_service.get_message_evaluations(
			message_id=message_id,
			organization_id=organization_id
		)
		
		return EvaluationHistoryResponse(**result)
		
	except ValueError as e:
		logger.warning(f"Invalid message ID: {message_id}")
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail={"error": "invalid_message_id", "message": str(e)}
		)
	except Exception as e:
		logger.error(f"Failed to get evaluations for message {message_id}: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail={"error": "fetch_failed", "message": "Failed to retrieve evaluations"}
		)


@router.post("/llm-evaluation")
async def trigger_llm_evaluation(
	message_id: str,
	organization_id: str
):
	"""
	Trigger LLM evaluation for a specific message.
	
	This endpoint can be used to run LLM evaluations independently
	of human feedback submission.
	"""
	try:
		# For now, this will be handled through the feedback service
		# But we could extend it to handle standalone LLM evaluations
		result = await feedback_service.get_message_evaluations(
			message_id=message_id,
			organization_id=organization_id
		)
		
		# Check if LLM evaluation already exists
		if result["llm_evaluations"]:
			return {
				"success": True,
				"message": "LLM evaluation already exists",
				"evaluation_id": result["llm_evaluations"][-1]["id"]
			}
		
		# If no LLM evaluation exists, we would trigger one here
		# For now, return a message indicating this functionality
		return {
			"success": False,
			"message": "Standalone LLM evaluation not yet implemented",
			"note": "LLM evaluations are currently triggered via feedback submission"
		}
		
	except Exception as e:
		logger.error(f"Failed to trigger LLM evaluation for message {message_id}: {str(e)}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail={"error": "evaluation_failed", "message": "Failed to trigger LLM evaluation"}
		)


@router.get("/health")
async def feedback_health_check():
	"""Health check endpoint for feedback service."""
	return {
		"status": "healthy",
		"service": "feedback",
		"timestamp": datetime.utcnow().isoformat(),
		"endpoints": [
			"POST /api/feedback/ - Submit feedback",
			"GET /api/feedback/message/{message_id} - Get evaluations",
			"POST /api/feedback/llm-evaluation - Trigger LLM evaluation"
		]
	}
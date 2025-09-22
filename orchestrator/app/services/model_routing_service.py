"""
Model Routing Service
====================

Provides configurable model routing for different types of LLM calls.
Allows a routing agent to dynamically change models based on domain, cost, performance, etc.
"""

import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class CallType(Enum):
    """Types of LLM calls that can be routed."""
    DOMAIN_CLASSIFICATION = "domain_classification"
    USER_RESPONSE = "user_response"
    EVALUATION = "evaluation"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"

@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    model_name: str
    max_tokens: int = 1000
    temperature: float = 0.7
    supports_json_mode: bool = False
    cost_per_1k_input_tokens: float = 0.0005
    cost_per_1k_output_tokens: float = 0.0015
    priority: int = 1  # Higher number = higher priority
    metadata: Dict[str, Any] = field(default_factory=dict)

class ModelRoutingService:
    """Service for routing different types of LLM calls to appropriate models."""
    
    def __init__(self, organization_id: str = "default"):
        """Initialize the model routing service with default configurations."""
        self.organization_id = organization_id
        self._routing_config: Dict[CallType, ModelConfig] = {}
        self._fallback_models: Dict[str, str] = {}
        
        # Initialize default model configurations
        self._setup_default_configurations()
    
    def _setup_default_configurations(self):
        """Setup default model configurations for different call types."""
        
        # Domain classification: Fast, cheap, JSON-compatible model
        self._routing_config[CallType.DOMAIN_CLASSIFICATION] = ModelConfig(
            model_name="gpt-4-1106-preview",
            max_tokens=200,
            temperature=0.1,
            supports_json_mode=True,
            cost_per_1k_input_tokens=0.00001,
            cost_per_1k_output_tokens=0.00003,
            priority=1,
            metadata={"purpose": "classification", "optimized_for": "speed_and_accuracy"}
        )
        
        # User response: Default high-quality model
        self._routing_config[CallType.USER_RESPONSE] = ModelConfig(
            model_name="gpt-4o",
            max_tokens=1000,
            temperature=0.7,
            supports_json_mode=False,
            cost_per_1k_input_tokens=0.000005,
            cost_per_1k_output_tokens=0.000015,
            priority=1,
            metadata={"purpose": "user_interaction", "optimized_for": "quality"}
        )
        
        # Evaluation services: Cost-effective model
        self._routing_config[CallType.EVALUATION] = ModelConfig(
            model_name="gpt-4-1106-preview",
            max_tokens=500,
            temperature=0.2,
            supports_json_mode=True,
            cost_per_1k_input_tokens=0.00001,
            cost_per_1k_output_tokens=0.00003,
            priority=1,
            metadata={"purpose": "evaluation", "optimized_for": "consistency"}
        )
        
        # Fallback models for compatibility issues
        self._fallback_models = {
            "gpt-4o": "gpt-4-1106-preview",  # If gpt-4o fails with JSON mode
            "gpt-4": "gpt-4-1106-preview",   # If base gpt-4 doesn't support features
            "gpt-3.5-turbo": "gpt-3.5-turbo-1106"  # Ensure JSON mode support
        }
        
        logger.info("Model routing service initialized with default configurations")
    
    def get_model_for_call_type(
        self,
        call_type: CallType,
        domain: Optional[str] = None,
        user_preferences: Optional[Dict] = None,
        override_model: Optional[str] = None
    ) -> ModelConfig:
        """
        Get the appropriate model configuration for a specific call type.
        
        Args:
            call_type: Type of LLM call being made
            domain: Domain classification (for future routing logic)
            user_preferences: User-specific model preferences
            override_model: Explicit model override from routing agent
            
        Returns:
            ModelConfig for the selected model
        """
        
        # Handle explicit override first
        if override_model:
            logger.info(f"Using model override: {override_model} for {call_type.value}")
            return self._create_override_config(override_model, call_type)
        
        # Get base configuration
        base_config = self._routing_config.get(call_type)
        if not base_config:
            logger.warning(f"No configuration found for {call_type.value}, using default")
            base_config = self._routing_config[CallType.USER_RESPONSE]
        
        # Apply domain-specific routing (future enhancement)
        model_config = self._apply_domain_routing(base_config, domain)
        
        # Apply user preferences (future enhancement)
        model_config = self._apply_user_preferences(model_config, user_preferences)
        
        logger.debug(f"Selected model {model_config.model_name} for {call_type.value}")
        return model_config
    
    def _create_override_config(self, model_name: str, call_type: CallType) -> ModelConfig:
        """Create a model config for an overridden model."""
        base_config = self._routing_config.get(call_type, self._routing_config[CallType.USER_RESPONSE])
        
        # Determine JSON mode support based on known models
        supports_json = model_name in [
            "gpt-4-1106-preview", "gpt-4-0125-preview", "gpt-4o-2024-08-06",
            "gpt-3.5-turbo-1106", "gpt-3.5-turbo-0125", "gpt-4o-mini"
        ]
        
        return ModelConfig(
            model_name=model_name,
            max_tokens=base_config.max_tokens,
            temperature=base_config.temperature,
            supports_json_mode=supports_json,
            cost_per_1k_input_tokens=base_config.cost_per_1k_input_tokens,
            cost_per_1k_output_tokens=base_config.cost_per_1k_output_tokens,
            priority=base_config.priority,
            metadata={"override": True, "original_call_type": call_type.value}
        )
    
    def _apply_domain_routing(self, base_config: ModelConfig, domain: Optional[str]) -> ModelConfig:
        """Apply domain-specific model routing (future enhancement point)."""
        if not domain:
            return base_config
            
        # Future: Route based on domain
        # e.g., use code-specialized models for programming domain
        # e.g., use math-optimized models for math domain
        
        return base_config
    
    def _apply_user_preferences(self, base_config: ModelConfig, preferences: Optional[Dict]) -> ModelConfig:
        """Apply user-specific preferences (future enhancement point)."""
        if not preferences:
            return base_config
            
        # Future: Apply user preferences like:
        # - Cost optimization vs quality
        # - Speed vs accuracy trade-offs
        # - Specific model preferences
        
        return base_config
    
    def update_model_for_call_type(
        self,
        call_type: CallType,
        model_config: ModelConfig,
        routing_agent_id: Optional[str] = None
    ):
        """
        Update model configuration for a specific call type.
        This will be called by the routing agent.
        
        Args:
            call_type: The call type to update
            model_config: New model configuration
            routing_agent_id: ID of the routing agent making the change
        """
        old_model = self._routing_config.get(call_type)
        self._routing_config[call_type] = model_config
        
        logger.info(f"Model routing updated by agent {routing_agent_id}: {call_type.value} "
                   f"{old_model.model_name if old_model else 'None'} -> {model_config.model_name}")
    
    def get_fallback_model(self, failed_model: str) -> Optional[str]:
        """
        Get a fallback model for a failed model.
        
        Args:
            failed_model: The model that failed
            
        Returns:
            Fallback model name or None if no fallback available
        """
        fallback = self._fallback_models.get(failed_model)
        if fallback:
            logger.info(f"Using fallback model {fallback} for failed model {failed_model}")
        return fallback
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """Get statistics about current routing configuration."""
        return {
            "call_types_configured": len(self._routing_config),
            "fallback_models_available": len(self._fallback_models),
            "configurations": {
                call_type.value: {
                    "model": config.model_name,
                    "supports_json": config.supports_json_mode,
                    "priority": config.priority
                }
                for call_type, config in self._routing_config.items()
            }
        }
    
    def validate_model_compatibility(self, model_name: str, requires_json_mode: bool = False) -> bool:
        """
        Validate if a model is compatible with specific requirements.
        
        Args:
            model_name: Model to validate
            requires_json_mode: Whether JSON mode support is required
            
        Returns:
            True if model is compatible, False otherwise
        """
        if requires_json_mode:
            json_compatible_models = [
                "gpt-4-1106-preview", "gpt-4-0125-preview", "gpt-4o-2024-08-06",
                "gpt-3.5-turbo-1106", "gpt-3.5-turbo-0125", "gpt-4o-mini"
            ]
            return model_name in json_compatible_models
        
        return True  # Most models are compatible for basic text generation

# Singleton instance
_model_routing_service: Optional[ModelRoutingService] = None

def get_model_routing_service(organization_id: str = "default") -> ModelRoutingService:
    """Get the singleton model routing service instance."""
    global _model_routing_service
    if _model_routing_service is None:
        _model_routing_service = ModelRoutingService(organization_id=organization_id)
    return _model_routing_service
"""Custom Phoenix span processor to properly classify LLM spans."""

from opentelemetry.sdk.trace import SpanProcessor, ReadableSpan
from opentelemetry.trace import SpanKind, Span
from typing import Optional


class PhoenixLLMSpanProcessor(SpanProcessor):
    """Custom span processor to fix LLM span classification for Phoenix."""
    
    def on_start(self, span: ReadableSpan, parent_context: Optional[object] = None) -> None:
        """Called when a span starts - enrich LLM spans with classification attributes."""
        # Check if this is a writable span
        if hasattr(span, 'set_attribute'):
            # First, fix UNKNOWN span names
            if span.name == 'UNKNOWN' or not span.name:
                # Try to infer proper name from attributes
                attributes = getattr(span, 'attributes', {})
                if self._is_llm_span('', attributes):
                    # Set a proper span name for LLM calls
                    if hasattr(span, 'update_name'):
                        span.update_name('openai.chat.completion')
                    # Set span kind
                    if hasattr(span, '_span_kind'):
                        span._span_kind = SpanKind.CLIENT
            
            # Check if this is an LLM call or MoolAI enhanced span
            span_attributes = getattr(span, 'attributes', {})
            is_llm_span = self._is_llm_span(span.name, span_attributes)
            is_moolai_span = self._is_moolai_span(span.name, span_attributes)
            
            if is_llm_span or is_moolai_span:
                try:
                    # Add traditional LLM attributes for Phoenix compatibility
                    if is_llm_span:
                        span.set_attribute("llm.system", self._extract_llm_system(span_attributes))
                        span.set_attribute("phoenix.span_type", "LLM")
                        
                        # Extract model name
                        model_name = self._extract_model_name(span_attributes)
                        if model_name:
                            span.set_attribute("llm.model.name", model_name)
                        
                        # Ensure span kind is set properly
                        span.set_attribute("span.kind", "LLM")
                        
                        # Add moolai service attributes for OpenAI auto-instrumented spans
                        if span.name == 'openai.chat':
                            # Service attribution now comes from parent span or OpenAI proxy
                            # Only add default fallback if no service attribution exists
                            if not span_attributes.get('moolai.service_name'):
                                span.set_attribute("moolai.service_name", "unknown_service")
                            span.set_attribute("moolai.operation_name", "chat_completion")
                            span.set_attribute("moolai.organization_id", "org_001")  # Default org
                            
                            # Calculate and add cost data using token information
                            self._add_cost_calculation(span, span_attributes)
                    
                    # Handle vendor-prefixed MoolAI attributes for enhanced observability
                    if is_moolai_span:
                        # Mark as MoolAI enhanced span
                        span.set_attribute("moolai.enhanced", True)
                        
                        # Extract and preserve vendor-prefixed cache attributes
                        if any(key.startswith('moolai.cache.') for key in str(span_attributes)):
                            span.set_attribute("moolai.cache.tracked", True)
                            
                        # Extract and preserve vendor-prefixed firewall attributes
                        if any(key.startswith('moolai.firewall.') for key in str(span_attributes)):
                            span.set_attribute("moolai.firewall.tracked", True)
                    
                    # Add legacy cache-related attributes for backward compatibility
                    if 'cache_hit' in str(span_attributes) or 'from_cache' in str(span_attributes):
                        span.set_attribute("cache.hit", span_attributes.get('from_cache', False))
                        if 'cache_similarity' in str(span_attributes):
                            span.set_attribute("cache.similarity", span_attributes.get('cache_similarity', 0.0))
                            
                except Exception:
                    # Silently ignore if we can't set attributes
                    pass
            
    def on_end(self, span: ReadableSpan) -> None:
        """Called when a span ends - span is now read-only."""
        # ReadableSpan is read-only, so we can't modify it here
        # All modifications must happen in on_start
        pass
            
    def _is_llm_span(self, span_name: str, attributes: dict) -> bool:
        """Check if this span represents an LLM call."""
        if not span_name:
            return False
            
        # Check span name patterns
        llm_patterns = [
            'openai.chat',
            'openai.completion',
            'anthropic.chat',
            'chat.completion',
            'llm.',
            'moolai.llm.call'  # Enhanced MoolAI LLM span names
        ]
        
        for pattern in llm_patterns:
            if pattern.lower() in span_name.lower():
                return True
                
        # Check attributes for LLM indicators
        if attributes:
            # Check for gen_ai namespace (GenAI semantic conventions)
            if any(key.startswith('gen_ai.') for key in attributes.keys()):
                return True
            # Check for llm namespace  
            if any(key.startswith('llm.') for key in attributes.keys()):
                return True
            # Check for OpenAI specific attributes
            if 'openai.api_base' in str(attributes) or 'openai' in str(attributes.get('llm.system', '')):
                return True
            # Check for vendor-prefixed LLM attributes
            if any(key.startswith('moolai.llm.') for key in str(attributes)):
                return True
                
        return False
        
    def _is_moolai_span(self, span_name: str, attributes: dict) -> bool:
        """Check if this span is enhanced with MoolAI vendor-prefixed attributes."""
        # Check span name patterns for MoolAI spans
        moolai_patterns = [
            'moolai.request.process',
            'moolai.cache.lookup',
            'moolai.firewall.scan',
            'moolai.llm.call'
        ]
        
        for pattern in moolai_patterns:
            if pattern in span_name:
                return True
                
        # Check for vendor-prefixed attributes
        if attributes:
            attribute_str = str(attributes)
            if any(prefix in attribute_str for prefix in [
                'moolai.session_id',
                'moolai.cache.',
                'moolai.firewall.',
                'moolai.llm.',
                'moolai.tokens.'
            ]):
                return True
                
        return False
        
    def _extract_llm_system(self, attributes: dict) -> str:
        """Extract the LLM system/provider from span attributes."""
        if not attributes:
            return "unknown"
            
        # Check gen_ai.system first (semantic conventions)
        gen_ai_system = attributes.get('gen_ai.system')
        if gen_ai_system:
            return gen_ai_system
            
        # Check llm.system
        llm_system = attributes.get('llm.system')  
        if llm_system:
            return llm_system
            
        # Infer from other attributes
        if 'openai' in str(attributes).lower():
            return "openai"
        elif 'anthropic' in str(attributes).lower():
            return "anthropic"
        elif 'claude' in str(attributes).lower():
            return "anthropic"
            
        return "openai"  # Default fallback
        
    def _extract_model_name(self, attributes: dict) -> str:
        """Extract the model name from span attributes."""
        if not attributes:
            return ""
            
        # Check gen_ai.request.model first (semantic conventions)
        gen_ai_model = attributes.get('gen_ai.request.model')
        if gen_ai_model:
            return gen_ai_model
            
        # Check gen_ai response model
        gen_ai_response_model = attributes.get('gen_ai.response.model')
        if gen_ai_response_model:
            return gen_ai_response_model
            
        # Check llm.model_name
        llm_model = attributes.get('llm.model_name')
        if llm_model:
            return llm_model
            
        return "gpt-3.5-turbo"  # Default fallback
    
    def _add_cost_calculation(self, span, attributes: dict) -> None:
        """Add cost calculation to OpenAI chat spans using token data."""
        try:
            # Extract token data from gen_ai attributes
            prompt_tokens = attributes.get('gen_ai', {}).get('usage', {}).get('prompt_tokens', 0)
            completion_tokens = attributes.get('gen_ai', {}).get('usage', {}).get('completion_tokens', 0)
            model_name = attributes.get('gen_ai', {}).get('request', {}).get('model', 'gpt-3.5-turbo')
            
            # Only calculate cost if we have token data
            if prompt_tokens and completion_tokens:
                # Import cost calculator  
                from ...monitoring.utils.cost_calculator import calculate_cost
                
                # Calculate cost using existing utility
                total_cost = calculate_cost(model_name, prompt_tokens, completion_tokens)
                
                # Add cost to span attributes
                span.set_attribute("moolai.cost", total_cost)
                span.set_attribute("moolai.llm.cost", total_cost)
                span.set_attribute("moolai.llm.input_tokens", prompt_tokens)
                span.set_attribute("moolai.llm.output_tokens", completion_tokens)
                span.set_attribute("moolai.llm.total_tokens", prompt_tokens + completion_tokens)
                span.set_attribute("moolai.llm.model", model_name)
                
        except Exception as e:
            # Silently ignore cost calculation errors to avoid breaking spans
            pass
        
    def shutdown(self) -> None:
        """Shutdown the processor."""
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush the processor."""
        return True
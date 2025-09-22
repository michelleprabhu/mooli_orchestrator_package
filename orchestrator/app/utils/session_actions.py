# Session Action Processing System
from __future__ import annotations
import logging
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timezone

from .session_state import SessionState, SessionManager, get_session_manager

logger = logging.getLogger("session_actions")

@dataclass
class ActionResult:
    """Result of processing a session action."""
    success: bool
    action_type: str
    data: Dict[str, Any]
    side_effects: List[str]  # What happened (buffer_update, persistence, etc.)
    new_state: Optional[SessionState] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

def _now_iso() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()

class SessionActionProcessor:
    """Processes session actions with state validation."""
    
    def __init__(self, buffer_manager=None, config_manager=None):
        self.buffer_manager = buffer_manager
        self.config_manager = config_manager
        self.session_manager = get_session_manager()
        
        # Map action types to handler methods
        self.action_handlers = {
            "connect": self._handle_connect_action,
            "send_message": self._handle_message_action,
            "join_conversation": self._handle_join_conversation_action,
            "heartbeat": self._handle_heartbeat_action,
            "disconnect": self._handle_disconnect_action,
            "prompts_request": self._handle_prompts_request_action,
            "prompt_detail_request": self._handle_prompt_detail_request_action,
            "prompts_subscribe": self._handle_prompts_subscribe_action,
            "prompts_export": self._handle_prompts_export_action,
            "analytics_subscribe": self._handle_analytics_subscribe_action,
            "analytics_unsubscribe": self._handle_analytics_unsubscribe_action,
            "analytics_request": self._handle_analytics_request_action
        }
    
    async def process_action(self, 
                           msg: Dict[str, Any], 
                           user_id: str, 
                           session_id: str, 
                           current_state: SessionState) -> ActionResult:
        """Process action with state validation."""
        action_type = msg.get("type")
        
        try:
            # Validate action is allowed in current state
            if not self._is_action_valid(action_type, current_state):
                logger.warning(f"[ACTION-PROC] Invalid action '{action_type}' in state '{current_state.value}' for session {session_id}")
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    data={},
                    side_effects=[],
                    error=f"Action '{action_type}' not valid in state '{current_state.value}'"
                )
            
            # Get the appropriate handler
            handler = self.action_handlers.get(action_type)
            if not handler:
                logger.warning(f"[ACTION-PROC] Unknown action type: {action_type}")
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    data={},
                    side_effects=[],
                    error=f"Unknown action type: {action_type}"
                )
            
            # Process the action
            logger.debug(f"[ACTION-PROC] Processing {action_type} for session {session_id}")
            result = await handler(msg, user_id, session_id, current_state)
            
            # Update session activity
            if result.success:
                self.session_manager.update_activity(
                    session_id,
                    increment_messages=(action_type == "send_message"),
                    custom_data=result.metadata
                )
            
            return result
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Error processing {action_type} for session {session_id}: {e}")
            return ActionResult(
                success=False,
                action_type=action_type,
                data={},
                side_effects=[],
                error=f"Internal error: {str(e)}"
            )
    
    def _is_action_valid(self, action_type: str, state: SessionState) -> bool:
        """Validate if action is allowed in current state."""
        action_state_map = {
            "connect": [SessionState.INITIALIZING],
            "send_message": [SessionState.ACTIVE, SessionState.IDLE],
            "join_conversation": [SessionState.ACTIVE, SessionState.IDLE],
            "heartbeat": [SessionState.ACTIVE, SessionState.PROCESSING, SessionState.IDLE],
            "disconnect": [SessionState.ACTIVE, SessionState.PROCESSING, SessionState.IDLE, SessionState.DISCONNECTING],
            "analytics_subscribe": [SessionState.ACTIVE, SessionState.IDLE],
            "analytics_unsubscribe": [SessionState.ACTIVE, SessionState.IDLE],
            "analytics_request": [SessionState.ACTIVE, SessionState.IDLE],
            "prompts_request": [SessionState.ACTIVE, SessionState.IDLE],
            "prompt_detail_request": [SessionState.ACTIVE, SessionState.IDLE],
            "prompts_subscribe": [SessionState.ACTIVE, SessionState.IDLE],
            "prompts_export": [SessionState.ACTIVE, SessionState.IDLE]
        }
        
        allowed_states = action_state_map.get(action_type, [])
        return state in allowed_states
    
    async def _handle_connect_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle session connection with buffer manager integration."""
        side_effects = []
        
        try:
            # Update buffer manager if available
            if self.buffer_manager:
                metadata = msg.get("metadata", {})
                metadata.update({
                    "session_id": session_id,
                    "connected_at": _now_iso(),
                    "connection_type": "websocket_session"
                })
                
                self.buffer_manager.update_active_user(
                    user_id=user_id,
                    orch_id=session_id,
                    metadata=metadata
                )
                side_effects.append("buffer_manager_updated")
            
            # Update config manager presence if available
            if self.config_manager:
                try:
                    self.config_manager.touch_presence(status="active")
                    self.config_manager.update_session_activity(1)
                    side_effects.append("presence_updated")
                except Exception as e:
                    logger.warning(f"[ACTION-PROC] Config manager update failed: {e}")
            
            # Load existing conversations (placeholder for now)
            conversations = []  # TODO: Load from database
            
            return ActionResult(
                success=True,
                action_type="connect",
                data={
                    "session_id": session_id,
                    "user_id": user_id,
                    "created_at": _now_iso(),
                    "conversations": conversations,
                    "session_metadata": {
                        "connection_method": "websocket",
                        "established_at": _now_iso()
                    }
                },
                side_effects=side_effects,
                new_state=SessionState.ACTIVE,
                metadata={"connection_established": True}
            )
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Connect action failed: {e}")
            return ActionResult(
                success=False,
                action_type="connect",
                data={},
                side_effects=side_effects,
                error=str(e)
            )
    
    async def _handle_message_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle message sending with conversation management."""
        side_effects = []
        
        try:
            # Extract message details
            conversation_id = msg.get("conversation_id") or str(uuid.uuid4())
            message_content = msg.get("message", "")
            message_id = str(uuid.uuid4())
            
            # Add to buffer manager if available
            if self.buffer_manager:
                metadata = {
                    "session_id": session_id,
                    "conversation_id": conversation_id,
                    "message_type": "user",
                    "source": "websocket_session"
                }
                
                self.buffer_manager.add_prompt(
                    prompt_id=message_id,
                    user_id=user_id,
                    prompt=message_content,
                    response=None,
                    metadata=metadata
                )
                side_effects.append("message_buffered")
            
            # Update session conversation context
            self.session_manager.update_activity(
                session_id,
                conversation_id=conversation_id,
                custom_data={"last_message_id": message_id}
            )
            side_effects.append("session_updated")
            
            # Get sequence number (placeholder)
            sequence_number = 1  # TODO: Get actual sequence from conversation history
            
            return ActionResult(
                success=True,
                action_type="send_message",
                data={
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "sequence_number": sequence_number,
                    "processing_status": "received",
                    "content_length": len(message_content)
                },
                side_effects=side_effects,
                new_state=SessionState.PROCESSING,
                metadata={
                    "message_processed": True,
                    "conversation_id": conversation_id
                }
            )
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Message action failed: {e}")
            return ActionResult(
                success=False,
                action_type="send_message",
                data={},
                side_effects=side_effects,
                error=str(e)
            )
    
    async def _handle_join_conversation_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle conversation join with history loading."""
        side_effects = []
        
        try:
            conversation_id = msg.get("conversation_id")
            if not conversation_id:
                return ActionResult(
                    success=False,
                    action_type="join_conversation",
                    data={},
                    side_effects=[],
                    error="conversation_id required"
                )
            
            # Update session conversation context
            self.session_manager.update_activity(
                session_id,
                conversation_id=conversation_id,
                custom_data={"joined_conversation": conversation_id}
            )
            side_effects.append("conversation_context_updated")
            
            # Load conversation history (placeholder)
            messages = []  # TODO: Load actual messages from database
            conversation_title = f"Conversation {conversation_id[:8]}"  # Placeholder
            
            return ActionResult(
                success=True,
                action_type="join_conversation",
                data={
                    "conversation_id": conversation_id,
                    "title": conversation_title,
                    "messages": messages,
                    "message_count": len(messages),
                    "joined_at": _now_iso()
                },
                side_effects=side_effects,
                new_state=SessionState.ACTIVE,
                metadata={"active_conversation": conversation_id}
            )
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Join conversation action failed: {e}")
            return ActionResult(
                success=False,
                action_type="join_conversation",
                data={},
                side_effects=side_effects,
                error=str(e)
            )
    
    async def _handle_heartbeat_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle heartbeat/keepalive with presence update."""
        side_effects = []
        
        try:
            # Update buffer manager if available
            if self.buffer_manager:
                metadata = {
                    "heartbeat": _now_iso(),
                    "session_id": session_id
                }
                self.buffer_manager.update_active_user(
                    user_id=user_id,
                    orch_id=session_id,
                    metadata=metadata
                )
                side_effects.append("heartbeat_recorded")
            
            # Update presence (throttled)
            if self.config_manager:
                try:
                    self.config_manager.touch_presence(status="active")
                    side_effects.append("presence_updated")
                except Exception as e:
                    logger.debug(f"[ACTION-PROC] Presence update throttled or failed: {e}")
            
            return ActionResult(
                success=True,
                action_type="heartbeat",
                data={
                    "timestamp": _now_iso(),
                    "session_status": "active"
                },
                side_effects=side_effects,
                metadata={"heartbeat_processed": True}
            )
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Heartbeat action failed: {e}")
            return ActionResult(
                success=False,
                action_type="heartbeat",
                data={},
                side_effects=side_effects,
                error=str(e)
            )
    
    async def _handle_disconnect_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle session disconnect with cleanup."""
        side_effects = []
        
        try:
            # Remove from buffer manager if available
            if self.buffer_manager:
                self.buffer_manager.remove_active_user(user_id)
                side_effects.append("user_removed_from_buffer")
            
            # Update config manager
            if self.config_manager:
                try:
                    self.config_manager.update_session_activity(0)
                    side_effects.append("session_activity_cleared")
                except Exception as e:
                    logger.warning(f"[ACTION-PROC] Config manager cleanup failed: {e}")
            
            return ActionResult(
                success=True,
                action_type="disconnect",
                data={
                    "session_id": session_id,
                    "disconnected_at": _now_iso(),
                    "cleanup_completed": True
                },
                side_effects=side_effects,
                new_state=SessionState.EXPIRED,
                metadata={"disconnection_processed": True}
            )
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Disconnect action failed: {e}")
            return ActionResult(
                success=False,
                action_type="disconnect",
                data={},
                side_effects=side_effects,
                error=str(e)
            )

    async def _handle_analytics_subscribe_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle analytics subscription request."""
        logger.info(f"📊 [ANALYTICS-SUBSCRIBE-DEBUG] Analytics subscription request received for user {user_id}, session {session_id}")
        logger.info(f"📊 [ANALYTICS-SUBSCRIBE-DEBUG] Message: {msg}")
        side_effects = []

        try:
            from ..api.routes_websocket import analytics_subscribers
            from ..api.routes_websocket import session_connections

            logger.info(f"📊 [ANALYTICS-SUBSCRIBE-DEBUG] Current analytics_subscribers count: {len(analytics_subscribers)}")
            logger.info(f"📊 [ANALYTICS-SUBSCRIBE-DEBUG] Current session_connections: {list(session_connections.keys())}")

            # Get the actual connection_id from session mapping
            connection_id = session_connections.get(session_id, session_id)
            logger.info(f"📊 [ANALYTICS-SUBSCRIBE-DEBUG] Connection ID mapping: {session_id} -> {connection_id}")

            if session_id not in analytics_subscribers:
                subscriber_info = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "connection_id": connection_id,  # Use actual connection_id from mapping
                    "subscribed_at": datetime.now(timezone.utc).isoformat(),
                    "subscription_info": {},
                    "time_range": "30d"
                }
                analytics_subscribers[session_id] = subscriber_info
                logger.info(f"📊 [ANALYTICS-SUBSCRIBE-DEBUG] Added new subscriber: {subscriber_info}")
            else:
                logger.info(f"📊 [ANALYTICS-SUBSCRIBE-DEBUG] Session already subscribed, updating existing subscription")

            # Mark as subscribed to analytics
            analytics_subscribers[session_id]["subscription_info"]["include_analytics"] = True
            side_effects.append("added_to_analytics_subscribers")

            logger.info(f"📊 [ANALYTICS-SUBSCRIBE-DEBUG] Final analytics_subscribers: {analytics_subscribers}")

            # Mark session as subscribed to analytics
            self.session_manager.update_activity(
                session_id,
                custom_data={"analytics_subscribed": True, "subscribed_at": _now_iso()}
            )
            side_effects.append("analytics_subscription_recorded")

            # Update buffer manager if available
            if self.buffer_manager:
                metadata = {
                    "analytics_subscribed": True,
                    "session_id": session_id,
                    "subscribed_at": _now_iso()
                }
                self.buffer_manager.update_active_user(
                    user_id=user_id,
                    orch_id=session_id,
                    metadata=metadata
                )
                side_effects.append("buffer_subscription_updated")

            return ActionResult(
                success=True,
                action_type="analytics_subscribe",
                data={
                    "subscribed": True,
                    "session_id": session_id,
                    "subscribed_at": _now_iso(),
                    "subscriber_count": len(analytics_subscribers)
                },
                side_effects=side_effects,
                metadata={"analytics_subscription": True}
            )
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Analytics subscribe action failed: {e}")
            return ActionResult(
                success=False,
                action_type="analytics_subscribe",
                data={},
                side_effects=side_effects,
                error=str(e)
            )

    async def _handle_analytics_unsubscribe_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle analytics unsubscribe request."""
        side_effects = []

        try:
            from ..api.routes_websocket import analytics_subscribers

            # Remove this session from analytics subscribers (CRITICAL FIX)
            if session_id in analytics_subscribers:
                del analytics_subscribers[session_id]
                side_effects.append("removed_from_analytics_subscribers")

            # Mark session as unsubscribed from analytics
            self.session_manager.update_activity(
                session_id,
                custom_data={"analytics_subscribed": False, "unsubscribed_at": _now_iso()}
            )
            side_effects.append("analytics_unsubscription_recorded")

            # Update buffer manager if available
            if self.buffer_manager:
                metadata = {
                    "analytics_subscribed": False,
                    "session_id": session_id,
                    "unsubscribed_at": _now_iso()
                }
                self.buffer_manager.update_active_user(
                    user_id=user_id,
                    orch_id=session_id,
                    metadata=metadata
                )
                side_effects.append("buffer_unsubscription_updated")

            return ActionResult(
                success=True,
                action_type="analytics_unsubscribe",
                data={
                    "subscribed": False,
                    "session_id": session_id,
                    "unsubscribed_at": _now_iso(),
                    "subscriber_count": len(analytics_subscribers)
                },
                side_effects=side_effects,
                metadata={"analytics_subscription": False}
            )
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Analytics unsubscribe action failed: {e}")
            return ActionResult(
                success=False,
                action_type="analytics_unsubscribe",
                data={},
                side_effects=side_effects,
                error=str(e)
            )

    async def _handle_analytics_request_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle analytics data request."""
        side_effects = []
        
        try:
            # Extract request parameters
            request_data = msg.get("data", {})
            start_date = request_data.get("start_date")
            end_date = request_data.get("end_date")
            
            # Record analytics request
            self.session_manager.update_activity(
                session_id,
                custom_data={
                    "last_analytics_request": _now_iso(),
                    "request_params": request_data
                }
            )
            side_effects.append("analytics_request_recorded")
            
            return ActionResult(
                success=True,
                action_type="analytics_request",
                data={
                    "request_accepted": True,
                    "session_id": session_id,
                    "request_params": request_data,
                    "requested_at": _now_iso()
                },
                side_effects=side_effects,
                metadata={"analytics_request": request_data}
            )
            
        except Exception as e:
            logger.error(f"[ACTION-PROC] Analytics request action failed: {e}")
            return ActionResult(
                success=False,
                action_type="analytics_request",
                data={},
                side_effects=side_effects,
                error=str(e)
            )

    async def _handle_prompts_request_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle prompts request action."""
        logger.info(f"🔍 [PROMPTS-DEBUG] Handler called for prompts_request | user={user_id} | session={session_id}")
        logger.info(f"🔍 [PROMPTS-DEBUG] Raw message: {msg}")

        try:
            from ..services.prompt_tracking_service import get_user_prompts_data

            request_data = msg.get("data", {})
            logger.info(f"🔍 [PROMPTS-DEBUG] Extracted request_data: {request_data}")

            org_id = self.config_manager.get_organization_id() if hasattr(self.config_manager, 'get_organization_id') else 'org_001'
            logger.info(f"🔍 [PROMPTS-DEBUG] Using org_id: {org_id}")

            # Get prompts data with database session
            from ..db.database import get_db
            from datetime import datetime

            # Parse datetime strings or use defaults
            start_date_str = request_data.get("start_date", "2024-01-01T00:00:00Z")
            end_date_str = request_data.get("end_date", datetime.now(timezone.utc).isoformat())
            logger.info(f"🔍 [PROMPTS-DEBUG] Date range: {start_date_str} to {end_date_str}")

            # Handle Z suffix for both dates (Python's fromisoformat doesn't support 'Z' directly)
            if start_date_str.endswith('Z'):
                start_date_str = start_date_str.replace('Z', '+00:00')
            if end_date_str.endswith('Z'):
                end_date_str = end_date_str.replace('Z', '+00:00')

            start_date = datetime.fromisoformat(start_date_str)
            end_date = datetime.fromisoformat(end_date_str)
            logger.info(f"🔍 [PROMPTS-DEBUG] Parsed dates: {start_date} to {end_date}")

            # Query parameters
            limit = request_data.get("limit", 50)
            offset = request_data.get("offset", 0)
            search_text = request_data.get("search_text")
            logger.info(f"🔍 [PROMPTS-DEBUG] Query params: limit={limit}, offset={offset}, search_text={search_text}, user_filter={user_id}")

            logger.info(f"🔍 [PROMPTS-DEBUG] Attempting database query...")
            async for db in get_db():
                logger.info(f"🔍 [PROMPTS-DEBUG] Database session obtained, calling get_user_prompts_data...")
                result = await get_user_prompts_data(
                    start_date=start_date,
                    end_date=end_date,
                    organization_id=org_id,
                    limit=limit,
                    offset=offset,
                    user_filter=user_id,  # Use session user_id instead of request user_filter
                    search_text=search_text,
                    db=db
                )
                logger.info(f"🔍 [PROMPTS-DEBUG] Query completed successfully, result type: {type(result)}")
                logger.info(f"🔍 [PROMPTS-DEBUG] Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
                if isinstance(result, dict):
                    if 'prompts' in result:
                        logger.info(f"🔍 [PROMPTS-DEBUG] Found {len(result['prompts'])} prompts in result")
                    if 'pagination' in result:
                        logger.info(f"🔍 [PROMPTS-DEBUG] Pagination info: {result['pagination']}")
                break  # Only need first iteration

            logger.info(f"✅ [PROMPTS-DEBUG] Prompts request completed successfully")
            return ActionResult(
                success=True,
                action_type="prompts_request",
                data=result,
                side_effects=[],
                metadata={"prompt_tracking_request": request_data}
            )

        except ImportError as import_err:
            logger.error(f"❌ [PROMPTS-DEBUG] Import error: {import_err}")
            return ActionResult(
                success=False,
                action_type="prompts_request",
                data={},
                side_effects=[],
                error=f"Service import failed: {str(import_err)}"
            )
        except Exception as e:
            logger.error(f"❌ [PROMPTS-DEBUG] Handler failed: {e}")
            logger.error(f"❌ [PROMPTS-DEBUG] Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ [PROMPTS-DEBUG] Traceback: {traceback.format_exc()}")
            return ActionResult(
                success=False,
                action_type="prompts_request",
                data={},
                side_effects=[],
                error=str(e)
            )

    async def _handle_prompt_detail_request_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle prompt detail request action."""
        try:
            from ..services.prompt_tracking_service import get_prompt_detail_data
            from ..db.database import get_db
            
            request_data = msg.get("data", {})
            message_id = request_data.get("message_id")
            org_id = self.config_manager.get_organization_id() if hasattr(self.config_manager, 'get_organization_id') else 'org_001'
            
            if not message_id:
                raise ValueError("message_id is required")
            
            # Get prompt detail data with database session
            async for db in get_db():
                result = await get_prompt_detail_data(
                    message_id=message_id,
                    organization_id=org_id,
                    db=db
                )
                break  # Only need first iteration
            
            return ActionResult(
                success=True,
                action_type="prompt_detail_request",
                data=result,
                side_effects=[],
                metadata={"message_id": message_id}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="prompt_detail_request",
                data={},
                side_effects=[],
                error=str(e)
            )

    async def _handle_prompts_subscribe_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle prompts subscription action."""
        try:
            from ..api.routes_websocket import analytics_subscribers
            
            # Add this session to prompts subscribers
            from ..api.routes_websocket import session_connections

            # Get the actual connection_id from session mapping
            connection_id = session_connections.get(session_id, session_id)

            if session_id not in analytics_subscribers:
                analytics_subscribers[session_id] = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "connection_id": connection_id,  # Use actual connection_id from mapping
                    "subscribed_at": datetime.now(timezone.utc).isoformat(),
                    "subscription_info": {},
                    "time_range": "30d"
                }
            
            # Mark as subscribed to prompts
            analytics_subscribers[session_id]["subscription_info"]["include_prompts"] = True
            
            return ActionResult(
                success=True,
                action_type="prompts_subscribe",
                data={
                    "subscribed": True,
                    "subscriber_count": len(analytics_subscribers)
                },
                side_effects=[],
                metadata={"subscription_type": "prompts"}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="prompts_subscribe",
                data={},
                side_effects=[],
                error=str(e)
            )

    async def _handle_prompts_export_action(self, msg: Dict[str, Any], user_id: str, session_id: str, current_state: SessionState) -> ActionResult:
        """Handle prompts export action."""
        try:
            from ..services.prompt_tracking_service import export_prompts_data
            from ..db.database import get_db
            
            request_data = msg.get("data", {})
            org_id = self.config_manager.get_organization_id() if hasattr(self.config_manager, 'get_organization_id') else 'org_001'
            
            # Export prompts data with database session
            async for db in get_db():
                result = await export_prompts_data(
                    organization_id=org_id,
                    format=request_data.get("format", "csv"),
                    filters=request_data.get("filters", {}),
                    db=db
                )
                break  # Only need first iteration
            
            return ActionResult(
                success=True,
                action_type="prompts_export",
                data=result,
                side_effects=[],
                metadata={"export_format": request_data.get("format", "csv")}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                action_type="prompts_export", 
                data={},
                side_effects=[],
                error=str(e)
            )

# Global action processor instance will be created with dependencies
_action_processor_instance = None

def get_action_processor(buffer_manager=None, config_manager=None) -> SessionActionProcessor:
    """Get action processor instance with dependencies."""
    global _action_processor_instance
    
    if _action_processor_instance is None:
        _action_processor_instance = SessionActionProcessor(buffer_manager, config_manager)
    
    return _action_processor_instance

def reset_action_processor():
    """Reset global instance (for testing)."""
    global _action_processor_instance
    _action_processor_instance = None

__all__ = [
    "ActionResult",
    "SessionActionProcessor", 
    "get_action_processor",
    "reset_action_processor"
]
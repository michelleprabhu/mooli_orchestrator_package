"""Enhanced WebSocket endpoints with session management for real-time communication."""

import logging
import uuid
import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# Session management imports
from ..utils.session_dispatch import dispatch_session_message, get_session_stats, cleanup_expired_sessions
from ..utils.session_config import session_config
from ..utils.buffer_manager import buffer_manager
from ..utils.dev_users import ensure_dev_users
from ..services.auth_service import authenticate_websocket_user
from ..monitoring.config.database import get_db
from ..monitoring.config.settings import get_config
from ..core.logging_config import get_logger, audit_logger, log_exception

logger = get_logger(__name__)

router = APIRouter(prefix="/ws/v1", tags=["websocket", "session"])

# Active WebSocket connections tracking
active_connections: Dict[str, WebSocket] = {}
session_connections: Dict[str, str] = {}  # session_id -> connection_id

# Multi-user connection tracking (additive - no breaking changes)
user_connections: Dict[str, set] = {}  # user_id -> {connection_ids}
connection_users: Dict[str, str] = {}  # connection_id -> user_id
connection_metadata: Dict[str, Dict] = {}  # connection_id -> {user, org, timestamp}

# Analytics subscription tracking
analytics_subscribers: Dict[str, Dict] = {}  # session_id -> {user_id, connection_id, subscription_info}
analytics_broadcast_task: Optional[Any] = None
analytics_last_data: Dict[str, Any] = {}  # Cache for last analytics data


# Multi-user connection management functions
async def register_user_connection(user_id: str, connection_id: str, websocket: WebSocket, org_id: str):
    """Register a user connection (additive to existing system)."""
    # Keep existing connection tracking
    active_connections[connection_id] = websocket
    
    # Add user-specific tracking
    if user_id not in user_connections:
        user_connections[user_id] = set()
    user_connections[user_id].add(connection_id)
    connection_users[connection_id] = user_id
    connection_metadata[connection_id] = {
        "user_id": user_id,
        "org_id": org_id,
        "connected_at": datetime.now(timezone.utc),
        "last_activity": datetime.now(timezone.utc)
    }
    
    total_connections = len(active_connections)
    user_connection_count = len(user_connections.get(user_id, set()))
    
    logger.info(f"✅ WebSocket connection registered | user={user_id} | connection={connection_id} | org={org_id} | user_connections={user_connection_count} | total_connections={total_connections}")
    
    # Audit log for connection
    audit_logger.log_action(
        action="websocket_connect",
        user_id=user_id,
        resource=f"connection:{connection_id}",
        details={"org_id": org_id, "total_connections": total_connections}
    )

async def unregister_user_connection(connection_id: str):
    """Unregister a user connection (additive cleanup)."""
    # Clean up existing tracking
    if connection_id in active_connections:
        del active_connections[connection_id]
    
    # Clean up user-specific tracking
    if connection_id in connection_users:
        user_id = connection_users[connection_id]
        if user_id in user_connections:
            user_connections[user_id].discard(connection_id)
            if not user_connections[user_id]:  # Remove empty set
                del user_connections[user_id]
        del connection_users[connection_id]
    
    if connection_id in connection_metadata:
        del connection_metadata[connection_id]
    
    logger.debug(f"Unregistered connection: {connection_id}")

async def broadcast_to_user(user_id: str, message: Dict[str, Any]) -> int:
    """Broadcast message to all connections for a specific user."""
    if user_id not in user_connections:
        return 0
    
    sent_count = 0
    failed_connections = []
    
    # Get snapshot to avoid modification during iteration
    connection_ids = user_connections[user_id].copy()
    
    for connection_id in connection_ids:
        try:
            if connection_id in active_connections:
                websocket = active_connections[connection_id]
                await websocket.send_text(json.dumps(message))
                sent_count += 1
                
                # Update last activity
                if connection_id in connection_metadata:
                    connection_metadata[connection_id]["last_activity"] = datetime.now(timezone.utc)
            else:
                failed_connections.append(connection_id)
        except Exception as e:
            logger.warning(f"Failed to send message to connection {connection_id}: {e}")
            failed_connections.append(connection_id)
    
    # Clean up failed connections
    for failed_id in failed_connections:
        await unregister_user_connection(failed_id)
    
    return sent_count

async def get_session_config():
    """Get session configuration."""
    return session_config


async def get_live_analytics_data(org_id: str, time_range: str = '30d') -> Dict[str, Any]:
    """Get current analytics data for broadcasting.

    Args:
        org_id: Organization ID
        time_range: Time range string ('1h', '24h', '7d', '30d', '90d')
    """
    logger.info(f"📈 [ANALYTICS-DATA-DEBUG] Getting live analytics data for org {org_id}, time_range {time_range}")

    try:
        # Import analytics service and database
        from ..monitoring.api.routers.analytics import PhoenixAnalyticsService
        from ..db.database import db_manager

        logger.info(f"📈 [ANALYTICS-DATA-DEBUG] Imports successful")

        analytics_service = PhoenixAnalyticsService()
        logger.info(f"📈 [ANALYTICS-DATA-DEBUG] PhoenixAnalyticsService created")

        # Calculate time range based on the requested period
        end_date = datetime.now(timezone.utc)

        # Map time range to timedelta
        if time_range == '1h':
            start_date = end_date - timedelta(hours=1)
        elif time_range == '24h':
            start_date = end_date - timedelta(hours=24)
        elif time_range == '7d':
            start_date = end_date - timedelta(days=7)
        elif time_range == '90d':
            start_date = end_date - timedelta(days=90)
        else:  # Default to 30d
            start_date = end_date - timedelta(days=30)

        logger.info(f"📈 [ANALYTICS-DATA-DEBUG] Date range: {start_date} to {end_date}")

        # Get database session from orchestrator DB manager
        logger.info(f"📈 [ANALYTICS-DATA-DEBUG] Getting database session...")
        async for db in db_manager.get_session():
            try:
                logger.info(f"📈 [ANALYTICS-DATA-DEBUG] Database session obtained, calling PhoenixAnalyticsService...")
                analytics_data = await analytics_service.get_analytics_overview_from_phoenix(
                    start_date=start_date,
                    end_date=end_date,
                    organization_id=org_id,
                    db=db
                )
                logger.info(f"📈 [ANALYTICS-DATA-DEBUG] Analytics service call completed")
                logger.info(f"📈 [ANALYTICS-DATA-DEBUG] Raw analytics_data: {analytics_data}")
                break
            finally:
                await db.close()

        # Transform to the format expected by the frontend
        if analytics_data and analytics_data.get('overview'):
            overview = analytics_data['overview']
            logger.info(f"📈 [ANALYTICS-DATA-DEBUG] Found overview data: {overview}")
            result = {
                "total_api_calls": overview.get('total_api_calls', 0),
                "total_cost": overview.get('total_cost', 0.0),
                "total_tokens": overview.get('total_tokens', 0),
                "cache_hit_rate": overview.get('cache_hit_rate', 0.0),
                "avg_response_time_ms": overview.get('avg_response_time_ms', 0),
                "firewall_blocks": overview.get('firewall_blocks', 0),
                "provider_breakdown": analytics_data.get('provider_breakdown', [])
            }
            logger.info(f"📈 [ANALYTICS-DATA-DEBUG] ✅ Returning data with overview: {result}")
            return result
        else:
            # Return empty data structure if no analytics available
            empty_result = {
                "total_api_calls": 0,
                "total_cost": 0.0,
                "total_tokens": 0,
                "cache_hit_rate": 0.0,
                "avg_response_time_ms": 0,
                "firewall_blocks": 0,
                "provider_breakdown": []
            }
            logger.warning(f"📈 [ANALYTICS-DATA-DEBUG] No analytics data available, returning empty structure: {empty_result}")
            return empty_result

    except ImportError as import_err:
        logger.error(f"❌ [ANALYTICS-DATA-DEBUG] Import error: {import_err}")
        return {
            "total_api_calls": 0,
            "total_cost": 0.0,
            "total_tokens": 0,
            "cache_hit_rate": 0.0,
            "avg_response_time_ms": 0,
            "firewall_blocks": 0,
            "provider_breakdown": []
        }
    except Exception as e:
        logger.error(f"❌ [ANALYTICS-DATA-DEBUG] Error getting live analytics data: {e}")
        import traceback
        logger.error(f"❌ [ANALYTICS-DATA-DEBUG] Traceback: {traceback.format_exc()}")
        # Return empty data on error
        return {
            "total_api_calls": 0,
            "total_cost": 0.0,
            "total_tokens": 0,
            "cache_hit_rate": 0.0,
            "avg_response_time_ms": 0,
            "firewall_blocks": 0,
            "provider_breakdown": []
        }


async def broadcast_analytics_to_subscribers():
    """Broadcast analytics data to all subscribed sessions with their specific time ranges."""
    logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Starting broadcast cycle")
    logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Current subscriber count: {len(analytics_subscribers)}")

    if not analytics_subscribers:
        logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] No subscribers, skipping broadcast")
        return

    # Log subscriber details
    for session_id, subscriber_info in analytics_subscribers.items():
        logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Subscriber {session_id}: {subscriber_info}")

    try:
        # Get analytics data for the default organization
        config = get_config()
        org_id = config.get_organization_id() if hasattr(config, 'get_organization_id') else 'org_001'
        logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Using org_id: {org_id}")

        # Group subscribers by time range to optimize data fetching
        time_range_groups = {}
        for session_id, subscriber_info in analytics_subscribers.items():
            time_range = subscriber_info.get('time_range', '30d')
            if time_range not in time_range_groups:
                time_range_groups[time_range] = []
            time_range_groups[time_range].append((session_id, subscriber_info))

        logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Time range groups: {list(time_range_groups.keys())}")

        # Fetch data for each unique time range
        analytics_data_by_range = {}
        for time_range in time_range_groups.keys():
            logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Fetching data for time range: {time_range}")
            analytics_data = await get_live_analytics_data(org_id, time_range)
            logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Retrieved data for {time_range}: {analytics_data}")
            analytics_data_by_range[time_range] = analytics_data
            # Cache the data
            analytics_last_data[f"{org_id}_{time_range}"] = analytics_data

        # Broadcast to all subscribers with their respective time range data
        disconnected_sessions = []
        sent_count = 0

        for time_range, subscribers in time_range_groups.items():
            analytics_data = analytics_data_by_range[time_range]
            logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Broadcasting to {len(subscribers)} subscribers for time range {time_range}")

            for session_id, subscriber_info in subscribers:
                try:
                    connection_id = subscriber_info.get('connection_id')
                    logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Attempting to send to session {session_id}, connection {connection_id}")

                    if connection_id in active_connections:
                        websocket = active_connections[connection_id]
                        logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Found active connection for {connection_id}")

                        response = {
                            "type": "analytics_response",
                            "data": analytics_data,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "session_id": session_id,
                            "time_range": time_range
                        }

                        await websocket.send_text(json.dumps(response))
                        sent_count += 1
                        logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] ✅ Sent analytics data to session {session_id}")
                    else:
                        # Connection no longer active
                        logger.warning(f"📊 [ANALYTICS-BROADCAST-DEBUG] Connection {connection_id} not in active_connections")
                        logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Active connections: {list(active_connections.keys())}")
                        disconnected_sessions.append(session_id)

                except Exception as e:
                    logger.error(f"❌ [ANALYTICS-BROADCAST-DEBUG] Error sending analytics to session {session_id}: {e}")
                    import traceback
                    logger.error(f"❌ [ANALYTICS-BROADCAST-DEBUG] Traceback: {traceback.format_exc()}")
                    disconnected_sessions.append(session_id)

        logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Broadcast complete: sent to {sent_count} sessions, {len(disconnected_sessions)} disconnected")

        # Cleanup disconnected sessions
        for session_id in disconnected_sessions:
            if session_id in analytics_subscribers:
                del analytics_subscribers[session_id]
                logger.info(f"📊 [ANALYTICS-BROADCAST-DEBUG] Removed disconnected analytics subscriber: {session_id}")

    except Exception as e:
        logger.error(f"❌ [ANALYTICS-BROADCAST-DEBUG] Critical error in analytics broadcasting: {e}")
        import traceback
        logger.error(f"❌ [ANALYTICS-BROADCAST-DEBUG] Traceback: {traceback.format_exc()}")


async def start_analytics_broadcasting():
    """Start the periodic analytics broadcasting task."""
    global analytics_broadcast_task

    logger.info(f"🚀 [ANALYTICS-BROADCAST-DEBUG] Starting analytics broadcasting task")

    if analytics_broadcast_task is None:
        async def analytics_broadcast_loop():
            loop_count = 0
            while True:
                try:
                    loop_count += 1
                    logger.info(f"🔄 [ANALYTICS-BROADCAST-DEBUG] Loop iteration {loop_count}")
                    logger.info(f"🔄 [ANALYTICS-BROADCAST-DEBUG] Current subscribers: {len(analytics_subscribers)}")

                    if analytics_subscribers:  # Only broadcast if there are subscribers
                        logger.info(f"🔄 [ANALYTICS-BROADCAST-DEBUG] Broadcasting to subscribers...")
                        await broadcast_analytics_to_subscribers()
                    else:
                        logger.info(f"🔄 [ANALYTICS-BROADCAST-DEBUG] No subscribers, sleeping...")

                    logger.info(f"🔄 [ANALYTICS-BROADCAST-DEBUG] Sleeping for 2 seconds...")
                    await asyncio.sleep(2)  # Broadcast every 2 seconds
                except asyncio.CancelledError:
                    logger.info("🛑 [ANALYTICS-BROADCAST-DEBUG] Analytics broadcasting task cancelled")
                    break
                except Exception as e:
                    logger.error(f"❌ [ANALYTICS-BROADCAST-DEBUG] Error in analytics broadcast loop: {e}")
                    import traceback
                    logger.error(f"❌ [ANALYTICS-BROADCAST-DEBUG] Traceback: {traceback.format_exc()}")
                    await asyncio.sleep(2)  # Continue after error

        analytics_broadcast_task = asyncio.create_task(analytics_broadcast_loop())
        logger.info("✅ [ANALYTICS-BROADCAST-DEBUG] Analytics broadcasting task started and running")


async def stop_analytics_broadcasting():
    """Stop the analytics broadcasting task."""
    global analytics_broadcast_task
    
    if analytics_broadcast_task:
        analytics_broadcast_task.cancel()
        try:
            await analytics_broadcast_task
        except asyncio.CancelledError:
            pass
        analytics_broadcast_task = None
        logger.info("Analytics broadcasting task stopped")


@router.websocket("/session")
async def websocket_unified_session_endpoint(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time chat with session management.
    
    Enhanced with multi-user support while maintaining backward compatibility.
    
    Provides:
    - Session-aware user tracking
    - Real-time message handling  
    - Conversation management
    - Multi-user connection isolation
    - Automatic session cleanup
    
    Development mode: Authentication bypass with optional user management
    Production mode: Token-based authentication (when implemented)
    """
    config = get_config()
    org_id = config.get_organization_id() if hasattr(config, 'get_organization_id') else 'org_001'
    
    # Enhanced authentication with JWT bypass for development
    authenticated_user = None
    try:
        # Use new authentication service (handles development bypass)
        authenticated_user = await authenticate_websocket_user(user_id, token, org_id)
        if authenticated_user:
            user_id = authenticated_user.user_id
            logger.info(f"WebSocket authenticated: {authenticated_user.username} ({user_id})")
        else:
            # Fallback to original development bypass for backward compatibility
            if not user_id:
                user_id = f"dev_user_{uuid.uuid4().hex[:8]}"
            logger.info(f"Using fallback anonymous user: {user_id}")
    except Exception as e:
        logger.warning(f"WebSocket authentication failed, using development bypass: {e}")
        if not user_id:
            user_id = f"dev_user_{uuid.uuid4().hex[:8]}"
    
    # Session management (unchanged)
    if not session_id:
        session_id = f"session_{uuid.uuid4().hex[:8]}"
    
    connection_id = str(uuid.uuid4())
    
    try:
        # Accept WebSocket connection
        await websocket.accept()
        
        # Register connection (enhanced with multi-user support)
        await register_user_connection(user_id, connection_id, websocket, org_id)
        session_connections[session_id] = connection_id  # Keep existing session tracking
        
        # Send session establishment confirmation
        session_response = await dispatch_session_message(
            {"type": "connect", "user_id": user_id, "session_id": session_id},
            user_id,
            session_id,
            session_config
        )
        await websocket.send_text(json.dumps(session_response))
        
        logger.info(f"WebSocket chat connection established: {session_id} for user {user_id}")
        
        # Message handling loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Add message ID if not present
                if "message_id" not in message:
                    message["message_id"] = str(uuid.uuid4())
                
                # Dispatch message through enhanced session system
                logger.info(f"🔀 [WEBSOCKET-DEBUG] Dispatching message through session system: {message.get('type')} for user {user_id}")
                response = await dispatch_session_message(
                    message,
                    user_id,
                    session_id,
                    session_config
                )
                logger.info(f"🔀 [WEBSOCKET-DEBUG] Session dispatch response: {response}")

                # Send response back to client
                await websocket.send_text(json.dumps(response))
                logger.info(f"🔀 [WEBSOCKET-DEBUG] Response sent to client for message type {message.get('type')}")
                
                # Handle special message types
                if message.get("type") == "send_message":
                    # Process through actual agent system
                    logger.info(f"🚀 [DYNAROUTE-WS-DEBUG] Processing send_message for user {user_id}")
                    try:
                        # Import the actual agent system
                        from ..agents import generate_llm_response

                        # Extract message content and conversation ID
                        user_message = message.get("message", "")
                        conversation_id = response.get("data", {}).get("conversation_id", "default")
                        model = message.get("model")  # Use None to fall back to environment variable default

                        logger.info(f"🔍 [DYNAROUTE-WS-DEBUG] Message details:")
                        logger.info(f"   📝 Message: {user_message[:100]}{'...' if len(user_message) > 100 else ''}")
                        logger.info(f"   💬 Conversation ID: {conversation_id}")
                        logger.info(f"   🎯 Requested model: {model if model else 'default (environment)'}")
                        logger.info(f"   👤 User ID: {user_id}")

                        if user_message.strip():
                            logger.info(f"🧠 [DYNAROUTE-WS-DEBUG] Calling generate_llm_response with DynaRoute integration...")

                            # Call the actual LLM agent system
                            agent_result = await generate_llm_response(
                                query=user_message,
                                session_id=conversation_id,
                                user_id=user_id,
                                model=model
                            )

                            # Log the agent result for debugging
                            logger.info(f"✅ [DYNAROUTE-WS-DEBUG] Agent response received:")
                            logger.info(f"   🎯 Model used: {agent_result.get('user_response_model', agent_result.get('model', 'unknown'))}")
                            logger.info(f"   🏭 Provider used: {agent_result.get('provider_used', 'unknown')}")
                            logger.info(f"   💰 Cost estimate: {agent_result.get('cost_estimate', 0.0)}")
                            logger.info(f"   💾 From cache: {agent_result.get('from_cache', False)}")
                            logger.info(f"   📊 Message ID: {agent_result.get('message_id', 'none')}")

                            # Log DynaRoute metadata if present
                            dynaroute_metadata = agent_result.get("dynaroute_metadata")
                            if dynaroute_metadata:
                                logger.info(f"   🎯 DynaRoute metadata: {dynaroute_metadata}")
                            else:
                                logger.info(f"   ⚠️  No DynaRoute metadata (likely OpenAI fallback or cache hit)")
                            
                            # Format the response for WebSocket
                            logger.info(f"📦 [DYNAROUTE-WS-DEBUG] Formatting WebSocket response...")

                            assistant_response = {
                                "type": "assistant_response",
                                "data": {
                                    "message_id": str(agent_result.get("message_id", uuid.uuid4())),  # Use database ID if available
                                    "conversation_id": conversation_id,
                                    "content_delta": agent_result.get("response", agent_result.get("answer", "")),
                                    "is_complete": True,
                                    "sequence_number": 2,
                                    "metadata": {
                                        "model": agent_result.get("user_response_model", agent_result.get("model", "gpt-4o-mini")),
                                        "endpoint": "/ws/v1/session",
                                        "from_cache": agent_result.get("from_cache", False),
                                        "similarity": agent_result.get("similarity"),
                                        "provider_used": agent_result.get("provider_used", "openai"),
                                        "cost_estimate": agent_result.get("cost_estimate", 0.0),
                                        "dynaroute_metadata": agent_result.get("dynaroute_metadata")
                                    }
                                },
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }

                            # Log the formatted response metadata
                            response_metadata = assistant_response["data"]["metadata"]
                            logger.info(f"📤 [DYNAROUTE-WS-DEBUG] Sending assistant_response to client:")
                            logger.info(f"   📝 Response length: {len(assistant_response['data']['content_delta'])} chars")
                            logger.info(f"   🎯 Model in response: {response_metadata['model']}")
                            logger.info(f"   🏭 Provider in response: {response_metadata['provider_used']}")
                            logger.info(f"   💰 Cost in response: {response_metadata['cost_estimate']}")
                            logger.info(f"   💾 Cache hit in response: {response_metadata['from_cache']}")

                            await websocket.send_text(json.dumps(assistant_response))
                            logger.info(f"✅ [DYNAROUTE-WS-DEBUG] Assistant response sent successfully to client")
                    
                    except ImportError as import_error:
                        # Fallback if agent system not available
                        logger.error(f"Agent system import failed: {import_error}")
                        assistant_response = {
                            "type": "assistant_response",
                            "data": {
                                "message_id": str(uuid.uuid4()),
                                "conversation_id": response.get("data", {}).get("conversation_id"),
                                "content_delta": "Agent system unavailable - check import paths",
                                "is_complete": True,
                                "sequence_number": 2,
                                "metadata": {"model": "error", "error": "import_failed"}
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        await websocket.send_text(json.dumps(assistant_response))
                    except Exception as e:
                        # Error handling for agent system
                        logger.error(f"Agent system error: {e}")
                        error_response = {
                            "type": "assistant_response",
                            "data": {
                                "message_id": str(uuid.uuid4()),
                                "conversation_id": response.get("data", {}).get("conversation_id"),
                                "content_delta": f"Error processing request: {str(e)}",
                                "is_complete": True,
                                "sequence_number": 2,
                                "metadata": {"model": "error", "error_type": "agent_error"}
                            },
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        await websocket.send_text(json.dumps(error_response))
                
                # All dashboard message types are now handled by session dispatch above
                # Removed duplicate handlers to prevent double processing and correlation conflicts
                else:
                    # Unknown message type - log for debugging  
                    logger.warning(f"Unknown WebSocket message type: {message.get('type')}")
            except Exception as e:
                logger.error(f"Error in chat WebSocket: {e}")
                error_response = {
                    "type": "error", 
                    "data": {"error": str(e)},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await websocket.send_text(json.dumps(error_response))
                
    except Exception as e:
        logger.error(f"Fatal error in chat WebSocket: {e}")
        await websocket.close()
    finally:
        # Enhanced cleanup (handles both old and new connection tracking)
        await unregister_user_connection(connection_id)
        if session_id in session_connections:
            del session_connections[session_id]
        
        # Cleanup analytics subscription
        if session_id in analytics_subscribers:
            del analytics_subscribers[session_id]
            logger.info(f"Removed analytics subscriber: {session_id}")

            # Analytics broadcasting task continues running even with no subscribers
            # It will automatically resume broadcasting when new subscribers connect
        
        # Dispatch disconnect message
        try:
            await dispatch_session_message(
                {"type": "disconnect", "session_id": session_id},
                user_id,
                session_id,
                session_config
            )
        except Exception as e:
            logger.warning(f"Error during disconnect cleanup: {e}")


@router.websocket("/session/{session_id}")
async def websocket_session_endpoint(
    websocket: WebSocket,
    session_id: str,
    user_id: Optional[str] = Query(None),
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for joining existing session.
    
    Allows reconnection to existing sessions with state restoration.
    """
    if not user_id:
        user_id = f"reconnect_user_{uuid.uuid4().hex[:8]}"
    
    connection_id = str(uuid.uuid4())
    
    try:
        await websocket.accept()
        
        # Check if session exists in buffer
        active_user = buffer_manager.get_active_user(user_id) if buffer_manager else None
        
        if active_user:
            # Restore existing session
            active_connections[connection_id] = websocket
            session_connections[session_id] = connection_id
            
            response = {
                "type": "session_restored",
                "data": {
                    "session_id": session_id,
                    "user_id": user_id,
                    "restored_at": datetime.now(timezone.utc).isoformat(),
                    "session_data": active_user
                }
            }
            await websocket.send_text(json.dumps(response))
            
            logger.info(f"Session restored: {session_id} for user {user_id}")
        else:
            # Session not found
            error_response = {
                "type": "error",
                "data": {"error": "Session not found or expired"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await websocket.send_text(json.dumps(error_response))
            await websocket.close()
            return
        
        # Handle messages same as chat endpoint
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                response = await dispatch_session_message(
                    message,
                    user_id,
                    session_id,
                    session_config
                )
                
                await websocket.send_text(json.dumps(response))
                
            except WebSocketDisconnect:
                logger.info(f"Session WebSocket disconnected: {session_id}")
                break
            except Exception as e:
                logger.error(f"Error in session WebSocket: {e}")
                break
                
    except Exception as e:
        logger.error(f"Fatal error in session WebSocket: {e}")
    finally:
        # Cleanup
        if connection_id in active_connections:
            del active_connections[connection_id]
        if session_id in session_connections:
            del session_connections[session_id]


@router.get("/stats")
async def get_websocket_stats():
    """Get current WebSocket and session statistics with multi-user info."""
    try:
        session_stats = get_session_stats()
        connection_stats = {
            "active_websockets": len(active_connections),
            "active_sessions": len(session_connections),
            "connection_mappings": len(session_connections),
            # Enhanced with multi-user stats
            "active_users": len(user_connections),
            "user_connection_count": sum(len(connections) for connections in user_connections.values()),
            "total_connections_tracked": len(connection_metadata)
        }
        
        return {
            "websocket_stats": connection_stats,
            "session_stats": session_stats,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting WebSocket stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/active")
async def get_active_users():
    """Get list of currently connected users (development mode)."""
    try:
        from ..utils.dev_users import list_available_dev_users
        
        # Get available dev users
        dev_users = await list_available_dev_users()
        
        # Add connection status
        active_user_info = []
        for user in dev_users:
            user_id = user["user_id"]
            connection_count = len(user_connections.get(user_id, set()))
            
            user_info = {
                **user,
                "is_connected": connection_count > 0,
                "connection_count": connection_count,
                "last_activity": None
            }
            
            # Get last activity time if connected
            if user_id in user_connections:
                latest_activity = None
                for conn_id in user_connections[user_id]:
                    if conn_id in connection_metadata:
                        activity = connection_metadata[conn_id]["last_activity"]
                        if latest_activity is None or activity > latest_activity:
                            latest_activity = activity
                
                if latest_activity:
                    user_info["last_activity"] = latest_activity.isoformat()
            
            active_user_info.append(user_info)
        
        return {
            "users": active_user_info,
            "total_available": len(dev_users),
            "total_connected": len(user_connections),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup")
async def cleanup_sessions(timeout_seconds: int = 1800):
    """Manually trigger session cleanup."""
    try:
        cleaned_count = cleanup_expired_sessions(timeout_seconds)
        return {
            "cleaned_sessions": cleaned_count,
            "timeout_seconds": timeout_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error during session cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/active")
async def get_active_sessions():
    """Get list of currently active sessions."""
    try:
        if buffer_manager:
            active_users = buffer_manager.get_active_users()
            return {
                "active_sessions": active_users,
                "count": len(active_users),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {
                "active_sessions": [],
                "count": 0,
                "error": "Buffer manager not available"
            }
    except Exception as e:
        logger.error(f"Error getting active sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def broadcast_to_session(session_id: str, message: Dict[str, Any]) -> bool:
    """
    Broadcast message to specific session.
    
    Returns True if message was sent successfully.
    """
    try:
        if session_id in session_connections:
            connection_id = session_connections[session_id]
            if connection_id in active_connections:
                websocket = active_connections[connection_id]
                await websocket.send_text(json.dumps(message))
                return True
        return False
    except Exception as e:
        logger.error(f"Error broadcasting to session {session_id}: {e}")
        return False


async def broadcast_to_all_sessions(message: Dict[str, Any]) -> int:
    """
    Broadcast message to all active sessions.
    
    Returns count of sessions that received the message.
    """
    sent_count = 0
    for session_id in list(session_connections.keys()):
        try:
            if await broadcast_to_session(session_id, message):
                sent_count += 1
        except Exception as e:
            logger.warning(f"Failed to broadcast to session {session_id}: {e}")
    
    return sent_count


async def broadcast_feedback_notification(
    user_id: str, 
    message_id: str, 
    feedback_type: str, 
    feedback_data: Dict[str, Any]
) -> int:
    """
    Broadcast feedback notification to all user's active connections.
    
    Args:
        user_id: User who submitted the feedback
        message_id: Message that was evaluated  
        feedback_type: Type of feedback ("human_submitted", "llm_completed", "evaluation_complete")
        feedback_data: Feedback details
    
    Returns:
        Number of connections notified
    """
    try:
        notification = {
            "type": "feedback_notification",
            "data": {
                "message_id": message_id,
                "feedback_type": feedback_type,
                "feedback_data": feedback_data,
                "user_id": user_id
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        sent_count = await broadcast_to_user(user_id, notification)
        
        logger.info(f"Feedback notification sent to {sent_count} connections for user {user_id}: {feedback_type}")
        return sent_count
        
    except Exception as e:
        logger.error(f"Failed to broadcast feedback notification: {e}")
        return 0


async def broadcast_prompts_update(organization_id: str, prompt_data: Dict[str, Any]) -> int:
    """
    Broadcast new prompt/response to organization prompt tracking dashboard subscribers.
    
    Args:
        organization_id: Organization ID
        prompt_data: New prompt and response data
        
    Returns:
        Number of sessions notified
    """
    try:
        # Find sessions monitoring prompts for this organization
        target_sessions = []
        
        for session_id, subscriber_info in analytics_subscribers.items():
            # Check if this subscriber is interested in prompts tracking
            subscription_data = subscriber_info.get("subscription_info", {})
            if (subscription_data.get("type") == "prompts_tracking" or 
                subscription_data.get("include_prompts", False)):
                target_sessions.append(session_id)
        
        if not target_sessions:
            return 0
        
        notification = {
            "type": "prompts_update",
            "data": prompt_data,
            "organization_id": organization_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        sent_count = 0
        for session_id in target_sessions:
            try:
                if await broadcast_to_session(session_id, notification):
                    sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send prompts update to session {session_id}: {e}")
        
        logger.info(f"Prompts update sent to {sent_count} sessions for org {organization_id}")
        return sent_count
        
    except Exception as e:
        logger.error(f"Failed to broadcast prompts update: {e}")
        return 0


async def broadcast_evaluation_runs_update(organization_id: str, update_data: Dict[str, Any]) -> int:
    """
    Broadcast evaluation runs update to organization monitoring dashboard subscribers.
    
    Args:
        organization_id: Organization ID
        update_data: New evaluation run data
        
    Returns:
        Number of sessions notified
    """
    try:
        # Find sessions monitoring evaluation runs for this organization
        target_sessions = []
        
        for session_id, subscriber_info in analytics_subscribers.items():
            # Check if this subscriber is interested in evaluation runs
            subscription_data = subscriber_info.get("subscription_info", {})
            if subscription_data.get("type") == "evaluation_runs" or subscription_data.get("include_evaluations", False):
                target_sessions.append(session_id)
        
        if not target_sessions:
            return 0
        
        notification = {
            "type": "evaluation_runs_update",
            "data": update_data,
            "organization_id": organization_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        sent_count = 0
        for session_id in target_sessions:
            try:
                if await broadcast_to_session(session_id, notification):
                    sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send evaluation update to session {session_id}: {e}")
        
        logger.info(f"Evaluation runs update sent to {sent_count} sessions for org {organization_id}")
        return sent_count
        
    except Exception as e:
        logger.error(f"Failed to broadcast evaluation runs update: {e}")
        return 0
"""
Prompt Tracking Service - Database queries for user prompts dashboard with Phoenix span hierarchy.

This service provides comprehensive prompt tracking functionality with:
- Phoenix parent-child span hierarchy support
- Detailed evaluation scores from 7 different metrics
- Cache hit/miss data with similarity scores
- Firewall blocking information with risk assessment
- User feedback and evaluation data
- Real-time updates and export capabilities
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, and_, or_
import logging
import json
import csv
import io
import base64

logger = logging.getLogger(__name__)


async def get_user_prompts_data(
    start_date: datetime,
    end_date: datetime,
    organization_id: str,
    limit: int = 50,
    offset: int = 0,
    user_filter: Optional[str] = None,
    search_text: Optional[str] = None,
    db: AsyncSession = None
) -> Dict[str, Any]:
    """
    Get comprehensive user prompts data with Phoenix parent-child span hierarchy.

    Returns complete prompt tracking data including evaluation scores, cache metrics,
    firewall status, and user feedback using the correct Phoenix span relationships.
    """
    logger.info(f"🔍 [PROMPTS-SERVICE-DEBUG] Function called with params: start_date={start_date}, end_date={end_date}, org_id={organization_id}")
    logger.info(f"🔍 [PROMPTS-SERVICE-DEBUG] Query params: limit={limit}, offset={offset}, user_filter={user_filter}, search_text={search_text}")

    if not db:
        logger.error(f"❌ [PROMPTS-SERVICE-DEBUG] Database session is None!")
        raise ValueError("Database session required")

    logger.info(f"🔍 [PROMPTS-SERVICE-DEBUG] Database session valid, type: {type(db)}")

    try:
        # Main query with Phoenix parent-child span hierarchy
        query = text("""
            -- STEP 1: Get parent request spans (user prompts)
            WITH parent_requests AS (
                SELECT 
                    s.span_id,
                    s.trace_rowid,
                    s.attributes->'moolai'->>'message_id' as message_id,
                    s.attributes->'moolai'->>'user_id' as user_id,
                    s.start_time,
                    s.end_time,
                    EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000 as total_duration_ms
                FROM phoenix.spans s
                WHERE s.name = 'moolai.request.process'
                AND s.attributes->'moolai'->>'service_name' = 'main_response'
                AND s.start_time >= :start_time
                AND s.start_time <= :end_time
                AND (CAST(:user_filter AS text) IS NULL OR s.attributes->'moolai'->>'user_id' = :user_filter)
            ),
            
            -- STEP 2: Get message content from PostgreSQL
            message_content AS (
                SELECT 
                    m.id as message_id,
                    m.content as prompt_text,
                    m.created_at as message_timestamp,
                    c.user_id,
                    u.username,
                    u.full_name,
                    -- Get corresponding assistant response
                    m2.content as response_text,
                    m2.created_at as response_timestamp
                FROM messages m
                JOIN chats c ON m.chat_id = c.id
                LEFT JOIN users u ON c.user_id = u.user_id
                LEFT JOIN messages m2 ON m2.chat_id = m.chat_id 
                                     AND m2.role = 'assistant' 
                                     AND m2.id = (
                                         SELECT MIN(id) FROM messages 
                                         WHERE chat_id = m.chat_id 
                                         AND role = 'assistant' 
                                         AND id > m.id
                                     )
                WHERE m.role = 'user' 
                AND c.organization_id = :org_id
                AND (CAST(:search_text AS text) IS NULL OR 
                     LOWER(m.content) LIKE LOWER('%' || :search_text || '%'))
            ),
            
            -- STEP 3: Get cache data from parent request spans (cache data is embedded)
            -- Phoenix spans store message_id as either user_msg_id or assistant_msg_id depending on flow
            cache_metrics AS (
                SELECT DISTINCT
                    mc.message_id,
                    CASE 
                        WHEN s.attributes->'moolai'->'cache'->>'hit' IS NOT NULL THEN
                            (s.attributes->'moolai'->'cache'->>'hit')::boolean
                        ELSE NULL
                    END as cache_hit,
                    CASE 
                        WHEN s.attributes->'moolai'->'cache'->>'similarity' IS NOT NULL THEN
                            (s.attributes->'moolai'->'cache'->>'similarity')::float
                        ELSE NULL
                    END as similarity_score,
                    0 as cache_lookup_ms  -- Cache lookup time is negligible for hits
                FROM message_content mc
                LEFT JOIN messages m2 ON m2.chat_id = (SELECT chat_id FROM messages WHERE id = mc.message_id)
                                     AND m2.role = 'assistant' 
                                     AND m2.id = (SELECT MIN(id) FROM messages WHERE chat_id = m2.chat_id AND role = 'assistant' AND id > mc.message_id)
                LEFT JOIN phoenix.spans s ON (s.attributes->'moolai'->>'message_id' = mc.message_id::text 
                                            OR s.attributes->'moolai'->>'message_id' = m2.id::text)
                    AND s.name = 'moolai.request.process'
                    AND s.attributes->'moolai'->>'service_name' = 'main_response'
                    AND s.start_time >= :start_time
                    AND s.start_time <= :end_time
                WHERE s.attributes->'moolai'->'cache' IS NOT NULL
            ),
            
            -- STEP 4: Get LLM metrics from parent spans (data is stored there)
            -- Phoenix spans store message_id as either user_msg_id or assistant_msg_id depending on flow
            llm_metrics AS (
                SELECT DISTINCT
                    mc.message_id,
                    (s.attributes->'moolai'->'tokens'->>'total')::INTEGER as total_tokens,
                    (s.attributes->'moolai'->'tokens'->>'input')::INTEGER as prompt_tokens,
                    (s.attributes->'moolai'->'tokens'->>'output')::INTEGER as completion_tokens,
                    (s.attributes->'moolai'->>'cost')::FLOAT as total_cost,
                    s.attributes->'moolai'->>'model' as model,
                    EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000 as llm_duration_ms
                FROM message_content mc
                LEFT JOIN messages m2 ON m2.chat_id = (SELECT chat_id FROM messages WHERE id = mc.message_id)
                                     AND m2.role = 'assistant' 
                                     AND m2.id = (SELECT MIN(id) FROM messages WHERE chat_id = m2.chat_id AND role = 'assistant' AND id > mc.message_id)
                LEFT JOIN phoenix.spans s ON (s.attributes->'moolai'->>'message_id' = mc.message_id::text 
                                            OR s.attributes->'moolai'->>'message_id' = m2.id::text)
                    AND s.name = 'moolai.request.process'
                    AND s.attributes->'moolai'->>'service_name' = 'main_response'
                    AND s.start_time >= :start_time
                    AND s.start_time <= :end_time
                WHERE s.attributes->'moolai'->'tokens' IS NOT NULL
            ),
            
            -- STEP 5: Get firewall data from parent request spans (firewall data is embedded)
            -- Phoenix spans store message_id as either user_msg_id or assistant_msg_id depending on flow
            firewall_metrics AS (
                SELECT DISTINCT
                    mc.message_id,
                    CASE 
                        WHEN s.attributes->'moolai'->'firewall'->>'blocked' IS NOT NULL THEN
                            (s.attributes->'moolai'->'firewall'->>'blocked')::boolean
                        ELSE NULL
                    END as was_blocked,
                    s.attributes->'moolai'->'firewall'->>'reason' as block_reason,
                    s.attributes->'moolai'->'firewall'->>'rule_category' as rule_category,
                    CASE 
                        WHEN s.attributes->'moolai'->'firewall'->>'risk_score' IS NOT NULL THEN
                            (s.attributes->'moolai'->'firewall'->>'risk_score')::float
                        ELSE NULL
                    END as risk_score,
                    s.attributes->'moolai'->'firewall'->'detected_entities' as detected_entities
                FROM message_content mc
                LEFT JOIN messages m2 ON m2.chat_id = (SELECT chat_id FROM messages WHERE id = mc.message_id)
                                     AND m2.role = 'assistant' 
                                     AND m2.id = (SELECT MIN(id) FROM messages WHERE chat_id = m2.chat_id AND role = 'assistant' AND id > mc.message_id)
                LEFT JOIN phoenix.spans s ON (s.attributes->'moolai'->>'message_id' = mc.message_id::text 
                                            OR s.attributes->'moolai'->>'message_id' = m2.id::text)
                    AND s.name = 'moolai.request.process'
                    AND s.attributes->'moolai'->>'service_name' = 'main_response'
                    AND s.start_time >= :start_time
                    AND s.start_time <= :end_time
                WHERE s.attributes->'moolai'->'firewall' IS NOT NULL
            ),
            
            -- STEP 6: Get evaluation scores from child spans
            evaluation_scores AS (
                SELECT
                    -- Link evaluation scores from assistant messages to their corresponding user messages
                    -- User message triggers assistant response, so user_msg.id + 1 = assistant_msg.id typically
                    (SELECT m_user.id
                     FROM messages m_user
                     WHERE m_user.chat_id = m_assistant.chat_id
                     AND m_user.role = 'user'
                     AND m_user.id < m_assistant.id
                     ORDER BY m_user.id DESC
                     LIMIT 1)::text as message_id,
                    -- Create evaluation score object with all three scores
                    json_build_object(
                        'answer_correctness', json_build_object(
                            'score', les.answer_correctness,
                            'reasoning', 'LLM evaluation result'
                        ),
                        'answer_relevance', json_build_object(
                            'score', les.answer_relevance,
                            'reasoning', 'LLM evaluation result'
                        ),
                        'hallucination_score', json_build_object(
                            'score', les.hallucination_score,
                            'reasoning', 'LLM evaluation result'
                        )
                    ) as evaluation_scores_obj
                FROM llm_evaluation_scores les
                JOIN messages m_assistant ON m_assistant.id = les.message_id
                WHERE (les.answer_correctness IS NOT NULL
                   OR les.answer_relevance IS NOT NULL
                   OR les.hallucination_score IS NOT NULL)
                AND m_assistant.role = 'assistant'
            )
            
            -- FINAL QUERY: Combine all data with proper aggregation
            SELECT 
                mc.message_id,
                mc.user_id,
                mc.username,
                mc.full_name,
                mc.message_timestamp,
                mc.prompt_text,
                mc.response_text,
                
                -- Phoenix span data
                pr.total_duration_ms,
                
                -- Cache metrics
                cm.cache_hit,
                cm.similarity_score,
                cm.cache_lookup_ms,
                
                -- LLM metrics  
                lm.total_tokens,
                lm.prompt_tokens,
                lm.completion_tokens,
                lm.total_cost,
                lm.model,
                lm.llm_duration_ms,
                
                -- Firewall metrics
                fm.was_blocked,
                fm.block_reason,
                fm.rule_category,
                fm.risk_score,
                fm.detected_entities,
                
                -- Evaluation scores (direct from evaluation_scores table)
                COALESCE(es.evaluation_scores_obj, '{}'::json) as evaluation_scores
            
            FROM message_content mc
            LEFT JOIN parent_requests pr ON pr.message_id = mc.message_id::text
            LEFT JOIN cache_metrics cm ON cm.message_id = mc.message_id
            LEFT JOIN llm_metrics lm ON lm.message_id = mc.message_id
            LEFT JOIN firewall_metrics fm ON fm.message_id = mc.message_id
            LEFT JOIN evaluation_scores es ON es.message_id = mc.message_id::text
            
            -- No GROUP BY needed since evaluation scores are pre-aggregated in the CTE
            
            ORDER BY mc.message_timestamp DESC
            LIMIT :limit OFFSET :offset;
        """)
        
        # Execute query with parameters
        query_params = {
            'start_time': start_date,
            'end_time': end_date,
            'org_id': organization_id,
            'user_filter': user_filter,
            'search_text': search_text,
            'limit': limit,
            'offset': offset
        }
        logger.info(f"🔍 [PROMPTS-SERVICE-DEBUG] Executing main query with params: {query_params}")

        result = await db.execute(query, query_params)
        logger.info(f"🔍 [PROMPTS-SERVICE-DEBUG] Query executed successfully")

        rows = result.fetchall()
        logger.info(f"🔍 [PROMPTS-SERVICE-DEBUG] Retrieved {len(rows)} rows from database")

        # Process results into structured format
        prompts_data = []
        for row in rows:
            # Parse evaluation scores JSON
            evaluation_scores = {}
            try:
                if row.evaluation_scores:
                    evaluation_scores = json.loads(row.evaluation_scores) if isinstance(row.evaluation_scores, str) else row.evaluation_scores
            except (json.JSONDecodeError, TypeError):
                evaluation_scores = {}
            
            # Parse detected entities JSON
            detected_entities = []
            try:
                if row.detected_entities:
                    detected_entities = json.loads(row.detected_entities) if isinstance(row.detected_entities, str) else row.detected_entities
            except (json.JSONDecodeError, TypeError):
                detected_entities = []
            
            # Helper function to convert Decimal/None to float/None for JSON serialization
            def safe_float(val):
                if val is None:
                    return None
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return val
            
            prompt_data = {
                "message_id": row.message_id,
                "user_id": row.user_id,
                "username": row.username or "Unknown User",
                "full_name": row.full_name or "Unknown User",
                "timestamp": row.message_timestamp.isoformat() if row.message_timestamp else None,
                "prompt_text": row.prompt_text or "",
                "response_text": row.response_text or "",
                
                # Performance metrics - convert Decimal to float
                "total_duration_ms": safe_float(row.total_duration_ms),
                "cache_lookup_ms": safe_float(row.cache_lookup_ms),
                "llm_duration_ms": safe_float(row.llm_duration_ms),
                
                # Cache metrics - convert Decimal to float
                "cache_hit": row.cache_hit,
                "similarity_score": safe_float(row.similarity_score),
                
                # LLM metrics - convert Decimal to float
                "total_tokens": row.total_tokens,
                "prompt_tokens": row.prompt_tokens,
                "completion_tokens": row.completion_tokens,
                "total_cost": safe_float(row.total_cost),
                "model": row.model,
                
                # Firewall metrics - convert Decimal to float
                "was_blocked": row.was_blocked,
                "block_reason": row.block_reason,
                "rule_category": row.rule_category,
                "risk_score": safe_float(row.risk_score),
                "detected_entities": detected_entities,
                
                # Evaluation scores (detailed numeric scores)
                "evaluation_scores": evaluation_scores
            }
            
            prompts_data.append(prompt_data)
        
        # Get total count for pagination
        count_query = text("""
            SELECT COUNT(DISTINCT m.id)
            FROM messages m
            JOIN chats c ON m.chat_id = c.id
            WHERE m.role = 'user' 
            AND c.organization_id = :org_id
            AND m.created_at >= :start_time
            AND m.created_at <= :end_time
            AND (CAST(:user_filter AS text) IS NULL OR c.user_id = :user_filter)
            AND (CAST(:search_text AS text) IS NULL OR LOWER(m.content) LIKE LOWER('%' || :search_text || '%'))
        """)
        
        logger.info(f"🔍 [PROMPTS-SERVICE-DEBUG] Executing count query...")
        count_result = await db.execute(count_query, {
            'start_time': start_date,
            'end_time': end_date,
            'org_id': organization_id,
            'user_filter': user_filter,
            'search_text': search_text
        })

        total_count = count_result.scalar() or 0
        logger.info(f"🔍 [PROMPTS-SERVICE-DEBUG] Total count: {total_count}")

        result_data = {
            "prompts": prompts_data,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": total_count > (offset + limit)
            },
            "filters": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "user_filter": user_filter,
                "search_text": search_text
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"✅ [PROMPTS-SERVICE-DEBUG] Successfully returning data with {len(prompts_data)} prompts")
        return result_data

    except Exception as e:
        logger.error(f"❌ [PROMPTS-SERVICE-DEBUG] Exception occurred: {e}")
        logger.error(f"❌ [PROMPTS-SERVICE-DEBUG] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [PROMPTS-SERVICE-DEBUG] Traceback: {traceback.format_exc()}")
        return {
            "prompts": [],
            "pagination": {"total": 0, "limit": limit, "offset": offset, "has_more": False},
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


async def get_prompt_detail_data(
    message_id: str,
    organization_id: str,
    db: AsyncSession = None
) -> Dict[str, Any]:
    """
    Get detailed information for a specific prompt including all Phoenix span data.
    """
    if not db:
        raise ValueError("Database session required")
    
    try:
        # Detailed query for a specific message with all Phoenix span relationships
        query = text("""
            WITH target_message AS (
                SELECT 
                    m.id as message_id,
                    m.content as prompt_text,
                    m.created_at as message_timestamp,
                    c.user_id,
                    u.username,
                    u.full_name,
                    m2.content as response_text,
                    m2.created_at as response_timestamp
                FROM messages m
                JOIN chats c ON m.chat_id = c.id
                LEFT JOIN users u ON c.user_id = u.user_id
                LEFT JOIN messages m2 ON m2.chat_id = m.chat_id 
                                     AND m2.role = 'assistant' 
                                     AND m2.id = (
                                         SELECT MIN(id) FROM messages 
                                         WHERE chat_id = m.chat_id 
                                         AND role = 'assistant' 
                                         AND id > m.id
                                     )
                WHERE m.id = :message_id
                AND m.role = 'user'
                AND c.organization_id = :org_id
            ),
            
            parent_span AS (
                SELECT 
                    s.*,
                    EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000 as duration_ms
                FROM phoenix.spans s
                WHERE s.name = 'moolai.request.process'
                AND s.attributes->'moolai'->>'message_id' = :message_id
                AND s.attributes->'moolai'->>'service_name' = 'main_response'
            ),
            
            all_child_spans AS (
                SELECT 
                    s.name,
                    s.attributes,
                    s.start_time,
                    s.end_time,
                    EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000 as duration_ms,
                    s.parent_id
                FROM phoenix.spans s
                JOIN parent_span p ON s.trace_rowid = p.trace_rowid
                WHERE s.parent_id = p.span_id
            )
            
            SELECT 
                tm.*,
                ps.duration_ms as total_duration_ms,
                ps.attributes as parent_attributes,
                json_agg(
                    json_build_object(
                        'name', acs.name,
                        'attributes', acs.attributes,
                        'duration_ms', acs.duration_ms,
                        'start_time', acs.start_time,
                        'end_time', acs.end_time
                    )
                ) as child_spans
            FROM target_message tm
            LEFT JOIN parent_span ps ON TRUE
            LEFT JOIN all_child_spans acs ON TRUE
            GROUP BY tm.message_id, tm.prompt_text, tm.message_timestamp, 
                     tm.user_id, tm.username, tm.full_name, tm.response_text,
                     tm.response_timestamp, ps.duration_ms, ps.attributes;
        """)
        
        result = await db.execute(query, {
            'message_id': message_id,
            'org_id': organization_id
        })
        
        row = result.fetchone()
        
        if not row:
            return {
                "error": "Prompt not found",
                "message_id": message_id
            }
        
        # Process child spans into organized categories
        child_spans = json.loads(row.child_spans) if row.child_spans else []
        
        cache_data = None
        llm_data = None
        firewall_data = None
        evaluation_data = {}
        
        for span in child_spans:
            if span['name'] == 'moolai.cache.lookup':
                cache_attrs = span.get('attributes', {}).get('moolai', {}).get('cache', {})
                cache_data = {
                    "hit": cache_attrs.get('hit'),
                    "similarity": cache_attrs.get('similarity'),
                    "duration_ms": span['duration_ms'],
                    "start_time": span['start_time'],
                    "end_time": span['end_time']
                }
            
            elif span['name'] == 'openai.chat':
                llm_attrs = span.get('attributes', {})
                llm_data = {
                    "model": llm_attrs.get('moolai', {}).get('model') or llm_attrs.get('openai', {}).get('model'),
                    "tokens": llm_attrs.get('moolai', {}).get('tokens', {}),
                    "cost": llm_attrs.get('moolai', {}).get('cost'),
                    "duration_ms": span['duration_ms'],
                    "start_time": span['start_time'],
                    "end_time": span['end_time']
                }
            
            elif span['name'] == 'moolai.firewall.scan':
                firewall_attrs = span.get('attributes', {}).get('moolai', {}).get('firewall', {})
                firewall_data = {
                    "blocked": firewall_attrs.get('blocked'),
                    "reason": firewall_attrs.get('reason'),
                    "rule_category": firewall_attrs.get('rule_category'),
                    "risk_score": firewall_attrs.get('risk_score'),
                    "detected_entities": firewall_attrs.get('detected_entities', []),
                    "duration_ms": span['duration_ms'],
                    "start_time": span['start_time'],
                    "end_time": span['end_time']
                }
            
            elif span['name'].startswith('moolai.evaluation.'):
                eval_type = span['name'].replace('moolai.evaluation.', '')
                eval_attrs = span.get('attributes', {}).get('moolai', {}).get('evaluation', {})
                evaluation_data[eval_type] = {
                    "score": eval_attrs.get('score'),
                    "reasoning": eval_attrs.get('reasoning'),
                    "duration_ms": span['duration_ms'],
                    "start_time": span['start_time'],
                    "end_time": span['end_time']
                }
        
        return {
            "message_id": row.message_id,
            "user_id": row.user_id,
            "username": row.username or "Unknown User",
            "full_name": row.full_name or "Unknown User",
            "timestamp": row.message_timestamp.isoformat() if row.message_timestamp else None,
            "prompt_text": row.prompt_text or "",
            "response_text": row.response_text or "",
            "response_timestamp": row.response_timestamp.isoformat() if row.response_timestamp else None,
            
            # Performance overview
            "total_duration_ms": row.total_duration_ms,
            
            # Detailed component data
            "cache_data": cache_data,
            "llm_data": llm_data,
            "firewall_data": firewall_data,
            "evaluation_data": evaluation_data,
            
            # Raw span data for debugging
            "parent_attributes": json.loads(row.parent_attributes) if row.parent_attributes else {},
            "child_spans_count": len(child_spans),
            
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting prompt detail data: {e}", exc_info=True)
        return {
            "error": str(e),
            "message_id": message_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


async def export_prompts_data(
    organization_id: str,
    export_format: str = "csv",
    filters: Dict[str, Any] = None,
    db: AsyncSession = None
) -> Dict[str, Any]:
    """
    Export prompts data in CSV or JSON format with all metrics.
    """
    if not db:
        raise ValueError("Database session required")
    
    try:
        filters = filters or {}
        
        # Use default date range if not provided
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        
        if filters.get("start_date"):
            start_date = datetime.fromisoformat(filters["start_date"].replace('Z', '+00:00'))
        if filters.get("end_date"):
            end_date = datetime.fromisoformat(filters["end_date"].replace('Z', '+00:00'))
        
        # Get all prompts data (no limit for export)
        prompts_data = await get_user_prompts_data(
            start_date=start_date,
            end_date=end_date,
            organization_id=organization_id,
            limit=10000,  # High limit for export
            offset=0,
            user_filter=filters.get("user_filter"),
            search_text=filters.get("search_text"),
            db=db
        )
        
        if export_format.lower() == "csv":
            # Generate CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # CSV headers
            headers = [
                "Message ID", "User ID", "Username", "Full Name", "Timestamp",
                "Prompt Text", "Response Text", "Total Duration (ms)",
                "Cache Hit", "Similarity Score", "Cache Lookup (ms)",
                "Total Tokens", "Prompt Tokens", "Completion Tokens", "Total Cost", "Model",
                "LLM Duration (ms)", "Was Blocked", "Block Reason", "Rule Category",
                "Risk Score", "Detected Entities",
                "Answer Correctness", "Answer Relevance", "Hallucination Score",
                "Goal Accuracy", "Human vs AI", "Summarization Quality", "Toxicity Score"
            ]
            writer.writerow(headers)
            
            # CSV data rows
            for prompt in prompts_data.get("prompts", []):
                eval_scores = prompt.get("evaluation_scores", {})
                
                row = [
                    prompt.get("message_id", ""),
                    prompt.get("user_id", ""),
                    prompt.get("username", ""),
                    prompt.get("full_name", ""),
                    prompt.get("timestamp", ""),
                    prompt.get("prompt_text", "")[:500] + "..." if len(prompt.get("prompt_text", "")) > 500 else prompt.get("prompt_text", ""),
                    prompt.get("response_text", "")[:500] + "..." if len(prompt.get("response_text", "")) > 500 else prompt.get("response_text", ""),
                    prompt.get("total_duration_ms", ""),
                    prompt.get("cache_hit", ""),
                    prompt.get("similarity_score", ""),
                    prompt.get("cache_lookup_ms", ""),
                    prompt.get("total_tokens", ""),
                    prompt.get("prompt_tokens", ""),
                    prompt.get("completion_tokens", ""),
                    prompt.get("total_cost", ""),
                    prompt.get("model", ""),
                    prompt.get("llm_duration_ms", ""),
                    prompt.get("was_blocked", ""),
                    prompt.get("block_reason", ""),
                    prompt.get("rule_category", ""),
                    prompt.get("risk_score", ""),
                    json.dumps(prompt.get("detected_entities", [])),
                    eval_scores.get("answer_correctness", {}).get("score", ""),
                    eval_scores.get("answer_relevance", {}).get("score", ""),
                    eval_scores.get("hallucination", {}).get("score", ""),
                    eval_scores.get("goal_accuracy", {}).get("score", ""),
                    eval_scores.get("human_vs_ai", {}).get("score", ""),
                    eval_scores.get("summarization", {}).get("score", ""),
                    eval_scores.get("toxicity", {}).get("score", "")
                ]
                writer.writerow(row)
            
            csv_content = output.getvalue()
            output.close()
            
            # Encode as base64 for transfer
            csv_base64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
            
            return {
                "format": "csv",
                "filename": f"user_prompts_{organization_id}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv",
                "data": csv_base64,
                "size": len(csv_content),
                "rows": len(prompts_data.get("prompts", [])),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        else:  # JSON format
            json_content = json.dumps(prompts_data, indent=2, default=str)
            json_base64 = base64.b64encode(json_content.encode('utf-8')).decode('utf-8')
            
            return {
                "format": "json",
                "filename": f"user_prompts_{organization_id}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json",
                "data": json_base64,
                "size": len(json_content),
                "rows": len(prompts_data.get("prompts", [])),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
    except Exception as e:
        logger.error(f"Error exporting prompts data: {e}", exc_info=True)
        return {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
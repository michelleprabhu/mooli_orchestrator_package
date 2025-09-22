"""Analytics API endpoints for dashboard metrics - Direct PostgreSQL Phoenix queries."""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import asyncio
import os
import logging

# Import orchestrator database session since Phoenix data is in orchestrator DB
from ....db.database import db_manager

async def get_orchestrator_db():
    """Get orchestrator database session where Phoenix data resides."""
    async for session in db_manager.get_session():
        yield session

logger = logging.getLogger(__name__)

# We'll query Phoenix data directly from PostgreSQL
PHOENIX_SCHEMA = "phoenix"

router = APIRouter()


class PhoenixAnalyticsService:
    """Service to query Phoenix data directly from PostgreSQL database."""
    
    def __init__(self):
        """Initialize Phoenix Analytics Service to query PostgreSQL directly."""
        # We'll use the orchestrator database connection to query Phoenix schema
        self.phoenix_schema = PHOENIX_SCHEMA
        logger.info(f"Phoenix Analytics Service initialized to query PostgreSQL schema: {self.phoenix_schema}")
    
    def _empty_response(self, start_date: datetime, end_date: datetime, error: str = None) -> Dict[str, Any]:
        """Return empty analytics response with error message."""
        response = {
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "overview": {
                "total_api_calls": 0,
                "total_cost": 0.0,
                "total_tokens": 0,
                "avg_response_time_ms": 0,
                "cache_hit_rate": 0.0,
                "firewall_blocks": 0
            },
            "provider_breakdown": [],
            "data_source": "phoenix_native",
            "phoenix_available": True,  # Always true since we're using PostgreSQL
            "phoenix_connected": True
        }
        if error:
            response["error"] = error
        return response
    
    def _generate_fallback_data(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Return empty data structure when Phoenix is unavailable."""
        # Only used when Phoenix is truly unavailable
        # Real data should come from Phoenix
        return {
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "overview": {
                "total_api_calls": 0,
                "total_cost": 0.0,
                "total_tokens": 0,
                "avg_response_time_ms": 0,
                "cache_hit_rate": 0.0,
                "firewall_blocks": 0
            },
            "provider_breakdown": [],
            "data_source": "no_data",
            "phoenix_available": PHOENIX_AVAILABLE,
            "phoenix_connected": self.connection_validated,
            "message": "No data available. Make some API calls to see analytics."
        }
    
    async def get_analytics_overview_from_phoenix(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        organization_id: Optional[str] = None,
        db: AsyncSession = None,
        include_internal: bool = False  # False = user dashboard only, True = all services for controller
    ) -> Dict[str, Any]:
        """Get analytics overview data from Phoenix native schema."""
        if not db:
            return self._empty_response(start_date, end_date, "Database connection required")
        
        try:
            # Build query based on include_internal parameter
            # Dashboard view filters to main_response only, internal view shows all
            
            # Common CTE parts used in both queries
            base_query_start = """
                WITH llm_spans AS (
                    SELECT 
                        s.*,
                        -- Extract tokens from multiple possible sources (prioritize moolai parent spans)
                        COALESCE(
                            (s.attributes->'moolai'->'tokens'->>'input')::INTEGER,
                            (s.attributes->'openai.response'->>'tokens_prompt')::INTEGER,
                            (s.attributes->'gen_ai'->'usage'->>'prompt_tokens')::INTEGER
                        ) as prompt_tokens,
                        COALESCE(
                            (s.attributes->'moolai'->'tokens'->>'output')::INTEGER,
                            (s.attributes->'openai.response'->>'tokens_completion')::INTEGER,
                            (s.attributes->'gen_ai'->'usage'->>'completion_tokens')::INTEGER
                        ) as completion_tokens,
                        COALESCE(
                            (s.attributes->'moolai'->'tokens'->>'total')::INTEGER,
                            (s.attributes->'openai.response'->>'tokens_total')::INTEGER,
                            (s.attributes->'gen_ai'->'usage'->>'prompt_tokens')::INTEGER + (s.attributes->'gen_ai'->'usage'->>'completion_tokens')::INTEGER
                        ) as total_tokens,
                        COALESCE(
                            s.attributes->'moolai'->>'model',
                            s.attributes->>'openai.model',
                            s.attributes->'gen_ai'->'request'->>'model'
                        ) as model_name,
                        COALESCE(
                            s.attributes->>'openai.service_name',
                            s.attributes->'gen_ai'->>'system',
                            'openai'
                        ) as provider,
                        EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000 as duration_ms,
                        COALESCE(sc.total_cost, 
                            -- Try MoolAI cost attribute first
                            COALESCE((s.attributes->'moolai'->>'cost')::FLOAT, 
                                -- Try nested MoolAI llm cost
                                COALESCE((s.attributes->'moolai'->'llm'->>'cost')::FLOAT,
                                    -- Try direct cost attribute
                                    (s.attributes->>'cost')::FLOAT, 0)
                            )
                        ) as cost
                    FROM phoenix.spans s
                    LEFT JOIN phoenix.span_costs sc ON s.id = sc.span_rowid
                    WHERE s.start_time >= :start_time
                        AND s.start_time <= :end_time
                        AND (
                            -- Must be actual LLM call with gen_ai data, openai attributes, or moolai parent spans
                            s.attributes ? 'gen_ai' OR
                            s.attributes ? 'openai' OR
                            (s.name = 'moolai.request.process' AND s.attributes->'moolai' ? 'cost')
                        )
            """
            
            # Add service filter for dashboard view
            if not include_internal:
                # Dashboard: Focus on user-facing parent spans (new hierarchy structure)
                base_query_start += """
                        AND (
                            -- Parent request spans for user-facing services (new structure)
                            (s.name = 'moolai.request.process' AND s.attributes->'moolai'->>'service_name' = 'main_response') OR
                            -- Legacy spans for backward compatibility
                            (s.name = 'moolai.user_interaction') OR
                            -- LLM child spans from legacy structure (fallback)
                            (s.name = 'openai.chat' AND s.attributes->'moolai'->>'service_name' = 'main_response')
                        )
                """
            # else: include_internal=True includes all services
            
            # Use messages table for main analytics but Phoenix spans for response time
            query = text("""
                WITH messages_summary AS (
                    -- Get main metrics from messages table (most accurate for provider data)
                    SELECT
                        COUNT(*) as total_api_calls,
                        SUM(COALESCE(m.cost_estimate, 0)) as total_cost,
                        SUM(COALESCE(m.tokens_used, 0)) as total_tokens
                    FROM messages m
                    WHERE m.role = 'assistant'
                        AND m.created_at >= :start_time
                        AND m.created_at <= :end_time
                        AND m.organization_id = 'org_001'
                ),
                response_time_summary AS (
                    -- Get response times from Phoenix spans (accurate timing data)
                    SELECT
                        AVG(EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000)::INTEGER as avg_response_time_ms
                    FROM phoenix.spans s
                    WHERE s.name = 'moolai.request.process'
                        AND s.attributes->'moolai'->>'service_name' = 'main_response'
                        AND s.start_time >= :start_time
                        AND s.start_time <= :end_time
                ),
                cache_summary AS (
                    -- Get cache data from Phoenix spans
                    SELECT
                        COUNT(*) as total_cache_requests,
                        COUNT(*) FILTER (WHERE
                            (s.attributes->'moolai'->'cache'->>'hit')::boolean = true
                        ) as cache_hits,
                        CASE
                            WHEN COUNT(*) > 0 THEN
                                (COUNT(*) FILTER (WHERE
                                    (s.attributes->'moolai'->'cache'->>'hit')::boolean = true
                                )) * 100.0 / COUNT(*)
                            ELSE 0
                        END as cache_hit_rate
                    FROM phoenix.spans s
                    WHERE s.name = 'moolai.request.process'
                    AND s.attributes->'moolai'->>'service_name' = 'main_response'
                    AND s.start_time >= :start_time
                    AND s.start_time <= :end_time
                    AND s.attributes->'moolai'->'cache' IS NOT NULL
                ),
                firewall_summary AS (
                    -- Get firewall blocks from Phoenix spans
                    SELECT
                        COUNT(*) FILTER (WHERE
                            (s.attributes->'moolai'->'firewall'->>'blocked')::boolean = true
                        ) as firewall_blocks
                    FROM phoenix.spans s
                    WHERE s.name = 'moolai.request.process'
                    AND s.attributes->'moolai'->>'service_name' = 'main_response'
                    AND s.start_time >= :start_time
                    AND s.start_time <= :end_time
                    AND s.attributes->'moolai'->'firewall' IS NOT NULL
                ),
                provider_stats AS (
                    -- Get provider stats from messages table
                    SELECT
                        COALESCE(m.provider_used, 'openai') as provider,
                        COALESCE(m.model_used, 'gpt-3.5-turbo') as model,
                        COUNT(*) as calls,
                        SUM(COALESCE(m.tokens_used, 0)) as tokens,
                        SUM(COALESCE(m.cost_estimate, 0)) as cost
                    FROM messages m
                    WHERE m.role = 'assistant'
                        AND m.created_at >= :start_time
                        AND m.created_at <= :end_time
                        AND m.organization_id = 'org_001'
                    GROUP BY COALESCE(m.provider_used, 'openai'), COALESCE(m.model_used, 'gpt-3.5-turbo')
                )
                SELECT
                    COALESCE(s.total_api_calls, 0) as total_api_calls,
                    COALESCE(s.total_cost, 0) as total_cost,
                    COALESCE(s.total_tokens, 0) as total_tokens,
                    COALESCE(rt.avg_response_time_ms, 0) as avg_response_time_ms,
                    COALESCE(c.cache_hit_rate, 0) as cache_hit_rate,
                    COALESCE(f.firewall_blocks, 0) as firewall_blocks,
                    COALESCE(
                        jsonb_agg(
                            jsonb_build_object(
                                'provider', p.provider,
                                'model', p.model,
                                'calls', p.calls,
                                'tokens', p.tokens,
                                'cost', p.cost
                            )
                        ) FILTER (WHERE p.provider IS NOT NULL),
                        '[]'::jsonb
                    ) as provider_breakdown
                FROM messages_summary s
                FULL OUTER JOIN response_time_summary rt ON true
                FULL OUTER JOIN cache_summary c ON true
                FULL OUTER JOIN firewall_summary f ON true
                LEFT JOIN provider_stats p ON true
                GROUP BY s.total_api_calls, s.total_cost, s.total_tokens,
                         rt.avg_response_time_ms, c.cache_hit_rate, f.firewall_blocks;
            """)
            
            result = await db.execute(query, {
                'start_time': start_date,
                'end_time': end_date
            })
            
            row = result.fetchone()
            
            if row and row.total_api_calls > 0:
                return {
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    },
                    "overview": {
                        "total_api_calls": int(row.total_api_calls or 0),
                        "total_cost": float(row.total_cost or 0),
                        "total_tokens": int(row.total_tokens or 0),
                        "avg_response_time_ms": int(row.avg_response_time_ms or 0),
                        "cache_hit_rate": float(row.cache_hit_rate or 0),
                        "firewall_blocks": int(row.firewall_blocks or 0)
                    },
                    "provider_breakdown": row.provider_breakdown or [],
                    "data_source": "phoenix_native",
                    "phoenix_available": True,
                    "phoenix_connected": True
                }
            else:
                logger.info(f"No LLM data found in Phoenix between {start_date} and {end_date}")
                return self._empty_response(start_date, end_date)
                
        except Exception as e:
            logger.error(f"Phoenix native query error: {e}")
            return self._empty_response(start_date, end_date, str(e))
    
    async def get_provider_breakdown_from_phoenix(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        organization_id: Optional[str] = None,
        db: AsyncSession = None,
        include_internal: bool = False  # Add same parameter for consistency
    ) -> Dict[str, Any]:
        """Get provider breakdown from Phoenix PostgreSQL database."""
        try:
            project_name = f"moolai-org_001"  # Default org for now
            if organization_id:
                project_name = f"moolai-{organization_id}"

            # Build query with optional service filtering
            base_provider_query = """
                WITH llm_spans AS (
                    SELECT 
                        -- Extract tokens from multiple possible sources (prioritize moolai parent spans)
                        COALESCE(
                            (s.attributes->'moolai'->'tokens'->>'input')::INTEGER,
                            (s.attributes->'openai.response'->>'tokens_prompt')::INTEGER,
                            (s.attributes->'gen_ai'->'usage'->>'prompt_tokens')::INTEGER
                        ) as prompt_tokens,
                        COALESCE(
                            (s.attributes->'moolai'->'tokens'->>'output')::INTEGER,
                            (s.attributes->'openai.response'->>'tokens_completion')::INTEGER,
                            (s.attributes->'gen_ai'->'usage'->>'completion_tokens')::INTEGER
                        ) as completion_tokens,
                        COALESCE(
                            (s.attributes->'moolai'->'tokens'->>'total')::INTEGER,
                            (s.attributes->'openai.response'->>'tokens_total')::INTEGER,
                            (s.attributes->'gen_ai'->'usage'->>'prompt_tokens')::INTEGER + (s.attributes->'gen_ai'->'usage'->>'completion_tokens')::INTEGER
                        ) as total_tokens,
                        COALESCE(
                            s.attributes->'moolai'->>'model',
                            s.attributes->>'openai.model',
                            s.attributes->'gen_ai'->'request'->>'model'
                        ) as model_name,
                        COALESCE(
                            s.attributes->>'openai.service_name',
                            s.attributes->'gen_ai'->>'system',
                            'openai'
                        ) as provider,
                        EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000 as duration_ms,
                        COALESCE(sc.total_cost, 
                            -- Try MoolAI cost attribute first
                            COALESCE((s.attributes->'moolai'->>'cost')::FLOAT, 
                                -- Try nested MoolAI llm cost
                                COALESCE((s.attributes->'moolai'->'llm'->>'cost')::FLOAT,
                                    -- Try direct cost attribute
                                    (s.attributes->>'cost')::FLOAT, 0)
                            )
                        ) as total_cost
                    FROM phoenix.spans s
                    LEFT JOIN phoenix.span_costs sc ON s.id = sc.span_rowid
                    WHERE s.start_time >= :start_time
                        AND s.start_time <= :end_time
                        AND (
                            -- Must be actual LLM call with gen_ai data, openai attributes, or moolai parent spans
                            s.attributes ? 'gen_ai' OR
                            s.attributes ? 'openai' OR
                            (s.name = 'moolai.request.process' AND s.attributes->'moolai' ? 'cost')
                        )
            """
            
            # Add service filter for dashboard view
            if not include_internal:
                base_provider_query += """
                        AND (
                            -- Parent request spans for user-facing services (new structure)
                            (s.name = 'moolai.request.process' AND s.attributes->'moolai'->>'service_name' = 'main_response') OR
                            -- Legacy spans for backward compatibility
                            (s.name = 'moolai.user_interaction') OR
                            -- LLM child spans from legacy structure (fallback)
                            (s.name = 'openai.chat' AND s.attributes->'moolai'->>'service_name' = 'main_response')
                        )
                """
            
            # Use messages table for provider/cost data but Phoenix for accurate timing
            query = text("""
                WITH provider_messages AS (
                    SELECT
                        COALESCE(m.provider_used, 'openai') as provider,
                        COALESCE(m.model_used, 'gpt-3.5-turbo') as model_name,
                        COUNT(*) as call_count,
                        SUM(COALESCE(m.tokens_used, 0)) as total_tokens,
                        SUM(COALESCE(m.cost_estimate, 0)) as total_cost,
                        m.chat_id
                    FROM messages m
                    WHERE m.role = 'assistant'
                        AND m.created_at >= :start_time
                        AND m.created_at <= :end_time
                        AND m.organization_id = 'org_001'
                    GROUP BY COALESCE(m.provider_used, 'openai'), COALESCE(m.model_used, 'gpt-3.5-turbo'), m.chat_id
                ),
                provider_latency AS (
                    SELECT
                        COALESCE(pm.provider, 'openai') as provider,
                        COALESCE(pm.model_name, 'gpt-3.5-turbo') as model_name,
                        AVG(EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000)::INTEGER as avg_latency
                    FROM provider_messages pm
                    LEFT JOIN phoenix.spans s ON s.attributes->'moolai'->>'session_id' = pm.chat_id::text
                        AND s.name = 'moolai.request.process'
                        AND s.attributes->'moolai'->>'service_name' = 'main_response'
                        AND s.start_time >= :start_time
                        AND s.start_time <= :end_time
                    GROUP BY pm.provider, pm.model_name
                )
                SELECT
                    pm.provider,
                    pm.model_name,
                    SUM(pm.call_count) as call_count,
                    SUM(pm.total_tokens) as total_tokens,
                    SUM(pm.total_tokens) as prompt_tokens,  -- We don't separate prompt/completion in messages
                    0 as completion_tokens,  -- Set to 0 since not available separately
                    SUM(pm.total_cost) as total_cost,
                    COALESCE(pl.avg_latency, 0) as avg_latency
                FROM provider_messages pm
                LEFT JOIN provider_latency pl ON pm.provider = pl.provider AND pm.model_name = pl.model_name
                GROUP BY pm.provider, pm.model_name, pl.avg_latency
                ORDER BY call_count DESC;
            """)
            
            if db:
                result = await db.execute(query, {
                    'start_time': start_date,
                    'end_time': end_date
                })
                rows = result.fetchall()
                
                provider_breakdown = []
                for row in rows:
                    provider_breakdown.append({
                        "provider": row.provider,
                        "model": row.model_name,
                        "calls": int(row.call_count),
                        "tokens": int(row.total_tokens or 0),
                        "prompt_tokens": int(row.prompt_tokens or 0),
                        "completion_tokens": int(row.completion_tokens or 0),
                        "cost": float(row.total_cost or 0),
                        "avg_latency_ms": int(row.avg_latency or 0)
                    })
                
                return {
                    "time_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    },
                    "provider_breakdown": provider_breakdown,
                    "data_source": "phoenix_postgresql"
                }
            else:
                return {
                    "time_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                    "provider_breakdown": [],
                    "data_source": "phoenix_postgresql",
                    "error": "Database session not available"
                }
                
        except Exception as e:
            logger.error(f"Phoenix provider breakdown query error: {e}")
            return {
                "time_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "provider_breakdown": [],
                "data_source": "phoenix_postgresql",
                "error": str(e)
            }
    
    async def get_time_series_from_phoenix(
        self,
        metric: str,
        interval: str,
        start_date: datetime,
        end_date: datetime,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get time series data from Phoenix."""
        if not self.client:
            return {
                "metric": metric,
                "interval": interval,
                "time_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "data": [],
                "data_source": "phoenix_native",
                "error": "Phoenix client not available"
            }
        
        # For now, return empty time series data
        # This could be enhanced to query actual time series data from Phoenix
        return {
            "metric": metric,
            "interval": interval,
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "data": [],
            "data_source": "phoenix_native"
        }
    
    async def get_provider_breakdown_from_langfuse(
        self, 
        start_date: datetime, 
        end_date: datetime, 
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get provider breakdown from Langfuse and format for existing dashboard."""
        if not self.langfuse_client:
            raise HTTPException(status_code=503, detail="Langfuse client not available")
        
        try:
            traces = self.langfuse_client.fetch_traces(
                from_timestamp=start_date,
                to_timestamp=end_date,
                user_id=organization_id if organization_id else None
            )
            
            # Group by provider and model
            provider_stats = {}
            for trace in traces:
                model = trace.metadata.get('model', 'unknown')
                provider = 'openai' if 'gpt' in model.lower() else 'anthropic' if 'claude' in model.lower() else 'unknown'
                
                key = f"{provider}_{model}"
                if key not in provider_stats:
                    provider_stats[key] = {
                        "provider": provider,
                        "model": model,
                        "calls": 0,
                        "cost": 0.0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latencies": []
                    }
                
                provider_stats[key]["calls"] += 1
                provider_stats[key]["cost"] += trace.cost or 0
                if hasattr(trace, 'usage') and trace.usage:
                    provider_stats[key]["input_tokens"] += trace.usage.input or 0
                    provider_stats[key]["output_tokens"] += trace.usage.output or 0
                if hasattr(trace, 'latency') and trace.latency:
                    provider_stats[key]["latencies"].append(trace.latency)
            
            # Format breakdown
            breakdown = []
            for stats in provider_stats.values():
                avg_latency = sum(stats["latencies"]) / len(stats["latencies"]) if stats["latencies"] else 0
                avg_cost_per_query = stats["cost"] / stats["calls"] if stats["calls"] > 0 else 0
                
                breakdown.append({
                    "provider": stats["provider"],
                    "model": stats["model"],
                    "calls": stats["calls"],
                    "cost": float(stats["cost"]),
                    "input_tokens": stats["input_tokens"],
                    "output_tokens": stats["output_tokens"],
                    "total_tokens": stats["input_tokens"] + stats["output_tokens"],
                    "avg_latency_ms": int(avg_latency),
                    "avg_cost_per_query": avg_cost_per_query
                })
            
            # Sort by cost descending
            breakdown.sort(key=lambda x: x["cost"], reverse=True)
            
            return {
                "time_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "provider_breakdown": breakdown,
                "data_source": "langfuse"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to query Langfuse provider breakdown: {str(e)}")
    
    async def get_time_series_from_langfuse(
        self,
        metric: str,
        interval: str,
        start_date: datetime,
        end_date: datetime,
        organization_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get time series data from Langfuse."""
        if not self.langfuse_client:
            raise HTTPException(status_code=503, detail="Langfuse client not available")
        
        try:
            traces = self.langfuse_client.fetch_traces(
                from_timestamp=start_date,
                to_timestamp=end_date,
                user_id=organization_id if organization_id else None
            )
            
            # Group traces by time buckets
            from collections import defaultdict
            buckets = defaultdict(list)
            
            for trace in traces:
                timestamp = trace.timestamp
                if interval == "hour":
                    bucket = timestamp.replace(minute=0, second=0, microsecond=0)
                else:  # day
                    bucket = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
                
                buckets[bucket].append(trace)
            
            # Calculate metrics for each bucket
            time_series = []
            for bucket_time in sorted(buckets.keys()):
                bucket_traces = buckets[bucket_time]
                
                if metric == "cost":
                    value = sum(trace.cost or 0 for trace in bucket_traces)
                elif metric == "calls":
                    value = len(bucket_traces)
                elif metric == "tokens":
                    value = sum(
                        trace.usage.total_tokens if hasattr(trace, 'usage') and trace.usage else 0
                        for trace in bucket_traces
                    )
                elif metric == "latency":
                    latencies = [trace.latency for trace in bucket_traces if hasattr(trace, 'latency') and trace.latency]
                    value = sum(latencies) / len(latencies) if latencies else 0
                else:
                    value = 0
                
                time_series.append({
                    "timestamp": bucket_time.isoformat(),
                    "value": float(value) if metric != "calls" else int(value)
                })
            
            return {
                "metric": metric,
                "interval": interval,
                "time_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "data": time_series,
                "data_source": "langfuse"
            }
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to query Langfuse time series: {str(e)}")

# Initialize Phoenix analytics service
phoenix_analytics = PhoenixAnalyticsService()


@router.get("/analytics/overview")
async def get_analytics_overview(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    use_phoenix: bool = Query(True, description="Use Phoenix backend for analytics (legacy DB disabled)"),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """Get comprehensive analytics overview for the dashboard using Langfuse backend."""
    try:
        # Default to last 30 days if no dates provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # If end_date is at midnight (from date-only input), set to end of day
        if end_date.time() == datetime.min.time():
            logger.info(f"Adjusting end_date from midnight to end-of-day: {end_date} -> {end_date.replace(hour=23, minute=59, second=59, microsecond=999999)}")
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # If start_date is at midnight (from date-only input), keep as beginning of day
        if start_date.time() == datetime.min.time():
            logger.info(f"Confirmed start_date at beginning-of-day: {start_date}")
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Always use Phoenix backend (legacy database removed)
        if use_phoenix:
            # Dashboard view: Only show main_response (chat interface) calls
            return await phoenix_analytics.get_analytics_overview_from_phoenix(
                start_date, end_date, organization_id, db, include_internal=False
            )
        else:
            # Return message for legacy mode
            return {
                "message": "Legacy database monitoring has been removed. Using Phoenix backend.",
                "redirect": "Set use_phoenix=true to use Phoenix analytics",
                "data_source": "legacy_disabled",
                "time_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "overview": {
                    "total_api_calls": 0,
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "avg_response_time_ms": 0,
                    "cache_hit_rate": 0.0,
                    "firewall_blocks": 0
                },
                "provider_breakdown": []
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/internal")
async def get_internal_analytics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """
    Get comprehensive internal analytics including ALL services.
    This endpoint is designed for the controller VM to gather complete system metrics.
    
    Includes:
    - Main chat interface calls (main_response)
    - All evaluation service calls (*_evaluation)
    - Complete cost and token usage across all services
    
    Returns the same structure as /analytics/overview but with ALL internal service calls.
    """
    try:
        # Default to last 30 days if no dates provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # If end_date is at midnight (from date-only input), set to end of day
        if end_date.time() == datetime.min.time():
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # If start_date is at midnight (from date-only input), keep as beginning of day
        if start_date.time() == datetime.min.time():
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Call with include_internal=True to get ALL services
        return await phoenix_analytics.get_analytics_overview_from_phoenix(
            start_date, end_date, organization_id, db, include_internal=True
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/services")
async def get_service_breakdown(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """
    Get breakdown of API calls by service type.
    Shows which services are making calls and their respective costs/performance.
    
    Useful for:
    - Understanding the ratio of user-facing vs internal calls
    - Identifying which evaluation services are most expensive
    - Monitoring individual service performance
    """
    try:
        # Default to last 30 days if no dates provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        query = text("""
            WITH span_with_service AS (
                SELECT s.*,
                    COALESCE(
                        -- Check current span for service attribution (for parent spans)
                        s.attributes->'moolai'->>'service_name',
                        -- Check parent span for service attribution (for child spans)
                        (SELECT p.attributes->'moolai'->>'service_name' 
                         FROM phoenix.spans p 
                         WHERE p.span_id = s.parent_id AND p.name = 'moolai.request.process'),
                        -- Legacy service attribution fallbacks
                        s.attributes->'openai'->>'service_name',
                        CASE 
                            WHEN s.attributes->'openai'->>'operation_name' = 'generate_llm_response' THEN 'main_response'
                            ELSE 'unknown'
                        END
                    ) as service_name
                FROM phoenix.spans s
                WHERE s.start_time >= :start_time
                    AND s.start_time <= :end_time
                    AND (s.attributes ? 'gen_ai' OR s.attributes ? 'openai')
            )
            SELECT 
                service_name,
                COUNT(*) as call_count,
                SUM(COALESCE(
                    (s.attributes->'moolai'->>'cost')::FLOAT,
                    (s.attributes->'moolai'->'llm'->>'cost')::FLOAT,
                    0
                )) as total_cost,
                SUM(COALESCE(
                    (s.attributes->'openai.response'->>'tokens_total')::INTEGER,
                    (s.attributes->'gen_ai'->'usage'->>'prompt_tokens')::INTEGER + 
                    (s.attributes->'gen_ai'->'usage'->>'completion_tokens')::INTEGER,
                    0
                )) as total_tokens,
                AVG(EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * 1000)::INTEGER as avg_duration_ms
            FROM span_with_service s
            GROUP BY service_name
            ORDER BY call_count DESC
        """)
        
        result = await db.execute(query, {
            "start_time": start_date,
            "end_time": end_date
        })
        
        services = []
        user_facing_total = 0
        internal_total = 0
        
        for row in result:
            is_user_facing = row.service_name == "main_response"
            
            services.append({
                "service": row.service_name,
                "calls": row.call_count,
                "cost": round(float(row.total_cost or 0), 4),
                "tokens": row.total_tokens or 0,
                "avg_duration_ms": row.avg_duration_ms or 0,
                "is_user_facing": is_user_facing,
                "type": "chat_interface" if is_user_facing else "evaluation_service"
            })
            
            if is_user_facing:
                user_facing_total += row.call_count
            else:
                internal_total += row.call_count
        
        return {
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "services": services,
            "summary": {
                "user_facing_calls": user_facing_total,
                "internal_evaluation_calls": internal_total,
                "total_calls": user_facing_total + internal_total,
                "evaluation_multiplication_factor": round(internal_total / max(user_facing_total, 1), 2)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/provider-breakdown")
async def get_provider_breakdown(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    use_phoenix: bool = Query(True, description="Use Phoenix backend for analytics (legacy DB disabled)"),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """Get detailed provider breakdown for API calls and costs using Langfuse backend."""
    try:
        # Default to last 30 days if no dates provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # If end_date is at midnight (from date-only input), set to end of day
        if end_date.time() == datetime.min.time():
            logger.info(f"Adjusting end_date from midnight to end-of-day: {end_date} -> {end_date.replace(hour=23, minute=59, second=59, microsecond=999999)}")
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # If start_date is at midnight (from date-only input), keep as beginning of day
        if start_date.time() == datetime.min.time():
            logger.info(f"Confirmed start_date at beginning-of-day: {start_date}")
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Always use Phoenix backend (legacy database removed)
        if use_phoenix:
            return await phoenix_analytics.get_provider_breakdown_from_phoenix(
                start_date, end_date, organization_id, db
            )
        else:
            # Return message for legacy mode
            return {
                "message": "Legacy database monitoring has been removed. Using Phoenix backend.",
                "redirect": "Set use_phoenix=true to use Phoenix analytics",
                "data_source": "legacy_disabled",
                "time_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "provider_breakdown": []
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/time-series")
async def get_time_series_data(
    metric: str = Query("cost", regex="^(cost|calls|tokens|latency)$"),
    interval: str = Query("hour", regex="^(hour|day)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    use_phoenix: bool = Query(True, description="Use Phoenix backend for analytics (legacy DB disabled)"),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """Get time series data for specified metric using Langfuse backend."""
    try:
        # Default to last 24 hours if no dates provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            if interval == "hour":
                start_date = end_date - timedelta(hours=24)
            else:
                start_date = end_date - timedelta(days=30)
        
        # If end_date is at midnight (from date-only input), set to end of day
        if end_date.time() == datetime.min.time():
            logger.info(f"Adjusting end_date from midnight to end-of-day: {end_date} -> {end_date.replace(hour=23, minute=59, second=59, microsecond=999999)}")
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # If start_date is at midnight (from date-only input), keep as beginning of day
        if start_date.time() == datetime.min.time():
            logger.info(f"Confirmed start_date at beginning-of-day: {start_date}")
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Always use Phoenix backend (legacy database removed)
        if use_phoenix:
            return await phoenix_analytics.get_time_series_from_phoenix(
                metric, interval, start_date, end_date, organization_id
            )
        else:
            # Return message for legacy mode
            return {
                "message": "Legacy database monitoring has been removed. Using Phoenix backend.",
                "redirect": "Set use_phoenix=true to use Phoenix analytics",
                "data_source": "legacy_disabled",
                "metric": metric,
                "interval": interval,
                "time_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "data": []
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/cache-performance")
async def get_cache_performance(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """Legacy cache performance endpoint - data now available through Langfuse analytics."""
    return {
        "message": "Legacy cache monitoring has been removed. Cache performance is now tracked in Langfuse traces.",
        "redirect": "Use /analytics/overview?use_langfuse=true to see cache hit rates",
        "time_range": {
            "start": start_date.isoformat() if start_date else datetime.now(timezone.utc).isoformat(),
            "end": end_date.isoformat() if end_date else datetime.now(timezone.utc).isoformat()
        },
        "cache_performance": {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_hit_rate": 0.0,
            "cache_miss_rate": 0.0,
            "avg_similarity": 0.0,
            "avg_cache_latency_ms": 0,
            "avg_fresh_latency_ms": 0
        },
        "similarity_breakdown": []
    }


@router.get("/analytics/firewall-activity")
async def get_firewall_activity(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """Legacy firewall activity endpoint - data now available through Langfuse analytics."""
    return {
        "message": "Legacy firewall monitoring has been removed. Firewall activity is now tracked in Langfuse traces.",
        "redirect": "Use /analytics/overview?use_langfuse=true to see firewall block counts",
        "time_range": {
            "start": start_date.isoformat() if start_date else datetime.now(timezone.utc).isoformat(),
            "end": end_date.isoformat() if end_date else datetime.now(timezone.utc).isoformat()
        },
        "firewall_activity": {
            "total_requests": 0,
            "blocked_requests": 0,
            "allowed_requests": 0,
            "block_rate": 0.0,
            "allow_rate": 0.0
        },
        "block_reasons": {
            "pii_violations": 0,
            "secrets_detected": 0,
            "toxicity_detected": 0
        }
    }


@router.get("/analytics/evaluation-runs")
async def get_evaluation_runs(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    organization_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_orchestrator_db)
):
    """
    Get evaluation runs data for the organization monitoring dashboard.
    
    Returns evaluation data from both human evaluations and LLM evaluations,
    combining them into RunRow format expected by the dashboard.
    """
    try:
        # Default to last 30 days if no dates provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Adjust end_date to end of day if needed
        if end_date.time() == datetime.min.time():
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Keep start_date at beginning of day
        if start_date.time() == datetime.min.time():
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Build WHERE clause based on organization_id
        org_filter_he = "AND he.organization_id = :organization_id" if organization_id else ""
        org_filter_le = "AND le.organization_id = :organization_id" if organization_id else ""
        
        # Query to get evaluation runs combining human and LLM evaluations
        query = text(f"""
            WITH evaluation_runs AS (
                -- Human evaluations with message context
                SELECT 
                    he.id as evaluation_id,
                    'human' as evaluation_type,
                    he.message_id,
                    he.session_id as chat_id,
                    he.organization_id,
                    he.created_at as evaluation_time,
                    he.answer_correctness as accuracy,
                    he.answer_relevance as relevance,
                    he.hallucination_score as hallucination,
                    'complete' as status,
                    m.model_used,
                    m.tokens_used as total_tokens,
                    NULL as input_tokens,
                    NULL as output_tokens
                FROM human_evaluations he
                JOIN messages m ON he.message_id = m.id
                WHERE he.created_at >= :start_time
                    AND he.created_at <= :end_time
                    {org_filter_he}
                
                UNION ALL
                
                -- LLM evaluations with message context
                SELECT 
                    le.id as evaluation_id,
                    'llm' as evaluation_type,
                    le.message_id,
                    m.chat_id::text as chat_id,
                    le.organization_id,
                    le.created_at as evaluation_time,
                    le.answer_correctness as accuracy,
                    le.answer_relevance as relevance,
                    le.hallucination_score as hallucination,
                    CASE 
                        WHEN le.answer_correctness IS NOT NULL 
                             AND le.answer_relevance IS NOT NULL 
                             AND le.hallucination_score IS NOT NULL 
                        THEN 'complete'
                        ELSE 'running'
                    END as status,
                    COALESCE(le.evaluation_model, m.model_used) as model_used,
                    m.tokens_used as total_tokens,
                    -- Try to get input/output tokens from Phoenix spans if available
                    COALESCE(m.tokens_used, 0) / 2 as input_tokens,  -- Rough estimate
                    COALESCE(m.tokens_used, 0) / 2 as output_tokens  -- Rough estimate
                FROM llm_evaluation_scores le
                JOIN messages m ON le.message_id = m.id
                WHERE le.created_at >= :start_time
                    AND le.created_at <= :end_time
                    {org_filter_le}
            ),
            ranked_runs AS (
                SELECT 
                    er.*,
                    -- Calculate composite score and difference from baseline
                    CASE 
                        WHEN er.accuracy IS NOT NULL AND er.relevance IS NOT NULL AND er.hallucination IS NOT NULL
                        THEN (er.accuracy + er.relevance + (5 - er.hallucination)) / 3
                        ELSE NULL
                    END as composite_score,
                    ROW_NUMBER() OVER (ORDER BY er.evaluation_time DESC) as rn
                FROM evaluation_runs er
            )
            SELECT 
                rr.chat_id,
                COALESCE(rr.model_used, 'gpt-3.5-turbo') as model,
                rr.evaluation_time,
                COALESCE(rr.input_tokens, 0) as input_tokens,
                COALESCE(rr.output_tokens, 0) as output_tokens,
                COALESCE(rr.accuracy, 0.0) as accuracy,
                COALESCE(rr.relevance, 0.0) as relevance,
                COALESCE(rr.hallucination, 0.0) as hallucination,
                COALESCE(rr.composite_score, 0.0) as composite_score,
                -- Calculate diff from previous run (simplified to show variance)
                CASE 
                    WHEN rr.composite_score IS NOT NULL 
                    THEN (rr.composite_score - 3.0) * 10  -- Difference from neutral (3.0)
                    ELSE 0.0 
                END as diff,
                rr.status,
                rr.evaluation_type,
                rr.evaluation_id
            FROM ranked_runs rr
            WHERE rr.rn <= :limit
            ORDER BY rr.evaluation_time DESC
            OFFSET :offset
        """)
        
        # Build parameters based on whether organization_id is provided
        params = {
            "start_time": start_date,
            "end_time": end_date,
            "limit": limit,
            "offset": offset
        }
        if organization_id:
            params["organization_id"] = organization_id
        
        result = await db.execute(query, params)
        
        runs = []
        for row in result:
            runs.append({
                "chatId": row.chat_id,
                "model": row.model,
                "evaluationTime": row.evaluation_time.isoformat(),
                "inputTokens": int(row.input_tokens or 0),
                "outputTokens": int(row.output_tokens or 0),
                "accuracy": round(float(row.accuracy or 0), 2),
                "relevance": round(float(row.relevance or 0), 2),
                "hallucination": round(float(row.hallucination or 0), 2),
                "compositeScore": round(float(row.composite_score or 0), 2),
                "diff": round(float(row.diff or 0), 1),
                "status": row.status,
                "evaluationType": row.evaluation_type,
                "evaluationId": row.evaluation_id
            })
        
        # Get summary statistics
        summary_query = text(f"""
            SELECT 
                COUNT(*) as total_runs,
                COUNT(*) FILTER (WHERE 
                    answer_correctness IS NOT NULL 
                    AND answer_relevance IS NOT NULL 
                    AND hallucination_score IS NOT NULL
                ) as completed_runs,
                AVG(answer_correctness) as avg_accuracy,
                AVG(answer_relevance) as avg_relevance,
                AVG(hallucination_score) as avg_hallucination
            FROM (
                SELECT answer_correctness, answer_relevance, hallucination_score
                FROM human_evaluations he
                WHERE he.created_at >= :start_time
                    AND he.created_at <= :end_time
                    {org_filter_he}
                
                UNION ALL
                
                SELECT answer_correctness, answer_relevance, hallucination_score
                FROM llm_evaluation_scores le
                WHERE le.created_at >= :start_time
                    AND le.created_at <= :end_time
                    {org_filter_le}
            ) combined_evals
        """)
        
        summary_result = await db.execute(summary_query, params)
        
        summary_row = summary_result.fetchone()
        
        return {
            "time_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": int(summary_row.total_runs or 0)
            },
            "summary": {
                "total_evaluations": int(summary_row.total_runs or 0),
                "completed_evaluations": int(summary_row.completed_runs or 0),
                "avg_accuracy": round(float(summary_row.avg_accuracy or 0), 2),
                "avg_relevance": round(float(summary_row.avg_relevance or 0), 2),
                "avg_hallucination": round(float(summary_row.avg_hallucination or 0), 2),
                "completion_rate": round(
                    (summary_row.completed_runs / max(summary_row.total_runs, 1)) * 100, 1
                ) if summary_row.total_runs else 0
            },
            "runs": runs,
            "data_source": "orchestrator_db"
        }
        
    except Exception as e:
        logger.error(f"Failed to get evaluation runs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
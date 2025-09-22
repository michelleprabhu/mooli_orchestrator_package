"""
Cache Management API Router
============================

Provides endpoints for cache statistics, management, and monitoring.
Integrates with the existing prompt-response agent Redis cache.
"""

import json
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import logging
from typing import List

# Import the enhanced cache service
from ..services.enhanced_cache_service import get_cache_service, EnhancedCacheService
from ..db.database import db_manager

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/cache", tags=["cache"])


class CacheStatsResponse(BaseModel):
    """Response model for cache statistics"""
    total_entries: int
    hit_rate: float
    memory_usage: str
    cache_enabled: bool
    ttl_seconds: int
    similarity_threshold: float
    semantic_cache_enabled: bool


class CacheEntry(BaseModel):
    """Individual cache entry model"""
    key: str
    session_id: Optional[str]
    has_vector: bool
    created_at: Optional[float]
    last_accessed: Optional[float]
    prompt: Optional[str]
    response: Optional[str]
    label: Optional[str]


# New request models for cache management
class CacheConfigUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    semantic_cache_enabled: Optional[bool] = None
    similarity_threshold: Optional[float] = None
    default_ttl_seconds: Optional[int] = None


class CacheWarmRequest(BaseModel):
    session_id: str
    prompts: List[str]
    mode: str = "embed_only"


class CacheKeyDeleteRequest(BaseModel):
    keys: Optional[List[str]] = None
    pattern: Optional[str] = None
    session_id: Optional[str] = None


async def get_orchestrator_db():
    """Get orchestrator database session where Phoenix data resides."""
    async for session in db_manager.get_session():
        yield session

def get_cache() -> EnhancedCacheService:
    """Dependency to get enhanced cache instance"""
    try:
        cache = get_cache_service()
        return cache
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Enhanced cache service initialization failed: {str(e)}")


@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_statistics(
    cache: EnhancedCacheService = Depends(get_cache),
    db: AsyncSession = Depends(get_orchestrator_db),
    time_window_hours: int = 24
):
    """
    Get comprehensive cache statistics including hit rates and memory usage.
    Queries Phoenix spans for actual cache request metrics.
    
    Args:
        time_window_hours: Number of hours to look back for cache metrics (default: 24)
    
    Returns:
        CacheStatsResponse: Cache statistics and configuration
    """
    try:
        # Test cache connection
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Enhanced cache service unavailable")
        
        # Get cache statistics from enhanced service
        stats = await cache.get_stats()
        total_entries = stats.get("total_keys", 0)
        
        # Query Phoenix for actual cache hit rate metrics
        hit_rate = 0.0
        try:
            # Calculate time window
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=time_window_hours)
            
            # Query Phoenix spans for cache lookup metrics
            query = text("""
                WITH cache_lookups AS (
                    SELECT 
                        COUNT(*) as total_requests,
                        COUNT(*) FILTER (WHERE 
                            (s.attributes->'moolai'->'cache'->>'hit')::boolean = true
                        ) as cache_hits
                    FROM phoenix.spans s
                    WHERE s.name = 'moolai.cache.lookup'
                    AND s.start_time >= :start_time
                    AND s.start_time <= :end_time
                )
                SELECT 
                    total_requests,
                    cache_hits,
                    CASE 
                        WHEN total_requests > 0 THEN 
                            (cache_hits * 100.0 / total_requests)
                        ELSE 0 
                    END as hit_rate
                FROM cache_lookups;
            """)
            
            result = await db.execute(query, {
                'start_time': start_time,
                'end_time': end_time
            })
            
            row = result.fetchone()
            if row:
                hit_rate = float(row.hit_rate or 0)
                logger.info(f"Cache metrics from Phoenix: {row.total_requests} requests, {row.cache_hits} hits, {hit_rate:.1f}% hit rate")
            else:
                logger.info(f"No cache metrics found in Phoenix for the last {time_window_hours} hours")
                
        except Exception as e:
            logger.error(f"Failed to query Phoenix for cache metrics: {e}")
        
        # Get memory usage from Redis
        memory_usage = stats.get("memory_usage", "unknown")
        
        return CacheStatsResponse(
            total_entries=total_entries,
            hit_rate=hit_rate,
            memory_usage=memory_usage,
            cache_enabled=cache.is_enabled(),
            ttl_seconds=3600,  # Default TTL for enhanced cache
            similarity_threshold=0.85,  # Default similarity threshold
            semantic_cache_enabled=cache.is_semantic_enabled()
        )
        
    except Exception as e:
        logger.error(f"Failed to get cache statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache statistics: {str(e)}")


@router.get("/entries")
async def get_cache_entries(
    limit: int = 100,
    offset: int = 0,
    session_id: Optional[str] = None,
    cache: EnhancedCacheService = Depends(get_cache)
):
    """
    Get basic cache information - detailed entry listing not supported by enhanced cache service.
    
    Args:
        limit: Maximum number of entries to return (default: 100)
        offset: Number of entries to skip (default: 0)
        session_id: Optional session filter (not implemented in enhanced cache)
        
    Returns:
        Basic cache information instead of detailed entries
    """
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Enhanced cache service unavailable")
        
        # Enhanced cache service doesn't support entry listing
        # Return basic information instead
        stats = await cache.get_stats()
        
        return {
            "message": "Enhanced cache service doesn't support detailed entry listing",
            "stats": stats,
            "total_entries": stats.get("total_keys", 0),
            "memory_usage": stats.get("memory_usage", "unknown"),
            "semantic_enabled": cache.is_semantic_enabled(),
            "cache_enabled": cache.is_enabled()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache information: {str(e)}")


@router.post("/clear")
async def clear_cache(cache: EnhancedCacheService = Depends(get_cache)):
    """
    Clear all cache entries.
    
    Returns:
        Success message with cleared entry count
    """
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Enhanced cache service unavailable")
        
        # Get count before clearing
        stats = await cache.get_stats()
        entry_count = stats.get("total_keys", 0)
        
        # Clear the cache
        cleared_count = await cache.clear_all()
        
        return {
            "message": "Enhanced cache cleared successfully",
            "entries_cleared": cleared_count,
            "timestamp": time.time()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear enhanced cache: {str(e)}")


@router.get("/config")
async def get_cache_config(cache: EnhancedCacheService = Depends(get_cache)):
    """
    Get current enhanced cache configuration.

    Returns:
        Current enhanced cache configuration settings
    """
    try:
        config = await cache.get_current_config()
        return config

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get enhanced cache config: {str(e)}")


@router.put("/config")
async def update_cache_config_runtime(
    request: CacheConfigUpdateRequest,
    cache: EnhancedCacheService = Depends(get_cache)
):
    """Update cache configuration at runtime."""
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Cache service unavailable")

        # Get updates excluding unset fields
        updates = request.dict(exclude_unset=True)

        updated_config = await cache.update_runtime_config(updates)

        return {
            "message": "Configuration updated successfully",
            "config": updated_config
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update cache configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to update configuration")


@router.post("/config/reload")
async def reload_cache_config_from_env(cache: EnhancedCacheService = Depends(get_cache)):
    """Reload cache configuration from environment variables."""
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Cache service unavailable")

        updated_config = await cache.reload_config_from_env()

        return {
            "message": "Configuration reloaded from environment variables",
            "config": updated_config
        }

    except Exception as e:
        logger.error(f"Failed to reload cache configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to reload configuration")


@router.get("/keys")
async def list_cache_keys_paginated(
    page: int = 1,
    page_size: int = 20,
    pattern: Optional[str] = None,
    session_id: Optional[str] = None,
    cache: EnhancedCacheService = Depends(get_cache)
):
    """List cache keys with pagination and filtering."""
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Cache service unavailable")

        result = await cache.cache.list_keys_paginated(page, page_size, pattern, session_id)
        return result

    except Exception as e:
        logger.error(f"Failed to list cache keys: {e}")
        raise HTTPException(status_code=500, detail="Failed to list cache keys")


@router.delete("/keys")
async def delete_cache_keys(
    request: CacheKeyDeleteRequest,
    cache: EnhancedCacheService = Depends(get_cache)
):
    """Delete cache keys by pattern, session, or explicit list."""
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Cache service unavailable")

        deleted_count = await cache.cache.delete_keys_by_pattern(
            keys=request.keys,
            pattern=request.pattern,
            session_id=request.session_id
        )

        return {
            "deleted_count": deleted_count,
            "message": f"Successfully deleted {deleted_count} cache entries"
        }

    except Exception as e:
        logger.error(f"Failed to delete cache keys: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete cache keys")


@router.post("/warm")
async def warm_cache_endpoint(
    request: CacheWarmRequest,
    cache: EnhancedCacheService = Depends(get_cache)
):
    """Warm cache with batch prompts."""
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Cache service unavailable")

        result = await cache.cache.warm_cache_batch(
            session_id=request.session_id,
            prompts=request.prompts,
            mode=request.mode,
            embedder=cache.embedder
        )

        return result

    except Exception as e:
        logger.error(f"Failed to warm cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to warm cache")


@router.get("/export/json")
async def export_cache_json(cache: EnhancedCacheService = Depends(get_cache)):
    """Export cache data as JSON."""
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Cache service unavailable")

        data = await cache.cache.export_cache_json()

        return {
            "format": "json",
            "data": data,
            "total_entries": len(data),
            "exported_at": time.time()
        }

    except Exception as e:
        logger.error(f"Failed to export cache data: {e}")
        raise HTTPException(status_code=500, detail="Failed to export cache data")


@router.get("/health")
async def cache_health_check(cache: EnhancedCacheService = Depends(get_cache)):
    """
    Check enhanced cache service health and connectivity.
    
    Returns:
        Health status and connectivity information
    """
    try:
        # Test enhanced cache connection
        ping_result = await cache.ping()
        
        if ping_result:
            # Get enhanced cache stats
            try:
                stats = await cache.get_stats()
                
                return {
                    "status": "healthy",
                    "cache_type": "enhanced_semantic",
                    "redis_connected": True,
                    "cache_enabled": cache.is_enabled(),
                    "semantic_enabled": cache.is_semantic_enabled(),
                    "total_keys": stats.get("total_keys", 0),
                    "memory_usage": stats.get("memory_usage", "unknown"),
                    "timestamp": time.time()
                }
            except Exception as e:
                return {
                    "status": "degraded",
                    "cache_type": "enhanced_semantic",
                    "redis_connected": True,
                    "cache_enabled": cache.is_enabled(),
                    "warning": f"Could not get detailed stats: {str(e)}",
                    "timestamp": time.time()
                }
        else:
            return {
                "status": "unhealthy",
                "cache_type": "enhanced_semantic",
                "redis_connected": False,
                "cache_enabled": cache.is_enabled(),
                "error": "Enhanced cache Redis connection failed",
                "timestamp": time.time()
            }
            
    except Exception as e:
        return {
            "status": "error",
            "cache_type": "enhanced_semantic",
            "redis_connected": False,
            "cache_enabled": False,
            "error": str(e),
            "timestamp": time.time()
        }


@router.get("/export")
async def export_cache_data(format: str = "json", cache: EnhancedCacheService = Depends(get_cache)):
    """
    Export basic cache information - detailed data export not supported by enhanced cache service.
    
    Args:
        format: Export format ('json' only)
        
    Returns:
        Basic cache statistics instead of detailed data
    """
    try:
        if not await cache.ping():
            raise HTTPException(status_code=503, detail="Enhanced cache service unavailable")
        
        if format.lower() == "json":
            # Enhanced cache doesn't support detailed export
            # Return stats instead
            stats = await cache.get_stats()
            
            return {
                "format": "json",
                "message": "Enhanced cache service doesn't support detailed data export",
                "stats": stats,
                "cache_type": "enhanced_semantic",
                "total_entries": stats.get("total_keys", 0),
                "exported_at": time.time()
            }
        else:
            raise HTTPException(status_code=400, detail="Enhanced cache only supports 'json' format for basic stats")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export enhanced cache data: {str(e)}")
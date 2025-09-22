"""
Enhanced Caching Service with Semantic Similarity
=================================================

Advanced caching service that combines traditional key-based caching with 
semantic similarity matching using sentence transformers. Provides intelligent
cache hits based on meaning rather than exact text matches.
"""

import os
import json
import hashlib
import time
import asyncio
import zlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
import numpy as np

# Core dependencies
import redis
from sentence_transformers import SentenceTransformer
from prometheus_client import Counter, Histogram

from ..core.logging_config import get_logger
from ..db.database import get_db

logger = get_logger(__name__)

# Enable debug logging for cache operations
logger.setLevel('DEBUG')

# Metrics
CACHE_HITS = Counter("enhanced_cache_hits_total", "Total enhanced cache hits", ["type", "similarity_level"])
CACHE_MISSES = Counter("enhanced_cache_misses_total", "Total enhanced cache misses", ["reason"])
CACHE_OPERATIONS = Histogram("enhanced_cache_operation_duration_seconds", "Cache operation duration", ["operation"])

class SemanticEmbedder:
    """Manages sentence transformer embeddings for semantic similarity."""
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._init_lock = asyncio.Lock()
    
    async def _ensure_initialized(self):
        """Initialize the sentence transformer model."""
        if self._model is not None:
            return
            
        async with self._init_lock:
            if self._model is not None:
                return
                
            logger.info(f"🔄 Loading sentence transformer model: {self.model_name}")
            start_time = time.time()
            try:
                # Load model in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                self._model = await loop.run_in_executor(
                    None,
                    lambda: SentenceTransformer(self.model_name)
                )
                load_time = time.time() - start_time
                logger.info(f"✅ Sentence transformer model loaded successfully in {load_time:.2f}s")
            except Exception as e:
                logger.error(f"❌ Failed to load sentence transformer model: {e}")
                raise
    
    async def encode(self, texts: List[str]) -> Optional[np.ndarray]:
        """Encode texts into embeddings."""
        await self._ensure_initialized()

        if not texts:
            return None

        try:
            start_time = time.time()
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: self._model.encode(texts)
            )
            encode_time = time.time() - start_time
            logger.debug(f"📊 Encoded {len(texts)} texts in {encode_time:.3f}s")
            return np.array(embeddings)
        except Exception as e:
            logger.error(f"❌ Failed to encode texts: {e}")
            return None
    
    async def encode_single(self, text: str) -> Optional[np.ndarray]:
        """Encode single text into embedding."""
        embeddings = await self.encode([text])
        return embeddings[0] if embeddings is not None else None


class EnhancedRedisCache:
    """Enhanced Redis cache with semantic similarity and advanced features."""
    
    def __init__(self, db_index: int = 1):
        """
        Initialize Redis cache.
        
        Args:
            db_index: Redis database index (1 for LLM cache, 0 for sessions)
        """
        self.db_index = db_index
        
        # Use proper Docker service URLs instead of localhost
        if db_index == 1:
            redis_url = os.getenv("REDIS_LLM_CACHE_URL", "redis://redis:6379/1")
        else:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        
        self.client = redis.from_url(
            redis_url,
            decode_responses=False,
            socket_timeout=5,
            socket_connect_timeout=5,
            health_check_interval=30,
        )
        
        # Configuration
        self.enabled = os.getenv("CACHE_ENABLED", "true").lower() == "true"
        self.use_semantic_cache = os.getenv("USE_SEMANTIC_CACHE", "true").lower() == "true"
        self.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))
        self.cache_ttl = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour default
        
        # Key prefixes
        self.key_prefix = "enhanced_cache:v1"
        self.vector_suffix = ":vec"
        self.metadata_suffix = ":meta"
        
        logger.info(f"🚀 Enhanced Redis cache initialized | db={db_index} | enabled={self.enabled} | semantic={self.use_semantic_cache} | threshold={self.similarity_threshold} | ttl={self.cache_ttl}s")
        logger.debug(f"🔧 Cache configuration: redis_url={redis_url}, key_prefix={self.key_prefix}")
    
    def _make_key(self, session_id: str, content_hash: str) -> str:
        """Create a cache key."""
        return f"{self.key_prefix}:{session_id}:{content_hash}"
    
    def _hash_content(self, content: str) -> str:
        """Create hash for content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _compress(self, value: Any) -> bytes:
        """Compress value for storage."""
        if isinstance(value, np.ndarray):
            value = value.tolist()
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        elif not isinstance(value, str):
            value = str(value)
        return zlib.compress(value.encode('utf-8'))
    
    def _decompress(self, value: bytes) -> Any:
        """Decompress value from storage."""
        try:
            decompressed = zlib.decompress(value).decode('utf-8')
            return json.loads(decompressed)
        except json.JSONDecodeError:
            return decompressed
        except Exception as e:
            logger.error(f"Failed to decompress value: {e}")
            return None
    
    async def ping(self) -> bool:
        """Check Redis connection."""
        try:
            # Use the sync ping method since this is sync Redis client
            start_time = time.time()
            result = bool(self.client.ping())
            ping_time = (time.time() - start_time) * 1000  # Convert to ms
            logger.debug(f"🏓 Redis ping: {ping_time:.2f}ms | status={'OK' if result else 'FAILED'}")
            return result
        except Exception as e:
            logger.error(f"❌ Redis ping failed: {e}")
            return False
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        if vec1 is None or vec2 is None:
            return 0.0
        
        try:
            dot_product = np.dot(vec1, vec2)
            norm_product = np.linalg.norm(vec1) * np.linalg.norm(vec2)
            return float(dot_product / norm_product) if norm_product != 0 else 0.0
        except Exception as e:
            logger.error(f"Failed to calculate cosine similarity: {e}")
            return 0.0
    
    async def store(
        self,
        session_id: str,
        prompt: str,
        response: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedder: Optional[SemanticEmbedder] = None
    ) -> bool:
        """
        Store prompt-response pair with optional semantic indexing.
        
        Args:
            session_id: Session identifier
            prompt: Original prompt text
            response: Generated response text
            metadata: Additional metadata
            embedder: Semantic embedder for vector storage
            
        Returns:
            True if stored successfully
        """
        if not self.enabled:
            return False
        
        start_time = time.time()
        content_hash = self._hash_content(prompt)
        key = self._make_key(session_id, content_hash)
        
        try:
            # Prepare cache entry
            cache_entry = {
                "prompt": prompt,
                "response": response,
                "session_id": session_id,
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {}
            }
            
            # Store main entry
            compressed_entry = self._compress(cache_entry)
            entry_size = len(compressed_entry)
            self.client.setex(key, self.cache_ttl, compressed_entry)
            logger.debug(f"📦 Storing cache entry | key={key[:40]}... | size={entry_size} bytes | ttl={self.cache_ttl}s")

            # Store metadata
            meta_key = f"{key}{self.metadata_suffix}"
            meta_entry = {
                "created_at": time.time(),
                "last_accessed": time.time(),
                "access_count": 0,
                "prompt_length": len(prompt),
                "response_length": len(response)
            }
            compressed_meta = self._compress(meta_entry)
            self.client.setex(meta_key, self.cache_ttl, compressed_meta)
            
            # Store semantic vector if enabled
            if self.use_semantic_cache and embedder:
                try:
                    embedding = await embedder.encode_single(prompt)
                    if embedding is not None:
                        vector_key = f"{key}{self.vector_suffix}"
                        compressed_vector = self._compress(embedding.tolist())
                        vector_size = len(compressed_vector)
                        self.client.setex(vector_key, self.cache_ttl, compressed_vector)
                        logger.debug(f"🧠 Stored semantic vector | key={vector_key[:40]}... | size={vector_size} bytes | dim={len(embedding)}")
                except Exception as e:
                    logger.warning(f"Failed to store semantic vector: {e}")
            
            duration = time.time() - start_time
            CACHE_OPERATIONS.labels(operation="store").observe(duration)

            logger.info(f"✅ Cache STORE successful | session={session_id[:8]}... | duration={duration:.3f}s | semantic={self.use_semantic_cache and embedder is not None}")
            logger.debug(f"📊 Store details | key={key} | prompt_len={len(prompt)} | response_len={len(response)}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to store cache entry | session={session_id[:8]}... | error={e}")
            return False
    
    async def retrieve(
        self,
        session_id: str,
        prompt: str,
        embedder: Optional[SemanticEmbedder] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached response with exact and semantic matching.
        
        Args:
            session_id: Session identifier
            prompt: Query prompt
            embedder: Semantic embedder for similarity matching
            
        Returns:
            Cache entry if found, None otherwise
        """
        if not self.enabled:
            return None
        
        start_time = time.time()
        content_hash = self._hash_content(prompt)
        key = self._make_key(session_id, content_hash)
        
        try:
            # Try exact match first
            cached_data = self.client.get(key)
            if cached_data:
                entry = self._decompress(cached_data)
                if entry:
                    # Update access metadata
                    await self._update_access_metadata(key)
                    
                    duration = time.time() - start_time
                    CACHE_OPERATIONS.labels(operation="retrieve_exact").observe(duration)
                    CACHE_HITS.labels(type="exact", similarity_level="1.0").inc()
                    
                    logger.info(f"🎯 Cache HIT (exact) | session={session_id[:8]}... | duration={duration:.3f}s")
                    logger.debug(f"🔍 Exact match details | key={key} | prompt_len={len(prompt)}")
                    entry['cache_hit_type'] = 'exact'
                    entry['similarity_score'] = 1.0
                    return entry
            
            # Try semantic matching if enabled
            if self.use_semantic_cache and embedder:
                semantic_result = await self._find_semantic_match(session_id, prompt, embedder)
                if semantic_result:
                    entry, similarity = semantic_result
                    await self._update_access_metadata(entry.get('_cache_key', ''))
                    
                    duration = time.time() - start_time
                    CACHE_OPERATIONS.labels(operation="retrieve_semantic").observe(duration)
                    
                    # Determine similarity level for metrics
                    similarity_level = "high" if similarity >= 0.95 else "medium" if similarity >= 0.85 else "low"
                    CACHE_HITS.labels(type="semantic", similarity_level=similarity_level).inc()
                    
                    logger.info(f"🧩 Cache HIT (semantic) | session={session_id[:8]}... | similarity={similarity:.3f} | duration={duration:.3f}s")
                    logger.debug(f"🔮 Semantic match details | threshold={self.similarity_threshold} | level={similarity_level}")
                    entry['cache_hit_type'] = 'semantic'
                    entry['similarity_score'] = similarity
                    return entry
            
            # Cache miss
            duration = time.time() - start_time
            CACHE_OPERATIONS.labels(operation="retrieve_miss").observe(duration)
            CACHE_MISSES.labels(reason="not_found").inc()

            logger.info(f"❌ Cache MISS | session={session_id[:8]}... | duration={duration:.3f}s | semantic_enabled={self.use_semantic_cache}")
            logger.debug(f"🔍 Miss details | key={key} | prompt_hash={content_hash}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve from cache: {e}")
            CACHE_MISSES.labels(reason="error").inc()
            return None
    
    async def _find_semantic_match(
        self,
        session_id: str,
        query: str,
        embedder: SemanticEmbedder
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        """Find semantically similar cached entry."""
        try:
            # Get query embedding
            query_embedding = await embedder.encode_single(query)
            if query_embedding is None:
                return None
            
            # Search pattern for session vectors
            pattern = f"{self.key_prefix}:{session_id}:*{self.vector_suffix}"
            best_match = None
            best_similarity = 0.0
            candidates_checked = 0
            start_search = time.time()
            
            for vector_key in self.client.scan_iter(match=pattern):
                vector_key_str = vector_key.decode() if isinstance(vector_key, bytes) else str(vector_key)
                candidates_checked += 1
                
                try:
                    # Get stored vector
                    vector_data = self.client.get(vector_key_str)
                    if not vector_data:
                        continue
                    
                    stored_embedding = self._decompress(vector_data)
                    if not stored_embedding:
                        continue
                    
                    stored_vector = np.array(stored_embedding, dtype=np.float32)
                    
                    # Calculate similarity
                    similarity = self._cosine_similarity(query_embedding, stored_vector)
                    logger.debug(f"🔍 Checking semantic candidate #{candidates_checked} | similarity={similarity:.3f} | threshold={self.similarity_threshold}")
                    
                    if similarity > best_similarity and similarity >= self.similarity_threshold:
                        # Get the main cache entry
                        main_key = vector_key_str.replace(self.vector_suffix, '')
                        cached_data = self.client.get(main_key)
                        
                        if cached_data:
                            entry = self._decompress(cached_data)
                            if entry:
                                entry['_cache_key'] = main_key
                                best_match = entry
                                best_similarity = similarity
                
                except Exception as e:
                    logger.warning(f"Failed to process vector key {vector_key_str}: {e}")
                    continue
            
            search_time = time.time() - start_search
            if best_match:
                logger.debug(f"🎯 Semantic search completed | candidates={candidates_checked} | best_similarity={best_similarity:.3f} | time={search_time:.3f}s")
            else:
                logger.debug(f"🕳 No semantic match found | candidates={candidates_checked} | time={search_time:.3f}s")
            return (best_match, best_similarity) if best_match else None
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return None
    
    async def _update_access_metadata(self, key: str):
        """Update access metadata for cache entry."""
        if not key:
            return
            
        try:
            meta_key = f"{key}{self.metadata_suffix}"
            meta_data = self.client.get(meta_key)
            
            if meta_data:
                metadata = self._decompress(meta_data)
                if metadata and isinstance(metadata, dict):
                    metadata['last_accessed'] = time.time()
                    metadata['access_count'] = metadata.get('access_count', 0) + 1

                    compressed_meta = self._compress(metadata)
                    self.client.setex(meta_key, self.cache_ttl, compressed_meta)
                    logger.debug(f"📊 Updated access metadata | key={key[:40]}... | count={metadata['access_count']}")
        
        except Exception as e:
            logger.debug(f"⚠️ Failed to update access metadata | key={key[:40]}... | error={e}")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        try:
            logger.debug(f"📊 Gathering cache statistics...")
            # Basic Redis info
            info = self.client.info()
            
            # Count different types of keys
            total_keys = 0
            vector_keys = 0
            metadata_keys = 0
            cache_entries = 0
            
            for key in self.client.scan_iter(match=f"{self.key_prefix}:*"):
                key_str = key.decode() if isinstance(key, bytes) else str(key)
                total_keys += 1
                
                if key_str.endswith(self.vector_suffix):
                    vector_keys += 1
                elif key_str.endswith(self.metadata_suffix):
                    metadata_keys += 1
                else:
                    cache_entries += 1
            
            # Calculate memory usage (approximate)
            memory_used = info.get('used_memory', 0)
            
            stats = {
                "enabled": self.enabled,
                "use_semantic_cache": self.use_semantic_cache,
                "similarity_threshold": self.similarity_threshold,
                "cache_ttl": self.cache_ttl,
                "redis_connected": await self.ping(),
                "total_keys": total_keys,
                "cache_entries": cache_entries,
                "vector_keys": vector_keys,
                "metadata_keys": metadata_keys,
                "memory_used_bytes": memory_used,
                "memory_used_mb": round(memory_used / (1024 * 1024), 2),
                "uptime_seconds": info.get('uptime_in_seconds', 0)
            }
            logger.info(f"📊 Cache stats | entries={cache_entries} | vectors={vector_keys} | memory={stats['memory_used_mb']}MB")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Failed to get cache stats: {e}")
            return {
                "enabled": self.enabled,
                "error": str(e)
            }
    
    async def clear_session_cache(self, session_id: str) -> int:
        """Clear all cache entries for a specific session."""
        try:
            pattern = f"{self.key_prefix}:{session_id}:*"
            keys_deleted = 0
            logger.debug(f"🗑 Clearing cache for session {session_id[:8]}...")

            for key in self.client.scan_iter(match=pattern):
                self.client.delete(key)
                keys_deleted += 1

            logger.info(f"🗑 Cleared {keys_deleted} cache keys for session {session_id[:8]}...")
            return keys_deleted
            
        except Exception as e:
            logger.error(f"❌ Failed to clear session cache | session={session_id[:8]}... | error={e}")
            return 0
    
    async def clear_all_cache(self) -> int:
        """Clear all cache entries."""
        try:
            pattern = f"{self.key_prefix}:*"
            keys_deleted = 0
            logger.warning(f"⚠️ Clearing ALL cache entries...")

            for key in self.client.scan_iter(match=pattern):
                self.client.delete(key)
                keys_deleted += 1

            logger.warning(f"🗑 Cleared ALL {keys_deleted} cache keys")
            return keys_deleted

        except Exception as e:
            logger.error(f"❌ Failed to clear all cache: {e}")
            return 0

    async def list_keys_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        pattern: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """List cache keys with pagination and filtering."""
        logger.debug(f"🔍 Listing cache keys | page={page} | size={page_size} | pattern={pattern} | session={session_id[:8] if session_id else 'all'}")
        # Build search pattern
        if session_id:
            search_pattern = f"{self.key_prefix}:{session_id}:*"
        elif pattern:
            search_pattern = f"{self.key_prefix}:*{pattern}*"
        else:
            search_pattern = f"{self.key_prefix}:*"

        # Get all matching keys (excluding meta and vector)
        all_keys = []
        keys_list = await self._scan_keys_async(search_pattern)
        for key in keys_list:
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            if not (key_str.endswith(self.metadata_suffix) or key_str.endswith(self.vector_suffix)):
                all_keys.append(key_str)

        # Paginate
        total = len(all_keys)
        start = (page - 1) * page_size
        end = start + page_size
        visible_keys = all_keys[start:end]

        # Get detailed info for visible keys
        key_details = []
        for key in visible_keys:
            details = await self._get_key_info_async(key)
            key_details.append(details)

        result = {
            "keys": key_details,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": end < total
        }
        logger.debug(f"📝 Found {total} keys, showing {len(key_details)} on page {page}")
        return result

    async def _scan_keys_async(self, pattern: str):
        """Async wrapper for Redis SCAN operation."""
        import asyncio
        loop = asyncio.get_event_loop()

        def _scan_blocking():
            return list(self.client.scan_iter(match=pattern))

        return await loop.run_in_executor(None, _scan_blocking)

    async def _get_key_info_async(self, key: str) -> Dict[str, Any]:
        """Get detailed information about a cache key asynchronously."""
        import asyncio
        loop = asyncio.get_event_loop()

        def _get_info_blocking():
            # Parse session_id and hash from key
            parts = key.split(":")
            session_id = parts[2] if len(parts) > 2 else None
            content_hash = parts[3] if len(parts) > 3 else None

            # Get metadata
            meta_key = f"{key}{self.metadata_suffix}"
            meta_data = self.client.get(meta_key)
            metadata = self._decompress(meta_data) if meta_data else {}

            # Check for vector
            vec_key = f"{key}{self.vector_suffix}"
            has_vector = bool(self.client.exists(vec_key))

            # Get TTL
            ttl = self.client.ttl(key)

            # Get cache entry for prompt info
            cache_data = self.client.get(key)
            entry = self._decompress(cache_data) if cache_data else {}

            return {
                "key": key,
                "session_id": session_id,
                "content_hash": content_hash,
                "has_vector": has_vector,
                "created_at": metadata.get("created_at"),
                "last_accessed": metadata.get("last_accessed"),
                "access_count": metadata.get("access_count", 0),
                "ttl_remaining": ttl if ttl > 0 else None,
                "prompt": entry.get("prompt", "")[:100] if isinstance(entry, dict) else "",
                "response_length": metadata.get("response_length", 0)
            }

        return await loop.run_in_executor(None, _get_info_blocking)

    async def delete_keys_by_pattern(
        self,
        pattern: Optional[str] = None,
        session_id: Optional[str] = None,
        keys: Optional[List[str]] = None
    ) -> int:
        """Delete keys by pattern, session, or explicit list."""
        import asyncio
        loop = asyncio.get_event_loop()

        def _delete_blocking():
            keys_to_delete = []

            if keys:
                keys_to_delete = keys
            elif session_id:
                pattern = f"{self.key_prefix}:{session_id}:*"
                keys_to_delete = [
                    k.decode() if isinstance(k, bytes) else str(k)
                    for k in self.client.scan_iter(match=pattern)
                ]
            elif pattern:
                search_pattern = f"{self.key_prefix}:*{pattern}*"
                keys_to_delete = [
                    k.decode() if isinstance(k, bytes) else str(k)
                    for k in self.client.scan_iter(match=search_pattern)
                ]

            # Delete main keys and associated meta/vector keys
            deleted_count = 0
            for key in keys_to_delete:
                if self.client.delete(key):
                    deleted_count += 1

                # Delete associated metadata and vector
                self.client.delete(f"{key}{self.metadata_suffix}")
                self.client.delete(f"{key}{self.vector_suffix}")

            return deleted_count

        return await loop.run_in_executor(None, _delete_blocking)

    async def warm_cache_batch(
        self,
        session_id: str,
        prompts: List[str],
        mode: str = "embed_only",
        embedder: Optional[SemanticEmbedder] = None
    ) -> Dict[str, Any]:
        """Batch cache warming with modes: embed_only, full."""
        logger.info(f"🔥 Starting cache warming | session={session_id[:8]}... | prompts={len(prompts)} | mode={mode}")
        warmed_count = 0
        failed_count = 0
        start_time = time.time()

        for prompt in prompts:
            try:
                if mode == "embed_only":
                    success = await self._warm_embedding_only(session_id, prompt, embedder)
                else:  # full mode - placeholder for future LLM integration
                    success = await self._warm_full_response(session_id, prompt, embedder)

                if success:
                    warmed_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f"❌ Failed to warm prompt '{prompt[:50]}...': {e}")
                failed_count += 1

        duration = time.time() - start_time
        logger.info(f"🎯 Cache warming completed | warmed={warmed_count} | failed={failed_count} | duration={duration:.2f}s")
        return {
            "message": f"Cache warming completed",
            "warmed_count": warmed_count,
            "failed_count": failed_count,
            "mode": mode,
            "duration_seconds": round(duration, 2)
        }

    async def _warm_embedding_only(self, session_id: str, prompt: str, embedder: Optional[SemanticEmbedder]) -> bool:
        """Warm cache with embedding only."""
        if not embedder:
            logger.debug(f"⚠️ No embedder available for warming")
            return False

        try:
            logger.debug(f"🧠 Warming embedding for prompt: {prompt[:30]}...")
            embedding = await embedder.encode_single(prompt)
            if embedding is None:
                return False

            content_hash = self._hash_content(prompt)
            key = self._make_key(session_id, content_hash)

            # Store minimal entry
            cache_entry = {
                "prompt": prompt,
                "response": "",  # Empty response for embed-only
                "session_id": session_id,
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {"source": "warmed_embed_only"}
            }

            # Store entry, metadata, and vector
            compressed_entry = self._compress(cache_entry)
            self.client.setex(key, self.cache_ttl, compressed_entry)

            # Store metadata
            meta_key = f"{key}{self.metadata_suffix}"
            meta_entry = {
                "created_at": time.time(),
                "last_accessed": time.time(),
                "access_count": 0,
                "prompt_length": len(prompt),
                "response_length": 0
            }
            compressed_meta = self._compress(meta_entry)
            self.client.setex(meta_key, self.cache_ttl, compressed_meta)

            # Store vector
            vector_key = f"{key}{self.vector_suffix}"
            compressed_vector = self._compress(embedding.tolist())
            self.client.setex(vector_key, self.cache_ttl, compressed_vector)

            logger.debug(f"✅ Successfully warmed embedding | key={key[:40]}...")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to warm embedding | prompt={prompt[:30]}... | error={e}")
            return False

    async def _warm_full_response(self, session_id: str, prompt: str, embedder: Optional[SemanticEmbedder]) -> bool:
        """Warm cache with full response (placeholder for future implementation)."""
        try:
            if not embedder:
                return False

            embedding = await embedder.encode_single(prompt)
            if embedding is None:
                return False

            # Create placeholder response (in production, integrate with LLM service)
            response = f"[Warmed response for: {prompt[:50]}...]"

            # Store using existing store method
            metadata = {"source": "warmed_full"}
            logger.debug(f"🔥 Warming full response for prompt: {prompt[:30]}...")
            success = await self.store(
                session_id=session_id,
                prompt=prompt,
                response=response,
                metadata=metadata,
                embedder=embedder
            )

            if success:
                logger.debug(f"✅ Successfully warmed full response | prompt={prompt[:30]}...")
            return success

        except Exception as e:
            logger.error(f"❌ Failed to warm full response: {e}")
            return False

    async def export_cache_json(self) -> List[Dict[str, Any]]:
        """Export cache data matching frontend expectations."""
        import asyncio
        loop = asyncio.get_event_loop()
        logger.info(f"📤 Starting cache export...")

        def _export_blocking():
            records = []
            start_time = time.time()

            try:
                for key in self.client.scan_iter(match=f"{self.key_prefix}:*"):
                    key_str = key.decode() if isinstance(key, bytes) else str(key)

                    # Skip metadata and vector keys
                    if key_str.endswith(self.metadata_suffix) or key_str.endswith(self.vector_suffix):
                        continue

                    # Get cache entry
                    cache_data = self.client.get(key_str)
                    entry = self._decompress(cache_data) if cache_data else {}

                    # Get metadata
                    meta_key = f"{key_str}{self.metadata_suffix}"
                    meta_data = self.client.get(meta_key)
                    metadata = self._decompress(meta_data) if meta_data else {}

                    # Check for vector
                    vec_key = f"{key_str}{self.vector_suffix}"
                    has_vector = bool(self.client.exists(vec_key))

                    # Parse key parts
                    parts = key_str.split(":")
                    session_id = parts[2] if len(parts) > 2 else None
                    content_hash = parts[3] if len(parts) > 3 else None

                    record = {
                        "key": key_str,
                        "session_id": session_id,
                        "content_hash": content_hash,
                        "has_vector": has_vector,
                        "created_at": metadata.get("created_at"),
                        "last_accessed": metadata.get("last_accessed"),
                        "access_count": metadata.get("access_count", 0),
                        "prompt": entry.get("prompt", "") if isinstance(entry, dict) else "",
                        "response": entry.get("response", "") if isinstance(entry, dict) else str(entry),
                        "metadata": entry.get("metadata", {}) if isinstance(entry, dict) else {}
                    }
                    records.append(record)

            except Exception as e:
                logger.error(f"❌ Failed to export cache data: {e}")

            export_time = time.time() - start_time
            logger.info(f"📤 Cache export completed | records={len(records)} | duration={export_time:.2f}s")
            return records

        return await loop.run_in_executor(None, _export_blocking)


class EnhancedCacheService:
    """Enhanced caching service with semantic similarity matching."""

    def __init__(self):
        logger.info(f"🎆 Initializing EnhancedCacheService...")
        self.cache = EnhancedRedisCache(db_index=1)  # Use DB 1 for LLM cache
        self.embedder = SemanticEmbedder()
        logger.debug(f"🤖 Cache service components initialized")

        # Load runtime configuration overrides from Redis if they exist
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._load_runtime_config_from_redis())
        except RuntimeError:
            # No event loop running yet - will be loaded on first API call
            pass

        # Domain classification mappings
        self.domain_mappings = {
            "AI.NLP.TransformerModels": ["transformer", "bert", "gpt", "llm", "attention"],
            "AI.ML.ModelTypes": ["classification", "regression", "supervised", "unsupervised"],
            "AI.NLP.SemanticSearch": ["embedding", "vector", "similarity"],
            "Finance.Accounting": ["revenue", "accounting", "financial", "ledger"],
            "Finance.Risk": ["credit", "risk", "loan", "default"],
            "Medicine.General": ["diagnosis", "symptom", "treatment", "medical"],
            "Tech.Databases": ["sql", "database", "query", "index"],
            "Tech.Systems": ["cache", "redis", "system", "architecture"],
            "Tech.Backend": ["api", "endpoint", "rest", "backend"]
        }
    
    def _classify_prompt(self, prompt: str) -> str:
        """Internal prompt classification method."""
        prompt_lower = prompt.lower()

        for domain, keywords in self.domain_mappings.items():
            if any(keyword in prompt_lower for keyword in keywords):
                logger.debug(f"🏷 Classified prompt to domain: {domain}")
                return domain

        logger.debug(f"🏷 No specific domain match, using General.Uncategorized")
        return "General.Uncategorized"
    
    def classify_prompt(self, prompt: str) -> str:
        """
        Public method to classify prompt into domain categories.
        
        Args:
            prompt: The prompt text to classify
            
        Returns:
            Domain classification string
        """
        return self._classify_prompt(prompt)
    
    async def get_cached_response(
        self,
        session_id: str,
        prompt: str,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached response for prompt with semantic matching.
        
        Args:
            session_id: Session identifier
            prompt: Query prompt
            user_id: User identifier for tracking
            organization_id: Organization identifier
            
        Returns:
            Cached response data if found
        """
        try:
            result = await self.cache.retrieve(session_id, prompt, self.embedder)
            
            if result:
                cache_type = result.get('cache_hit_type', 'unknown')
                similarity = result.get('similarity_score', 0.0)
                logger.info(
                    f"🔁 CACHE HIT | session={session_id[:8]}... | type={cache_type} | similarity={similarity:.3f} | "
                    f"user={user_id[:8] if user_id else 'none'}... | org={organization_id[:8] if organization_id else 'none'}..."
                )

                # Add retrieval metadata
                result['retrieved_at'] = datetime.now(timezone.utc).isoformat()
                result['user_id'] = user_id
                result['organization_id'] = organization_id
            else:
                logger.debug(f"🔍 No cache hit for session {session_id[:8]}...")

            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to get cached response | session={session_id[:8]}... | error={e}")
            return None
    
    async def store_response(
        self,
        session_id: str,
        prompt: str,
        response: str,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store prompt-response pair in cache with semantic indexing.
        
        Args:
            session_id: Session identifier
            prompt: Original prompt
            response: Generated response
            user_id: User identifier
            organization_id: Organization identifier
            metadata: Additional metadata
            
        Returns:
            True if stored successfully
        """
        try:
            # Prepare metadata
            enhanced_metadata = {
                "user_id": user_id,
                "organization_id": organization_id,
                "domain": self._classify_prompt(prompt),
                "response_length": len(response),
                "prompt_length": len(prompt),
                **(metadata or {})
            }
            
            success = await self.cache.store(
                session_id=session_id,
                prompt=prompt,
                response=response,
                metadata=enhanced_metadata,
                embedder=self.embedder
            )
            
            if success:
                logger.info(f"💾 STORED in cache | session={session_id[:8]}... | domain={enhanced_metadata['domain']} | "
                           f"prompt_len={len(prompt)} | response_len={len(response)}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Failed to store response in cache | session={session_id[:8]}... | error={e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        logger.debug(f"📊 Retrieving cache statistics...")
        return await self.cache.get_cache_stats()
    
    async def ping(self) -> bool:
        """Check Redis connection via underlying cache."""
        return await self.cache.ping()
    
    async def clear_session(self, session_id: str) -> int:
        """Clear cache for specific session."""
        logger.info(f"🗑 Clearing cache for session {session_id[:8]}...")
        return await self.cache.clear_session_cache(session_id)
    
    async def clear_all(self) -> int:
        """Clear all cache entries."""
        logger.warning(f"⚠️ Clearing ALL cache entries...")
        return await self.cache.clear_all_cache()
    
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self.cache.enabled
    
    def is_semantic_enabled(self) -> bool:
        """Check if semantic caching is enabled."""
        return self.cache.use_semantic_cache

    async def get_current_config(self) -> Dict[str, Any]:
        """Get current configuration maintaining existing field names."""
        return {
            "enabled": self.cache.enabled,
            "semantic_cache_enabled": self.cache.use_semantic_cache,  # Match existing API
            "cache_type": "enhanced_semantic",
            "default_ttl_seconds": self.cache.cache_ttl,              # Match existing API
            "similarity_threshold": self.cache.similarity_threshold,   # Already 0.0-1.0
            "redis_db": self.cache.db_index,
            "embedding_model": "all-MiniLM-L6-v2"
        }

    async def reload_config_from_env(self) -> Dict[str, Any]:
        """Hot-reload configuration from environment variables."""
        old_config = await self.get_current_config()

        # Update cache instance with new environment values
        self.cache.enabled = os.getenv("CACHE_ENABLED", "true").lower() == "true"
        self.cache.use_semantic_cache = os.getenv("USE_SEMANTIC_CACHE", "true").lower() == "true"
        self.cache.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))
        self.cache.cache_ttl = int(os.getenv("CACHE_TTL", "3600"))

        new_config = await self.get_current_config()
        logger.info(f"🔄 Cache configuration reloaded from environment | "
                   f"enabled: {old_config['enabled']} → {new_config['enabled']} | "
                   f"semantic: {old_config['semantic_cache_enabled']} → {new_config['semantic_cache_enabled']} | "
                   f"threshold: {old_config['similarity_threshold']} → {new_config['similarity_threshold']}")

        return await self.get_current_config()

    async def update_runtime_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update configuration at runtime and optionally persist to Redis."""
        # Apply updates to running cache instance
        if "enabled" in updates:
            self.cache.enabled = bool(updates["enabled"])

        if "semantic_cache_enabled" in updates:
            self.cache.use_semantic_cache = bool(updates["semantic_cache_enabled"])

        if "similarity_threshold" in updates:
            threshold = float(updates["similarity_threshold"])
            # Ensure threshold is in valid range
            if 0.0 <= threshold <= 1.0:
                self.cache.similarity_threshold = threshold
            else:
                raise ValueError("Similarity threshold must be between 0.0 and 1.0")

        if "default_ttl_seconds" in updates:
            ttl = int(updates["default_ttl_seconds"])
            if ttl > 0:
                self.cache.cache_ttl = ttl
            else:
                raise ValueError("TTL must be positive")

        # Optionally store runtime config in Redis for persistence across restarts
        await self._store_runtime_config_in_redis(updates)

        logger.info(f"✅ Cache configuration updated at runtime | changes={updates}")

        return await self.get_current_config()

    async def _store_runtime_config_in_redis(self, updates: Dict[str, Any]):
        """Store runtime configuration changes in Redis DB 2."""
        try:
            # Use Redis DB 2 for configuration storage
            import redis
            config_redis = redis.from_url(
                os.getenv("REDIS_URL", "redis://redis:6379/2"),
                decode_responses=True
            )

            # Store individual config values with timestamps
            timestamp = time.time()
            for key, value in updates.items():
                config_key = f"cache_config:runtime:{key}"
                config_data = {
                    "value": value,
                    "updated_at": timestamp,
                    "source": "runtime_update"
                }
                config_redis.hset(config_key, mapping=config_data)

            logger.debug(f"💾 Runtime configuration persisted to Redis DB 2 | keys={len(updates)}")

        except Exception as e:
            logger.debug(f"⚠️ Failed to persist runtime config to Redis (non-critical): {e}")
            # Don't fail the config update if Redis storage fails

    async def _load_runtime_config_from_redis(self):
        """Load any runtime configuration overrides from Redis DB 2."""
        try:
            import redis
            config_redis = redis.from_url(
                os.getenv("REDIS_URL", "redis://redis:6379/2"),
                decode_responses=True
            )

            # Check for runtime config overrides
            runtime_configs = {}
            for key in config_redis.scan_iter(match="cache_config:runtime:*"):
                config_data = config_redis.hgetall(key)
                if config_data:
                    config_name = key.split(":")[-1]
                    runtime_configs[config_name] = config_data.get("value")

            if runtime_configs:
                logger.info(f"🔄 Loaded runtime configuration overrides from Redis | configs={list(runtime_configs.keys())}")
                # Apply runtime overrides
                await self.update_runtime_config(runtime_configs)
            else:
                logger.debug(f"🔍 No runtime configuration overrides found in Redis")

        except Exception as e:
            logger.debug(f"⚠️ Failed to load runtime config from Redis (non-critical): {e}")


# Global service instance
_cache_service = None

def get_cache_service() -> EnhancedCacheService:
    """Get or create the global cache service instance."""
    global _cache_service
    if _cache_service is None:
        logger.info(f"🚀 Creating global cache service instance...")
        _cache_service = EnhancedCacheService()
        logger.info(f"✅ Global cache service instance created")
    return _cache_service
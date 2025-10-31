"""
Redis utility abstractions for caching operations
"""

import logging
from typing import Optional, Dict, Any, Union, List
from datetime import datetime, timedelta
import hashlib
from functools import lru_cache
import asyncio

import redis.asyncio as redis
import orjson
from redis.exceptions import RedisError, ConnectionError

from .config import get_redis_config, RedisConfig

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Centralized Redis cache manager with connection pooling,
    serialization utilities, and common caching patterns.
    """

    def __init__(self, config: Optional[RedisConfig] = None):
        self.config = config or get_redis_config()
        self._pool: Optional[redis.ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize Redis connection pool and client"""
        if self._initialized:
            return

        logger.info(f"Initializing Redis connection to {self.config.host}:{self.config.port}")

        try:
            # Create connection pool
            pool_kwargs = {
                "host": self.config.host,
                "port": self.config.port,
                "db": self.config.db,
                "max_connections": self.config.max_connections,
                "socket_timeout": self.config.socket_timeout,
                "socket_connect_timeout": self.config.socket_connect_timeout,
                "decode_responses": self.config.decode_responses,
                "retry_on_timeout": True,
                "retry_on_error": [ConnectionError],
            }

            if self.config.password:
                pool_kwargs["password"] = self.config.password

            self._pool = redis.ConnectionPool(**pool_kwargs)
            self._client = redis.Redis(connection_pool=self._pool)

            # Test connection
            await self._client.ping()
            logger.info("Redis connection established successfully")

            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise

    async def cleanup(self) -> None:
        """Cleanup Redis connections"""
        if self._pool:
            await self._pool.disconnect()
            self._initialized = False
            logger.info("Redis connections closed")

    @property
    def client(self) -> redis.Redis:
        """Get the Redis client instance"""
        if not self._initialized:
            raise RuntimeError("Cache manager not initialized. Call initialize() first.")
        return self._client

    async def health_check(self) -> Dict[str, Any]:
        """Perform Redis health check"""
        try:
            if not self._initialized:
                return {"status": "error", "message": "Redis not initialized"}

            # Test basic connectivity
            pong = await self._client.ping()
            if not pong:
                return {"status": "unhealthy", "message": "Ping failed"}

            # Get Redis info
            info = await self._client.info()

            return {
                "status": "healthy",
                "version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "total_commands_processed": info.get("total_commands_processed", 0),
            }

        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    # Serialization utilities
    def serialize(self, data: Any) -> bytes:
        """Serialize data using orjson for performance"""
        try:
            return orjson.dumps(data)
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            raise

    def deserialize(self, data: bytes) -> Any:
        """Deserialize data using orjson"""
        try:
            if data is None:
                return None
            return orjson.loads(data)
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            raise

    # Basic cache operations
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache with automatic deserialization"""
        try:
            raw_data = await self._client.get(key)
            return self.deserialize(raw_data) if raw_data else None
        except RedisError as e:
            logger.warning(f"Redis get failed for key {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """Set value in cache with automatic serialization"""
        try:
            serialized_value = self.serialize(value)
            ttl = ttl_seconds or self.config.default_ttl_seconds

            await self._client.setex(key, ttl, serialized_value)
            return True
        except RedisError as e:
            logger.warning(f"Redis set failed for key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            result = await self._client.delete(key)
            return result > 0
        except RedisError as e:
            logger.warning(f"Redis delete failed for key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            result = await self._client.exists(key)
            return result > 0
        except RedisError as e:
            logger.warning(f"Redis exists check failed for key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Set expiration time for a key"""
        try:
            result = await self._client.expire(key, ttl_seconds)
            return result
        except RedisError as e:
            logger.warning(f"Redis expire failed for key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """Get TTL for a key"""
        try:
            return await self._client.ttl(key)
        except RedisError as e:
            logger.warning(f"Redis TTL check failed for key {key}: {e}")
            return -1
        except Exception as e:
            logger.error(f"Cache TTL error for key {key}: {e}")
            return -1

    # Batch operations
    async def mget(self, keys: List[str]) -> List[Optional[Any]]:
        """Get multiple values from cache"""
        try:
            raw_values = await self._client.mget(keys)
            return [self.deserialize(val) if val else None for val in raw_values]
        except RedisError as e:
            logger.warning(f"Redis mget failed: {e}")
            return [None] * len(keys)
        except Exception as e:
            logger.error(f"Cache mget error: {e}")
            return [None] * len(keys)

    async def mset(self, mapping: Dict[str, Any], ttl_seconds: Optional[int] = None) -> bool:
        """Set multiple values in cache"""
        try:
            # Serialize all values
            serialized_mapping = {
                key: self.serialize(value)
                for key, value in mapping.items()
            }

            # Use pipeline for efficiency
            pipe = self._client.pipeline()
            pipe.mset(serialized_mapping)

            if ttl_seconds:
                for key in mapping.keys():
                    pipe.expire(key, ttl_seconds)

            await pipe.execute()
            return True
        except RedisError as e:
            logger.warning(f"Redis mset failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Cache mset error: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern"""
        try:
            keys = await self._client.keys(pattern)
            if keys:
                result = await self._client.delete(*keys)
                return result
            return 0
        except RedisError as e:
            logger.warning(f"Redis delete pattern failed for {pattern}: {e}")
            return 0
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0

    # Hash operations (useful for storing structured data)
    async def hget(self, name: str, key: str) -> Optional[Any]:
        """Get field from hash"""
        try:
            raw_data = await self._client.hget(name, key)
            return self.deserialize(raw_data) if raw_data else None
        except RedisError as e:
            logger.warning(f"Redis hget failed for {name}.{key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Cache hget error for {name}.{key}: {e}")
            return None

    async def hset(self, name: str, key: str, value: Any) -> bool:
        """Set field in hash"""
        try:
            serialized_value = self.serialize(value)
            await self._client.hset(name, key, serialized_value)
            return True
        except RedisError as e:
            logger.warning(f"Redis hset failed for {name}.{key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Cache hset error for {name}.{key}: {e}")
            return False

    async def hgetall(self, name: str) -> Dict[str, Any]:
        """Get all fields from hash"""
        try:
            raw_data = await self._client.hgetall(name)
            return {
                key.decode() if isinstance(key, bytes) else key: self.deserialize(value)
                for key, value in raw_data.items()
            }
        except RedisError as e:
            logger.warning(f"Redis hgetall failed for {name}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Cache hgetall error for {name}: {e}")
            return {}

    # Cache management utilities
    async def flush_db(self) -> bool:
        """Flush all keys from current database"""
        try:
            await self._client.flushdb()
            logger.info("Cache database flushed")
            return True
        except RedisError as e:
            logger.error(f"Redis flush failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Cache flush error: {e}")
            return False

    async def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        try:
            info = await self._client.info("memory")
            return {
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_peak": info.get("used_memory_peak", 0),
                "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                "maxmemory": info.get("maxmemory", 0),
            }
        except Exception as e:
            logger.error(f"Error getting Redis memory usage: {e}")
            return {}


class CacheKeyBuilder:
    """Utility class for building consistent cache keys"""

    @staticmethod
    def mpi_match_key(patient_data: Dict[str, Any]) -> str:
        """Generate cache key for MPI matching"""
        key_fields = {
            'ssn': patient_data.get('ssn', ''),
            'first_name': patient_data.get('first_name', '').lower(),
            'last_name': patient_data.get('last_name', '').lower(),
            'dob': patient_data.get('dob', '')
        }
        key_string = orjson.dumps(key_fields, option=orjson.OPT_SORT_KEYS)
        hash_key = hashlib.blake2b(key_string, digest_size=16).hexdigest()
        return f"mpi:match:{hash_key}"

    @staticmethod
    def patient_key(mpi_id: str) -> str:
        """Generate cache key for patient data"""
        return f"patient:{mpi_id}"

    @staticmethod
    def session_key(session_id: str) -> str:
        """Generate cache key for user sessions"""
        return f"session:{session_id}"

    @staticmethod
    def rate_limit_key(user_id: str, endpoint: str) -> str:
        """Generate cache key for rate limiting"""
        return f"rate_limit:{user_id}:{endpoint}"

    @staticmethod
    def metrics_key(endpoint: str, timeframe: str) -> str:
        """Generate cache key for metrics"""
        return f"metrics:{endpoint}:{timeframe}"

    @staticmethod
    def config_key(config_name: str) -> str:
        """Generate cache key for configuration"""
        return f"config:{config_name}"


class CacheDecorator:
    """Decorator for caching function results"""

    def __init__(self, cache_manager: CacheManager, ttl_seconds: int = 3600):
        self.cache_manager = cache_manager
        self.ttl_seconds = ttl_seconds

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            key_data = {
                'func': func.__name__,
                'args': str(args),
                'kwargs': str(sorted(kwargs.items()))
            }
            key_string = orjson.dumps(key_data)
            cache_key = f"func:{hashlib.blake2b(key_string, digest_size=16).hexdigest()}"

            # Try to get from cache
            cached_result = await self.cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = await func(*args, **kwargs)
            await self.cache_manager.set(cache_key, result, self.ttl_seconds)
            return result

        return wrapper


# Singleton cache manager instance
_cache_manager: Optional[CacheManager] = None


@lru_cache(maxsize=1)
def get_cache_manager() -> CacheManager:
    """
    Get the singleton cache manager instance.
    Uses LRU cache to ensure the same instance is returned.
    """
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


async def initialize_cache() -> CacheManager:
    """Initialize the cache manager"""
    cache_manager = get_cache_manager()
    await cache_manager.initialize()
    return cache_manager


async def cleanup_cache() -> None:
    """Cleanup cache connections"""
    global _cache_manager
    if _cache_manager and _cache_manager._initialized:
        await _cache_manager.cleanup()
        _cache_manager = None
        get_cache_manager.cache_clear()


# High-level caching utilities
class MatchingCache:
    """High-level caching utilities for matching operations"""

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or get_cache_manager()
        self.ttl_seconds = get_redis_config().match_cache_ttl_seconds

    async def get_match_result(self, patient_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached match result"""
        cache_key = CacheKeyBuilder.mpi_match_key(patient_data)
        return await self.cache_manager.get(cache_key)

    async def cache_match_result(
        self,
        patient_data: Dict[str, Any],
        result: Dict[str, Any]
    ) -> bool:
        """Cache match result"""
        cache_key = CacheKeyBuilder.mpi_match_key(patient_data)
        return await self.cache_manager.set(cache_key, result, self.ttl_seconds)

    async def invalidate_patient_cache(self, mpi_id: str) -> int:
        """Invalidate all cached data for a patient"""
        pattern = f"*{mpi_id}*"
        return await self.cache_manager.delete_pattern(pattern)


class MetricsCache:
    """High-level caching utilities for metrics"""

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or get_cache_manager()

    async def record_metric(
        self,
        endpoint: str,
        response_time_ms: float,
        cache_hit: bool,
        status: str = "success"
    ) -> bool:
        """Record a metric event"""
        timestamp = datetime.utcnow()
        metric_data = {
            "endpoint": endpoint,
            "response_time_ms": response_time_ms,
            "cache_hit": cache_hit,
            "status": status,
            "timestamp": timestamp.isoformat()
        }

        # Store metric with timestamp-based key
        key = f"metric:{endpoint}:{timestamp.timestamp()}"
        return await self.cache_manager.set(key, metric_data, ttl_seconds=3600)

    async def get_endpoint_metrics(
        self,
        endpoint: str,
        hours: int = 1
    ) -> List[Dict[str, Any]]:
        """Get metrics for an endpoint within the time window"""
        start_time = datetime.utcnow() - timedelta(hours=hours)
        pattern = f"metric:{endpoint}:*"

        # This is a simplified implementation
        # In production, you might want to use Redis Streams or TimeSeries
        keys = await self.cache_manager.client.keys(pattern)
        metrics = await self.cache_manager.mget([key.decode() for key in keys])

        # Filter by time window
        filtered_metrics = []
        for metric in metrics:
            if metric and "timestamp" in metric:
                metric_time = datetime.fromisoformat(metric["timestamp"])
                if metric_time >= start_time:
                    filtered_metrics.append(metric)

        return filtered_metrics


# Convenience functions
async def cache_patient_data(mpi_id: str, patient_data: Dict[str, Any], ttl_seconds: int = 3600) -> bool:
    """Cache patient data"""
    cache_manager = get_cache_manager()
    key = CacheKeyBuilder.patient_key(mpi_id)
    return await cache_manager.set(key, patient_data, ttl_seconds)


async def get_cached_patient_data(mpi_id: str) -> Optional[Dict[str, Any]]:
    """Get cached patient data"""
    cache_manager = get_cache_manager()
    key = CacheKeyBuilder.patient_key(mpi_id)
    return await cache_manager.get(key)


async def invalidate_patient_cache(mpi_id: str) -> bool:
    """Invalidate cached patient data"""
    cache_manager = get_cache_manager()
    key = CacheKeyBuilder.patient_key(mpi_id)
    return await cache_manager.delete(key)
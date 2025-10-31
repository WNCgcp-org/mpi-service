"""
Matching repository - handles caching and persistence for matching operations
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib
import json
import logging
import orjson

from core.database import BaseRepository, DatabaseManager
from core.cache import CacheManager, MatchingCache, MetricsCache, CacheKeyBuilder


logger = logging.getLogger(__name__)


class MatchingRepository(BaseRepository):
    """Repository for matching operations and caching"""

    def __init__(self, db_manager: DatabaseManager, cache_manager: Optional[CacheManager] = None):
        super().__init__(db_manager, "cache")
        self.cache_manager = cache_manager
        self.metrics_collection = db_manager.get_collection("metrics")

        # Initialize high-level cache utilities
        self.matching_cache = MatchingCache(cache_manager) if cache_manager else None
        self.metrics_cache = MetricsCache(cache_manager) if cache_manager else None

    def generate_cache_key(self, patient_data: Dict[str, Any]) -> str:
        """Generate cache key from patient data"""
        return CacheKeyBuilder.mpi_match_key(patient_data)

    async def get_cached_match(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached match result from Redis or MongoDB"""
        if not self.cache_manager:
            return None

        # Try Redis first (L2 cache)
        result = await self.cache_manager.get(cache_key)
        if result:
            return result

        # Try MongoDB cache (L3 cache)
        try:
            mongo_result = await self.find_one(
                {"request_hash": cache_key},
                projection={"_id": 0, "expires_at": 0}
            )
            if mongo_result:
                # Populate Redis cache
                await self.cache_manager.set(cache_key, mongo_result, ttl_seconds=3600)
                return mongo_result
        except Exception as e:
            logger.warning(f"MongoDB cache get failed: {e}")

        return None

    async def set_cache(
        self,
        cache_key: str,
        result: Dict[str, Any],
        ttl_seconds: int = 3600
    ):
        """Set cache in both Redis and MongoDB"""
        if not self.cache_manager:
            return

        # Redis cache
        await self.cache_manager.set(cache_key, result, ttl_seconds)

        # MongoDB cache with TTL
        try:
            await self.update_one(
                {"request_hash": cache_key},
                {
                    "$set": {
                        **result,
                        "request_hash": cache_key,
                        "created_at": datetime.utcnow(),
                        "expires_at": datetime.utcnow() + timedelta(seconds=ttl_seconds)
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.warning(f"MongoDB cache set failed: {e}")

    async def record_metric(
        self,
        endpoint: str,
        response_time_ms: float,
        cache_hit: bool,
        status: str = "success"
    ):
        """Record performance metric"""
        try:
            # Use the MetricsCache utility if available
            if self.metrics_cache:
                await self.metrics_cache.record_metric(endpoint, response_time_ms, cache_hit, status)

            # Also store in MongoDB for persistence
            await self.metrics_collection.insert_one({
                "endpoint": endpoint,
                "response_time_ms": response_time_ms,
                "cache_hit": cache_hit,
                "status": status,
                "timestamp": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(days=30)
            })
        except Exception as e:
            logger.error(f"Failed to record metric: {e}")

    async def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get metrics summary for the specified time period"""
        start_time = datetime.utcnow() - timedelta(hours=hours)

        pipeline = [
            {"$match": {"timestamp": {"$gte": start_time}}},
            {"$group": {
                "_id": "$endpoint",
                "count": {"$sum": 1},
                "avg_response_time": {"$avg": "$response_time_ms"},
                "cache_hits": {"$sum": {"$cond": ["$cache_hit", 1, 0]}},
                "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}}
            }}
        ]

        results = await self.metrics_collection.aggregate(pipeline).to_list(None)

        summary = {}
        for result in results:
            summary[result["_id"]] = {
                "requests": result["count"],
                "avg_response_time_ms": result["avg_response_time"],
                "cache_hit_rate": result["cache_hits"] / result["count"] if result["count"] > 0 else 0,
                "success_rate": result["success_count"] / result["count"] if result["count"] > 0 else 0
            }

        return summary

    # High-level convenience methods using the new abstractions
    async def get_match_from_cache(self, patient_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached match result using high-level API"""
        if self.matching_cache:
            return await self.matching_cache.get_match_result(patient_data)
        return None

    async def cache_match_result(self, patient_data: Dict[str, Any], result: Dict[str, Any]) -> bool:
        """Cache match result using high-level API"""
        if self.matching_cache:
            return await self.matching_cache.cache_match_result(patient_data, result)
        return False

    async def invalidate_patient_cache(self, mpi_id: str) -> int:
        """Invalidate all cached data for a patient"""
        if self.matching_cache:
            return await self.matching_cache.invalidate_patient_cache(mpi_id)
        return 0
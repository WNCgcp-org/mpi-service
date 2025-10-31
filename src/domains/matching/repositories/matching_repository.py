"""
Matching repository - handles caching and persistence for matching operations
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib
import json
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
import redis.asyncio as redis
import orjson


logger = logging.getLogger(__name__)


class MatchingRepository:
    """Repository for matching operations and caching"""

    def __init__(self, db: AsyncIOMotorDatabase, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client
        self.cache_collection = db["cache"]
        self.metrics_collection = db["metrics"]

    async def initialize(self):
        """Create indexes for caching"""
        # Cache indexes with TTL
        await self.cache_collection.create_index([("expires_at", 1)], expireAfterSeconds=0)
        await self.cache_collection.create_index([("request_hash", 1)], unique=True)

        # Metrics indexes with TTL (30 day retention)
        await self.metrics_collection.create_index([("expires_at", 1)], expireAfterSeconds=0)
        await self.metrics_collection.create_index([("timestamp", -1)])

    def generate_cache_key(self, patient_data: Dict[str, Any]) -> str:
        """Generate cache key from patient data"""
        # Use only key fields for cache key
        key_fields = {
            'ssn': patient_data.get('ssn', ''),
            'first_name': patient_data.get('first_name', '').lower(),
            'last_name': patient_data.get('last_name', '').lower(),
            'dob': patient_data.get('dob', '')
        }

        key_string = orjson.dumps(key_fields, option=orjson.OPT_SORT_KEYS)
        return f"mpi:{hashlib.blake2b(key_string, digest_size=16).hexdigest()}"

    async def get_cached_match(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached match result from Redis or MongoDB"""
        # Try Redis first (L2 cache)
        try:
            redis_result = await self.redis.get(cache_key)
            if redis_result:
                return orjson.loads(redis_result)
        except Exception as e:
            logger.warning(f"Redis cache get failed: {e}")

        # Try MongoDB cache (L3 cache)
        try:
            mongo_result = await self.cache_collection.find_one(
                {"request_hash": cache_key},
                {"_id": 0, "expires_at": 0}
            )
            if mongo_result:
                # Populate Redis cache
                await self.set_cache(cache_key, mongo_result, ttl_seconds=3600)
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
        serialized = orjson.dumps(result)

        # Redis cache
        try:
            await self.redis.setex(cache_key, ttl_seconds, serialized)
        except Exception as e:
            logger.warning(f"Redis cache set failed: {e}")

        # MongoDB cache with TTL
        try:
            await self.cache_collection.update_one(
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
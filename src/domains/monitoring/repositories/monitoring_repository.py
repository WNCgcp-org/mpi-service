"""
Monitoring repository - handles system monitoring and health checks
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging

from core.database import BaseRepository, DatabaseManager
from core.cache import CacheManager

logger = logging.getLogger(__name__)


class MonitoringRepository(BaseRepository):
    """Repository for monitoring operations"""

    def __init__(self, db_manager: DatabaseManager, cache_manager: Optional[CacheManager] = None):
        super().__init__(db_manager, "monitoring")
        self.cache_manager = cache_manager

    async def log_system_event(
        self,
        event_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        severity: str = "info"
    ) -> str:
        """Log a system event"""
        event_doc = {
            "event_type": event_type,
            "message": message,
            "details": details or {},
            "severity": severity,
            "timestamp": datetime.utcnow()
        }
        return await self.insert_one(event_doc)

    async def get_system_events(
        self,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get system events within time window"""
        start_time = datetime.utcnow() - timedelta(hours=hours)

        query = {"timestamp": {"$gte": start_time}}
        if event_type:
            query["event_type"] = event_type
        if severity:
            query["severity"] = severity

        return await self.find_many(
            query,
            sort=[("timestamp", -1)],
            limit=limit
        )

    async def get_health_status(self) -> Dict[str, Any]:
        """Get system health status"""
        # Database health
        db_health = await self.db_manager.health_check()

        # Cache health
        cache_health = {}
        if self.cache_manager:
            cache_health = await self.cache_manager.health_check()

        # Recent error counts
        recent_errors = await self.count_documents({
            "severity": {"$in": ["error", "critical"]},
            "timestamp": {"$gte": datetime.utcnow() - timedelta(hours=1)}
        })

        return {
            "timestamp": datetime.utcnow(),
            "database": db_health,
            "cache": cache_health,
            "recent_errors": recent_errors,
            "status": "healthy" if recent_errors < 10 and db_health.get("status") == "healthy" else "unhealthy"
        }
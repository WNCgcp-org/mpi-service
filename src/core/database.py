"""
Database utility abstractions for MongoDB operations
"""

import logging
from typing import Optional, Dict, Any, List, AsyncGenerator
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
import pymongo

from .config import get_database_config, DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Centralized database connection and operation manager.
    Provides a single point for database connections and common operations.
    """

    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or get_database_config()
        self._client: Optional[AsyncIOMotorClient] = None
        self._database: Optional[AsyncIOMotorDatabase] = None
        self._collections: Dict[str, AsyncIOMotorCollection] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database connection and collections"""
        if self._initialized:
            return

        logger.info(f"Initializing database connection to {self.config.uri}")

        try:
            self._client = AsyncIOMotorClient(
                self.config.uri,
                maxPoolSize=self.config.max_pool_size,
                minPoolSize=self.config.min_pool_size,
                maxIdleTimeMS=self.config.max_idle_time_ms,
                serverSelectionTimeoutMS=self.config.server_selection_timeout_ms
            )

            # Test connection
            await self._client.admin.command('ping')
            logger.info("Database connection established successfully")

            self._database = self._client[self.config.name]

            # Initialize collections
            await self._setup_collections()

            self._initialized = True
            logger.info("Database manager initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def _setup_collections(self) -> None:
        """Setup database collections with proper indexes"""
        logger.info("Setting up database collections and indexes...")

        # Get all collection references
        self._collections = {
            "mpi_identifiers": self._database[self.config.mpi_identifiers_collection],
            "identifier_mappings": self._database[self.config.identifier_mappings_collection],
            "patient_audit": self._database[self.config.patient_audit_collection],
            "patient_links": self._database[self.config.patient_links_collection],
            "cache": self._database[self.config.cache_collection],
            "metrics": self._database[self.config.metrics_collection],
        }

        # Create indexes for each collection
        await self._create_indexes()

    async def _create_indexes(self) -> None:
        """Create all necessary database indexes"""
        try:
            # MPI Identifiers collection indexes
            mpi_coll = self._collections["mpi_identifiers"]
            await mpi_coll.create_index([("mpi_id", 1)], unique=True)
            await mpi_coll.create_index([("ssn_hash", 1)])
            await mpi_coll.create_index([("last_accessed", 1)])

            # Compound indexes for matching
            await mpi_coll.create_index([
                ("match_keys.ssn_last4", 1),
                ("match_keys.dob", 1)
            ])
            await mpi_coll.create_index([
                ("match_keys.last_name_soundex", 1),
                ("match_keys.first_name_soundex", 1),
                ("match_keys.dob", 1)
            ])

            # Identifier mappings collection indexes
            mappings_coll = self._collections["identifier_mappings"]
            await mappings_coll.create_index([
                ("external_id", 1),
                ("external_system", 1)
            ], unique=True)
            await mappings_coll.create_index([("mpi_id", 1)])

            # Patient audit collection indexes
            audit_coll = self._collections["patient_audit"]
            await audit_coll.create_index([("mpi_id", 1)])
            await audit_coll.create_index([("timestamp", -1)])

            # Patient links collection indexes
            links_coll = self._collections["patient_links"]
            await links_coll.create_index([("survivor_id", 1)])
            await links_coll.create_index([("retired_id", 1)])
            await links_coll.create_index([("mpi_id_1", 1)])
            await links_coll.create_index([("mpi_id_2", 1)])
            await links_coll.create_index([("type", 1)])

            # Cache collection indexes with TTL
            cache_coll = self._collections["cache"]
            await cache_coll.create_index([("expires_at", 1)], expireAfterSeconds=0)
            await cache_coll.create_index([("request_hash", 1)], unique=True)

            # Metrics collection indexes with TTL
            metrics_coll = self._collections["metrics"]
            await metrics_coll.create_index([("expires_at", 1)], expireAfterSeconds=0)
            await metrics_coll.create_index([("timestamp", -1)])
            await metrics_coll.create_index([("endpoint", 1)])

            logger.info("Database indexes created successfully")

        except Exception as e:
            logger.error(f"Failed to create database indexes: {e}")
            raise

    async def cleanup(self) -> None:
        """Cleanup database connections"""
        if self._client:
            self._client.close()
            self._initialized = False
            logger.info("Database connections closed")

    @property
    def database(self) -> AsyncIOMotorDatabase:
        """Get the database instance"""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized. Call initialize() first.")
        return self._database

    @property
    def client(self) -> AsyncIOMotorClient:
        """Get the MongoDB client instance"""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized. Call initialize() first.")
        return self._client

    def get_collection(self, name: str) -> AsyncIOMotorCollection:
        """Get a collection by name"""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized. Call initialize() first.")

        if name in self._collections:
            return self._collections[name]

        # Return collection directly from database for dynamic collections
        return self._database[name]

    async def health_check(self) -> Dict[str, Any]:
        """Perform database health check"""
        try:
            if not self._initialized:
                return {"status": "error", "message": "Database not initialized"}

            # Test basic connectivity
            await self._client.admin.command('ping')

            # Get database stats
            stats = await self._database.command("dbStats")

            return {
                "status": "healthy",
                "database": self.config.name,
                "collections": stats.get("collections", 0),
                "objects": stats.get("objects", 0),
                "dataSize": stats.get("dataSize", 0),
                "indexSize": stats.get("indexSize", 0),
            }

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    @asynccontextmanager
    async def session(self) -> AsyncGenerator:
        """Get a database session for transactions"""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized. Call initialize() first.")

        async with await self._client.start_session() as session:
            yield session


class BaseRepository:
    """
    Base repository class providing common database operations.
    All repository classes should inherit from this.
    """

    def __init__(self, db_manager: DatabaseManager, collection_name: str):
        self.db_manager = db_manager
        self.collection_name = collection_name

    @property
    def collection(self) -> AsyncIOMotorCollection:
        """Get the collection for this repository"""
        return self.db_manager.get_collection(self.collection_name)

    @property
    def database(self) -> AsyncIOMotorDatabase:
        """Get the database instance"""
        return self.db_manager.database

    async def find_one(
        self,
        filter_dict: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Find a single document"""
        try:
            return await self.collection.find_one(filter_dict, projection)
        except Exception as e:
            logger.error(f"Error in find_one for {self.collection_name}: {e}")
            raise

    async def find_many(
        self,
        filter_dict: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Find multiple documents"""
        try:
            cursor = self.collection.find(filter_dict, projection)

            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)

            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error in find_many for {self.collection_name}: {e}")
            raise

    async def insert_one(self, document: Dict[str, Any]) -> str:
        """Insert a single document"""
        try:
            document.setdefault("created_at", datetime.utcnow())
            document.setdefault("updated_at", datetime.utcnow())

            result = await self.collection.insert_one(document)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error in insert_one for {self.collection_name}: {e}")
            raise

    async def insert_many(self, documents: List[Dict[str, Any]]) -> List[str]:
        """Insert multiple documents"""
        try:
            now = datetime.utcnow()
            for doc in documents:
                doc.setdefault("created_at", now)
                doc.setdefault("updated_at", now)

            result = await self.collection.insert_many(documents)
            return [str(oid) for oid in result.inserted_ids]
        except Exception as e:
            logger.error(f"Error in insert_many for {self.collection_name}: {e}")
            raise

    async def update_one(
        self,
        filter_dict: Dict[str, Any],
        update_dict: Dict[str, Any],
        upsert: bool = False
    ) -> bool:
        """Update a single document"""
        try:
            # Ensure updated_at is set
            if "$set" in update_dict:
                update_dict["$set"]["updated_at"] = datetime.utcnow()
            else:
                update_dict["$set"] = {"updated_at": datetime.utcnow()}

            result = await self.collection.update_one(filter_dict, update_dict, upsert=upsert)
            return result.modified_count > 0 or (upsert and result.upserted_id is not None)
        except Exception as e:
            logger.error(f"Error in update_one for {self.collection_name}: {e}")
            raise

    async def update_many(
        self,
        filter_dict: Dict[str, Any],
        update_dict: Dict[str, Any]
    ) -> int:
        """Update multiple documents"""
        try:
            # Ensure updated_at is set
            if "$set" in update_dict:
                update_dict["$set"]["updated_at"] = datetime.utcnow()
            else:
                update_dict["$set"] = {"updated_at": datetime.utcnow()}

            result = await self.collection.update_many(filter_dict, update_dict)
            return result.modified_count
        except Exception as e:
            logger.error(f"Error in update_many for {self.collection_name}: {e}")
            raise

    async def delete_one(self, filter_dict: Dict[str, Any]) -> bool:
        """Delete a single document"""
        try:
            result = await self.collection.delete_one(filter_dict)
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error in delete_one for {self.collection_name}: {e}")
            raise

    async def delete_many(self, filter_dict: Dict[str, Any]) -> int:
        """Delete multiple documents"""
        try:
            result = await self.collection.delete_many(filter_dict)
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error in delete_many for {self.collection_name}: {e}")
            raise

    async def count_documents(self, filter_dict: Dict[str, Any] = None) -> int:
        """Count documents matching the filter"""
        try:
            return await self.collection.count_documents(filter_dict or {})
        except Exception as e:
            logger.error(f"Error in count_documents for {self.collection_name}: {e}")
            raise

    async def create_index(
        self,
        keys: List[tuple],
        unique: bool = False,
        sparse: bool = False,
        expire_after_seconds: Optional[int] = None
    ) -> str:
        """Create an index on the collection"""
        try:
            index_options = {}
            if unique:
                index_options["unique"] = True
            if sparse:
                index_options["sparse"] = True
            if expire_after_seconds is not None:
                index_options["expireAfterSeconds"] = expire_after_seconds

            return await self.collection.create_index(keys, **index_options)
        except Exception as e:
            logger.error(f"Error creating index for {self.collection_name}: {e}")
            raise

    async def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Perform aggregation query"""
        try:
            cursor = self.collection.aggregate(pipeline)
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error(f"Error in aggregate for {self.collection_name}: {e}")
            raise


# Singleton database manager instance
_db_manager: Optional[DatabaseManager] = None


@lru_cache(maxsize=1)
def get_database_manager() -> DatabaseManager:
    """
    Get the singleton database manager instance.
    Uses LRU cache to ensure the same instance is returned.
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


async def initialize_database() -> DatabaseManager:
    """Initialize the database manager"""
    db_manager = get_database_manager()
    await db_manager.initialize()
    return db_manager


async def cleanup_database() -> None:
    """Cleanup database connections"""
    global _db_manager
    if _db_manager and _db_manager._initialized:
        await _db_manager.cleanup()
        _db_manager = None
        get_database_manager.cache_clear()


# Utility functions for common operations
async def ensure_indexes_exist(collections: List[str]) -> None:
    """Ensure that required indexes exist for the given collections"""
    db_manager = get_database_manager()
    if not db_manager._initialized:
        await db_manager.initialize()

    # Indexes are created during initialization, so this is a no-op
    # but kept for potential future custom index requirements
    logger.info(f"Verified indexes exist for collections: {', '.join(collections)}")


async def drop_collection(collection_name: str) -> bool:
    """Drop a collection (use with caution!)"""
    try:
        db_manager = get_database_manager()
        await db_manager.database.drop_collection(collection_name)
        logger.warning(f"Dropped collection: {collection_name}")
        return True
    except Exception as e:
        logger.error(f"Error dropping collection {collection_name}: {e}")
        return False


async def get_database_stats() -> Dict[str, Any]:
    """Get comprehensive database statistics"""
    try:
        db_manager = get_database_manager()

        # Get database stats
        db_stats = await db_manager.database.command("dbStats")

        # Get collection stats
        collection_stats = {}
        for collection_name in db_manager._collections.keys():
            try:
                stats = await db_manager.database.command("collStats", collection_name)
                collection_stats[collection_name] = {
                    "count": stats.get("count", 0),
                    "size": stats.get("size", 0),
                    "totalIndexSize": stats.get("totalIndexSize", 0),
                    "nindexes": stats.get("nindexes", 0)
                }
            except Exception:
                # Collection might not exist yet
                collection_stats[collection_name] = {
                    "count": 0,
                    "size": 0,
                    "totalIndexSize": 0,
                    "nindexes": 0
                }

        return {
            "database": {
                "name": db_stats.get("db"),
                "collections": db_stats.get("collections", 0),
                "objects": db_stats.get("objects", 0),
                "dataSize": db_stats.get("dataSize", 0),
                "indexSize": db_stats.get("indexSize", 0),
            },
            "collections": collection_stats
        }

    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {"error": str(e)}
"""
High-Performance MPI Service with optimizations
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager
import time
import json

# Performance optimizations
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("✓ Using uvloop for enhanced performance")
except ImportError:
    print("⚠ uvloop not installed, using standard asyncio")

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorClient
import orjson  # Faster JSON serialization
import numpy as np
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import aiohttp
from aiocache import Cache
from aiocache.serializers import JsonSerializer
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
request_count = Counter('mpi_requests_total', 'Total MPI requests', ['method', 'status'])
request_duration = Histogram('mpi_request_duration_seconds', 'MPI request duration', ['method'])
cache_hits = Counter('mpi_cache_hits_total', 'Cache hits')
cache_misses = Counter('mpi_cache_misses_total', 'Cache misses')
active_connections = Gauge('mpi_active_connections', 'Active connections')

# Performance configuration
PERFORMANCE_CONFIG = {
    "connection_pool_size": int(os.getenv("CONNECTION_POOL_SIZE", "100")),
    "redis_pool_size": int(os.getenv("REDIS_POOL_SIZE", "50")),
    "mongo_pool_size": int(os.getenv("MONGO_POOL_SIZE", "50")),
    "batch_size": int(os.getenv("BATCH_SIZE", "100")),
    "cache_ttl": int(os.getenv("CACHE_TTL", "3600")),
    "request_timeout": int(os.getenv("REQUEST_TIMEOUT", "30")),
    "enable_profiling": os.getenv("ENABLE_PROFILING", "false").lower() == "true"
}


# Note: This is the legacy main.py
# The refactored version is in main_refactored.py
# This file is kept for reference during migration

class OptimizedMPIService:
    """
    High-performance MPI Service with optimizations
    """

    def __init__(self):
        self.redis_pool = None
        self.redis = None
        self.mongo_client = None
        self.db = None
        self.collection = None
        self.cache = {}
        self.local_cache = Cache(Cache.MEMORY, serializer=JsonSerializer())
        self.http_session = None
        self.session = None
        self._initialized = False
        self.provider_name = os.getenv("MPI_PROVIDER", "verato")
        self.provider = None
        self.start_time = datetime.utcnow()
        # Cache metrics
        self.memory_cache_hits = 0
        self.memory_cache_misses = 0
        self.redis_cache_hits = 0
        self.redis_cache_misses = 0
        self.mongo_cache_hits = 0
        self.mongo_cache_misses = 0

    async def initialize(self):
        """Initialize all connections with optimized settings"""
        if self._initialized:
            return

        # Initialize Redis with connection pooling
        self.redis_pool = redis.ConnectionPool(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            max_connections=PERFORMANCE_CONFIG["redis_pool_size"],
            decode_responses=False  # Use raw bytes for speed
        )
        self.redis_client = redis.Redis(connection_pool=self.redis_pool)
        self.redis = self.redis_client  # Alias for compatibility

        # Initialize MongoDB with connection pooling
        mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.mongo_client = AsyncIOMotorClient(
            mongo_uri,
            maxPoolSize=PERFORMANCE_CONFIG["mongo_pool_size"],
            minPoolSize=10,
            maxIdleTimeMS=10000,
            serverSelectionTimeoutMS=5000
        )
        self.db = self.mongo_client[os.getenv("MPI_DB", "mpi_service")]
        self.collection = self.db["mpi_records"]

        # Create indexes for performance
        await self._create_indexes()

        # Initialize HTTP session for external calls
        connector = aiohttp.TCPConnector(
            limit=PERFORMANCE_CONFIG["connection_pool_size"],
            limit_per_host=30,
            ttl_dns_cache=300
        )
        timeout = aiohttp.ClientTimeout(total=PERFORMANCE_CONFIG["request_timeout"])
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            json_serialize=lambda x: orjson.dumps(x).decode()  # Fast JSON
        )
        self.session = self.http_session  # Alias for compatibility

        # Initialize provider
        await self._init_provider()

        self._initialized = True
        logger.info("MPI Service initialized with performance optimizations")

    async def _init_provider(self):
        """Initialize the configured provider"""
        if self.provider_name == "verato":
            from providers import VeratoProvider
            self.provider = VeratoProvider(
                api_key=os.getenv("VERATO_API_KEY"),
                endpoint=os.getenv("VERATO_ENDPOINT")
            )
            await self.provider.initialize()
        elif self.provider_name == "internal":
            from providers import InternalMPIProvider
            self.provider = InternalMPIProvider(mpi_service=self)
            await self.provider.initialize()
        else:
            # Default to internal
            self.provider_name = "internal"
            from providers import InternalMPIProvider
            self.provider = InternalMPIProvider(mpi_service=self)
            await self.provider.initialize()

    async def clear_all_caches(self):
        """Clear all cache levels"""
        self.cache.clear()
        await self.local_cache.clear()
        try:
            await self.redis.flushdb()
        except:
            pass

    async def _create_indexes(self):
        """Create MongoDB indexes for optimal query performance"""
        await self.collection.create_index([("ssn_hash", 1)])
        await self.collection.create_index([("mpi_id", 1)])
        await self.collection.create_index([("created_at", -1)])
        await self.collection.create_index(
            [("last_name", 1), ("first_name", 1), ("dob", 1)]
        )

    async def cleanup(self):
        """Cleanup all connections"""
        if self.http_session:
            await self.http_session.close()
        if self.redis_pool:
            await self.redis_pool.disconnect()
        if self.mongo_client:
            self.mongo_client.close()

    async def get_mpi_id(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get MPI ID with multi-level caching and optimizations
        """
        start_time = time.perf_counter()

        try:
            # Level 1: Local memory cache (fastest)
            cache_key = self._generate_cache_key(patient_data)
            cached = await self.local_cache.get(cache_key)
            if cached:
                cache_hits.inc()
                return orjson.loads(cached)

            # Level 2: Redis cache (fast)
            redis_cached = await self._get_redis_cache(cache_key)
            if redis_cached:
                cache_hits.inc()
                # Populate local cache
                await self.local_cache.set(cache_key, redis_cached, ttl=60)
                return orjson.loads(redis_cached)

            cache_misses.inc()

            # Level 3: MongoDB lookup (medium)
            mongo_result = await self._mongodb_lookup(patient_data)
            if mongo_result:
                await self._set_multi_cache(cache_key, mongo_result)
                return mongo_result

            # Level 4: Call provider (slowest)
            result = await self._call_provider(patient_data)

            # Store in all cache levels
            await self._store_result(patient_data, result)
            await self._set_multi_cache(cache_key, result)

            return result

        finally:
            duration = time.perf_counter() - start_time
            request_duration.labels(method='get_mpi_id').observe(duration)

    def _generate_cache_key(self, patient_data: Dict) -> str:
        """Generate cache key using fast hashing"""
        import hashlib

        # Use only key fields for cache key
        key_fields = {
            'ssn': patient_data.get('ssn', ''),
            'first_name': patient_data.get('first_name', '').lower(),
            'last_name': patient_data.get('last_name', '').lower(),
            'dob': patient_data.get('dob', '')
        }

        key_string = orjson.dumps(key_fields, option=orjson.OPT_SORT_KEYS)
        return f"mpi:{hashlib.blake2b(key_string, digest_size=16).hexdigest()}"

    async def _get_redis_cache(self, cache_key: str) -> Optional[bytes]:
        """Get from Redis with error handling"""
        try:
            return await self.redis_client.get(cache_key)
        except Exception as e:
            logger.warning(f"Redis cache get failed: {e}")
            return None

    async def _set_multi_cache(self, cache_key: str, data: Dict):
        """Set in multiple cache levels"""
        serialized = orjson.dumps(data)

        # Local cache (1 minute)
        await self.local_cache.set(cache_key, serialized, ttl=60)

        # Redis cache (1 hour)
        try:
            await self.redis_client.setex(
                cache_key,
                PERFORMANCE_CONFIG["cache_ttl"],
                serialized
            )
        except Exception as e:
            logger.warning(f"Redis cache set failed: {e}")

    async def _mongodb_lookup(self, patient_data: Dict) -> Optional[Dict]:
        """Optimized MongoDB lookup"""
        # Try exact SSN match first (indexed)
        ssn = patient_data.get('ssn', '').replace('-', '')
        if ssn:
            result = await self.collection.find_one(
                {'ssn_hash': self._hash_ssn(ssn)},
                {'_id': 0}
            )
            if result:
                return result

        # Try name + DOB match (indexed)
        if all(patient_data.get(f) for f in ['first_name', 'last_name', 'dob']):
            result = await self.collection.find_one(
                {
                    'first_name': patient_data['first_name'].upper(),
                    'last_name': patient_data['last_name'].upper(),
                    'dob': patient_data['dob']
                },
                {'_id': 0}
            )
            if result:
                return result

        return None

    def _hash_ssn(self, ssn: str) -> str:
        """Fast SSN hashing"""
        import hashlib
        clean_ssn = ''.join(filter(str.isdigit, ssn))
        return hashlib.blake2b(clean_ssn.encode(), digest_size=16).hexdigest()

    async def _call_provider(self, patient_data: Dict) -> Dict:
        """Call the configured provider (Verato or Internal)"""
        provider = os.getenv("MPI_PROVIDER", "verato")

        if provider == "verato":
            from providers.verato import VeratoModule
            verato = VeratoModule()
            return await verato.get_mpi_id(patient_data)
        else:
            # Internal provider (probabilistic for now)
            return await self._internal_match(patient_data)

    async def _internal_match(self, patient_data: Dict) -> Dict:
        """Fast internal matching using NumPy"""
        # This is a placeholder for probabilistic matching
        # Will be replaced with ML model later
        import uuid

        return {
            'mpi_id': f"MPI-{uuid.uuid4().hex[:8].upper()}",
            'confidence': 0.95,
            'provider': 'internal',
            'source': 'probabilistic'
        }

    async def _store_result(self, patient_data: Dict, result: Dict):
        """Store result in MongoDB"""
        if not result.get('mpi_id'):
            return

        document = {
            'mpi_id': result['mpi_id'],
            'ssn_hash': self._hash_ssn(patient_data.get('ssn', '')),
            'first_name': patient_data.get('first_name', '').upper(),
            'last_name': patient_data.get('last_name', '').upper(),
            'dob': patient_data.get('dob', ''),
            'confidence': result.get('confidence', 0),
            'provider': result.get('provider', 'unknown'),
            'created_at': time.time()
        }

        try:
            await self.collection.insert_one(document)
        except Exception as e:
            logger.error(f"MongoDB insert failed: {e}")

    async def batch_process(self, patient_records: List[Dict]) -> List[Dict]:
        """Process multiple records with batching and concurrency"""
        # Process in optimized batches
        batch_size = PERFORMANCE_CONFIG["batch_size"]
        results = []

        for i in range(0, len(patient_records), batch_size):
            batch = patient_records[i:i + batch_size]

            # Process batch concurrently
            batch_tasks = [self.get_mpi_id(record) for record in batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Handle any exceptions
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Batch processing error: {result}")
                    batch_results[j] = {'error': str(result), 'mpi_id': None}

            results.extend(batch_results)

        return results


# FastAPI application with optimizations
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle"""
    # Startup
    app.state.mpi_service = OptimizedMPIService()
    await app.state.mpi_service.initialize()
    yield
    # Shutdown
    await app.state.mpi_service.cleanup()


app = FastAPI(
    title="MPI Service",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
# Legacy routers removed - see main_refactored.py for new structure

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PatientRequest(BaseModel):
    patient_data: Dict[str, Any] = Field(..., description="Patient demographic data")


class BatchRequest(BaseModel):
    patients: List[Dict[str, Any]] = Field(..., description="List of patient records")


class MPIResponse(BaseModel):
    mpi_id: Optional[str] = None
    confidence: Optional[float] = None
    provider: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None


@app.post("/mpi/match", response_model=MPIResponse)
async def get_mpi_id(request: PatientRequest, req: Request):
    """Get MPI ID for a single patient"""
    start_time = time.perf_counter()

    try:
        result = await req.app.state.mpi_service.get_mpi_id(request.patient_data)
        processing_time = (time.perf_counter() - start_time) * 1000

        request_count.labels(method='match', status='success').inc()

        return MPIResponse(
            mpi_id=result.get('mpi_id'),
            confidence=result.get('confidence'),
            provider=result.get('provider'),
            processing_time_ms=processing_time
        )
    except Exception as e:
        request_count.labels(method='match', status='error').inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mpi/batch", response_model=List[MPIResponse])
async def batch_match(request: BatchRequest, req: Request):
    """Process multiple patients in batch"""
    start_time = time.perf_counter()

    try:
        results = await req.app.state.mpi_service.batch_process(request.patients)
        processing_time = (time.perf_counter() - start_time) * 1000

        request_count.labels(method='batch', status='success').inc()

        return [
            MPIResponse(
                mpi_id=r.get('mpi_id'),
                confidence=r.get('confidence'),
                provider=r.get('provider'),
                processing_time_ms=processing_time / len(results)
            )
            for r in results
        ]
    except Exception as e:
        request_count.labels(method='batch', status='error').inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "provider": os.getenv("MPI_PROVIDER", "verato"),
        "performance": {
            "connection_pool_size": PERFORMANCE_CONFIG["connection_pool_size"],
            "redis_pool_size": PERFORMANCE_CONFIG["redis_pool_size"],
            "cache_ttl": PERFORMANCE_CONFIG["cache_ttl"]
        }
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn

    # Run with optimized settings
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        workers=os.cpu_count(),  # Multiple workers
        loop="uvloop",  # Use uvloop
        log_level="info",
        access_log=False,  # Disable for performance
        reload=False
    )
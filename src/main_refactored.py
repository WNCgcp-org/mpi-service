"""
MPI Service - Refactored with Domain-Driven Design
Controller/Service/Repository Pattern
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

# Performance optimizations
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("✓ Using uvloop for enhanced performance")
except ImportError:
    print("⚠ uvloop not installed, using standard asyncio")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp

# Import domain controllers
from domains.patient.controllers.patient_controller import router as patient_router
from domains.matching.controllers.matching_controller import router as matching_router
from domains.admin.controllers.admin_controller import router as admin_router
from domains.monitoring.controllers.monitoring_controller import router as monitoring_router
from domains.config.controllers.config_controller import router as config_router

# Import repositories for initialization
from domains.patient.repositories.patient_repository import PatientRepository
from domains.matching.repositories.matching_repository import MatchingRepository
from domains.monitoring.repositories.monitoring_repository import MonitoringRepository

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MPIServiceContext:
    """Centralized service context for dependency injection"""

    def __init__(self):
        self.redis_pool = None
        self.redis = None
        self.mongo_client = None
        self.db = None
        self.http_session = None
        self.session = None  # Alias
        self.provider = None
        self.provider_name = os.getenv("MPI_PROVIDER", "internal")
        self.start_time = datetime.utcnow()
        self._initialized = False

        # Performance settings
        self.connection_pool_size = int(os.getenv("CONNECTION_POOL_SIZE", "100"))
        self.redis_pool_size = int(os.getenv("REDIS_POOL_SIZE", "50"))
        self.mongo_pool_size = int(os.getenv("MONGO_POOL_SIZE", "50"))

    async def initialize(self):
        """Initialize all connections and services"""
        if self._initialized:
            return

        logger.info("Initializing MPI Service Context...")

        # Initialize Redis
        self.redis_pool = redis.ConnectionPool(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            max_connections=self.redis_pool_size,
            decode_responses=False
        )
        self.redis = redis.Redis(connection_pool=self.redis_pool)

        # Initialize MongoDB
        mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.mongo_client = AsyncIOMotorClient(
            mongo_uri,
            maxPoolSize=self.mongo_pool_size,
            minPoolSize=10,
            maxIdleTimeMS=10000,
            serverSelectionTimeoutMS=5000
        )
        self.db = self.mongo_client[os.getenv("MPI_DB", "mpi_service")]

        # Initialize HTTP session for external calls
        connector = aiohttp.TCPConnector(
            limit=self.connection_pool_size,
            limit_per_host=30,
            ttl_dns_cache=300
        )
        timeout = aiohttp.ClientTimeout(total=30)
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
        self.session = self.http_session  # Alias

        # Initialize provider
        await self._init_provider()

        # Initialize repositories
        await self._init_repositories()

        self._initialized = True
        logger.info("MPI Service Context initialized successfully")

    async def _init_provider(self):
        """Initialize the configured provider"""
        logger.info(f"Initializing provider: {self.provider_name}")

        if self.provider_name == "verato":
            from providers import VeratoProvider
            self.provider = VeratoProvider(
                api_key=os.getenv("VERATO_API_KEY"),
                endpoint=os.getenv("VERATO_ENDPOINT")
            )
            await self.provider.initialize()
        elif self.provider_name == "hybrid":
            from providers import HybridMPIProvider
            self.provider = HybridMPIProvider(mpi_service=self)
            await self.provider.initialize()
        else:  # Default to internal
            from providers import InternalMPIProvider
            self.provider = InternalMPIProvider(mpi_service=self)
            await self.provider.initialize()

    async def _init_repositories(self):
        """Initialize repository indexes"""
        logger.info("Initializing repository indexes...")

        # Patient repository
        patient_repo = PatientRepository(self.db)
        await patient_repo.initialize()

        # Matching repository
        matching_repo = MatchingRepository(self.db, self.redis)
        await matching_repo.initialize()

        # Monitoring repository
        monitoring_repo = MonitoringRepository(self.db)
        await monitoring_repo.initialize()

        logger.info("Repository indexes created")

    async def cleanup(self):
        """Cleanup all connections"""
        logger.info("Cleaning up MPI Service Context...")

        if self.http_session:
            await self.http_session.close()

        if self.redis_pool:
            await self.redis_pool.disconnect()

        if self.mongo_client:
            self.mongo_client.close()

        if self.provider and hasattr(self.provider, 'cleanup'):
            await self.provider.cleanup()

        logger.info("Cleanup complete")

    async def get_mpi_id(self, patient_data):
        """Compatibility method for legacy code"""
        if hasattr(self.provider, 'get_mpi_id'):
            result = await self.provider.get_mpi_id(patient_data)
            # Convert to dict if needed
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            elif hasattr(result, 'dict'):
                return result.dict()
            return result
        else:
            raise NotImplementedError("Provider does not implement get_mpi_id")

    async def clear_all_caches(self):
        """Clear all cache levels"""
        try:
            await self.redis.flushdb()
            logger.info("All caches cleared")
        except Exception as e:
            logger.error(f"Error clearing caches: {e}")


# FastAPI application with lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle"""
    # Startup
    logger.info("Starting MPI Service...")
    app.state.mpi_service = MPIServiceContext()
    await app.state.mpi_service.initialize()
    logger.info("MPI Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down MPI Service...")
    await app.state.mpi_service.cleanup()
    logger.info("MPI Service shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="MPI Service",
    version="2.0.0",
    description="Master Patient Index Service with Domain-Driven Design",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include domain routers
app.include_router(patient_router)
app.include_router(matching_router)
app.include_router(admin_router)
app.include_router(monitoring_router)
app.include_router(config_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "provider": os.getenv("MPI_PROVIDER", "internal"),
        "timestamp": datetime.utcnow()
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "MPI Service",
        "version": "2.0.0",
        "architecture": "Domain-Driven Design",
        "pattern": "Controller/Service/Repository",
        "documentation": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn

    # Run with optimized settings
    uvicorn.run(
        "main_refactored:app",
        host="0.0.0.0",
        port=8000,
        workers=os.cpu_count(),
        loop="uvloop",
        log_level="info",
        access_log=False,
        reload=False
    )
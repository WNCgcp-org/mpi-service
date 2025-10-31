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
import aiohttp

# Core utilities
from core.config import get_config, ApplicationConfig
from core.database import initialize_database, cleanup_database, get_database_manager
from core.cache import initialize_cache, cleanup_cache, get_cache_manager

# Import domain controllers
from domains.patient.controllers.patient_controller import router as patient_router
from domains.matching.controllers.matching_controller import router as matching_router
from domains.admin.controllers.admin_controller import router as admin_router
from domains.monitoring.controllers.monitoring_controller import router as monitoring_router
from domains.config.controllers.config_controller import router as config_router

# Configure logging
config = get_config()
logging.basicConfig(
    level=getattr(logging, config.logging.level.upper()),
    format=config.logging.format
)
logger = logging.getLogger(__name__)


class MPIServiceContext:
    """Centralized service context for dependency injection"""

    def __init__(self, config: ApplicationConfig):
        self.config = config
        self.http_session = None
        self.session = None  # Alias
        self.provider = None
        self.start_time = datetime.utcnow()
        self._initialized = False

    async def initialize(self):
        """Initialize all connections and services"""
        if self._initialized:
            return

        logger.info("Initializing MPI Service Context...")

        # Initialize HTTP session for external calls
        connector = aiohttp.TCPConnector(
            limit=self.config.http.max_pool_size,
            limit_per_host=self.config.http.max_per_host,
            ttl_dns_cache=self.config.http.ttl_dns_cache
        )
        timeout = aiohttp.ClientTimeout(total=self.config.http.total_timeout)
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
        self.session = self.http_session  # Alias

        # Initialize provider
        await self._init_provider()

        self._initialized = True
        logger.info("MPI Service Context initialized successfully")

    async def _init_provider(self):
        """Initialize the configured provider"""
        provider_name = self.config.mpi_provider.provider_name
        logger.info(f"Initializing provider: {provider_name}")

        if provider_name == "verato":
            from providers import VeratoProvider
            self.provider = VeratoProvider(
                api_key=self.config.mpi_provider.verato_api_key,
                endpoint=self.config.mpi_provider.verato_endpoint
            )
            await self.provider.initialize()
        elif provider_name == "hybrid":
            from providers import HybridMPIProvider
            self.provider = HybridMPIProvider(mpi_service=self)
            await self.provider.initialize()
        else:  # Default to internal
            from providers import InternalMPIProvider
            self.provider = InternalMPIProvider(mpi_service=self)
            await self.provider.initialize()

    async def cleanup(self):
        """Cleanup all connections"""
        logger.info("Cleaning up MPI Service Context...")

        if self.http_session:
            await self.http_session.close()

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
            cache_manager = get_cache_manager()
            if cache_manager._initialized:
                await cache_manager.flush_db()
                logger.info("All caches cleared")
        except Exception as e:
            logger.error(f"Error clearing caches: {e}")


# FastAPI application with lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage service lifecycle"""
    # Startup
    logger.info("Starting MPI Service...")

    # Get configuration
    app_config = get_config()

    # Initialize core managers
    logger.info("Initializing database manager...")
    db_manager = await initialize_database()
    app.state.db_manager = db_manager

    logger.info("Initializing cache manager...")
    cache_manager = await initialize_cache()
    app.state.cache_manager = cache_manager

    # Initialize MPI service context
    app.state.mpi_service = MPIServiceContext(app_config)
    await app.state.mpi_service.initialize()

    logger.info("MPI Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down MPI Service...")

    # Cleanup in reverse order
    await app.state.mpi_service.cleanup()
    await cleanup_cache()
    await cleanup_database()

    logger.info("MPI Service shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="Master Patient Index Service with Domain-Driven Design",
    lifespan=lifespan,
    docs_url="/docs" if not config.is_production() else None,
    redoc_url="/redoc" if not config.is_production() else None,
    debug=config.debug
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.cors_origins,
    allow_credentials=config.security.cors_allow_credentials,
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
        "version": config.app_version,
        "provider": config.mpi_provider.provider_name,
        "environment": config.environment,
        "timestamp": datetime.utcnow()
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": config.app_name,
        "version": config.app_version,
        "environment": config.environment,
        "architecture": "Domain-Driven Design",
        "pattern": "Controller/Service/Repository",
        "documentation": "/docs" if not config.is_production() else "disabled in production",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn

    # Run with optimized settings from config
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        workers=config.workers if not config.debug else 1,
        loop="uvloop",
        log_level=config.logging.level.lower(),
        access_log=config.debug,
        reload=config.debug
    )
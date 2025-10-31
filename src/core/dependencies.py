"""
Dependency injection for the application
"""

from typing import AsyncGenerator, Optional
from fastapi import Request, Depends

# Core utilities
from core.database import DatabaseManager, get_database_manager
from core.cache import CacheManager, get_cache_manager
from core.config import get_config

# Domain services
from domains.patient.services.patient_service import PatientService
from domains.patient.repositories.patient_repository import PatientRepository

from domains.admin.services.admin_service import AdminService
from domains.admin.repositories.admin_repository import AdminRepository

from domains.monitoring.services.monitoring_service import MonitoringService
from domains.monitoring.repositories.monitoring_repository import MonitoringRepository

from domains.config.services.config_service import ConfigService
from domains.config.repositories.config_repository import ConfigRepository

from domains.matching.services.matching_service import MatchingService
from domains.matching.repositories.matching_repository import MatchingRepository


# Core dependencies
async def get_database_manager(request: Request) -> DatabaseManager:
    """Get database manager instance"""
    return request.app.state.db_manager


async def get_cache_manager(request: Request) -> Optional[CacheManager]:
    """Get cache manager instance"""
    return getattr(request.app.state, 'cache_manager', None)


async def get_mpi_service(request: Request):
    """Get MPI service instance"""
    return request.app.state.mpi_service


# Repository dependencies
async def get_patient_repository(
    db_manager: DatabaseManager = Depends(get_database_manager),
    cache_manager: Optional[CacheManager] = Depends(get_cache_manager)
) -> PatientRepository:
    """Get patient repository instance"""
    return PatientRepository(db_manager, cache_manager)


async def get_admin_repository(
    db_manager: DatabaseManager = Depends(get_database_manager),
    cache_manager: Optional[CacheManager] = Depends(get_cache_manager)
) -> AdminRepository:
    """Get admin repository instance"""
    return AdminRepository(db_manager, cache_manager)


async def get_monitoring_repository(
    db_manager: DatabaseManager = Depends(get_database_manager),
    cache_manager: Optional[CacheManager] = Depends(get_cache_manager)
) -> MonitoringRepository:
    """Get monitoring repository instance"""
    return MonitoringRepository(db_manager, cache_manager)


async def get_config_repository(
    db_manager: DatabaseManager = Depends(get_database_manager),
    cache_manager: Optional[CacheManager] = Depends(get_cache_manager)
) -> ConfigRepository:
    """Get config repository instance"""
    return ConfigRepository(db_manager, cache_manager)


async def get_matching_repository(
    db_manager: DatabaseManager = Depends(get_database_manager),
    cache_manager: Optional[CacheManager] = Depends(get_cache_manager)
) -> MatchingRepository:
    """Get matching repository instance"""
    return MatchingRepository(db_manager, cache_manager)


# Service dependencies
async def get_patient_service(
    repository: PatientRepository = Depends(get_patient_repository)
) -> PatientService:
    """Get patient service instance"""
    return PatientService(repository)


async def get_admin_service(
    repository: AdminRepository = Depends(get_admin_repository),
    patient_repository: PatientRepository = Depends(get_patient_repository)
) -> AdminService:
    """Get admin service instance"""
    return AdminService(repository, patient_repository)


async def get_monitoring_service(
    repository: MonitoringRepository = Depends(get_monitoring_repository),
    mpi_service = Depends(get_mpi_service)
) -> MonitoringService:
    """Get monitoring service instance"""
    return MonitoringService(repository, mpi_service)


async def get_config_service(
    repository: ConfigRepository = Depends(get_config_repository),
    mpi_service = Depends(get_mpi_service)
) -> ConfigService:
    """Get config service instance"""
    return ConfigService(repository, mpi_service)


async def get_matching_service(
    repository: MatchingRepository = Depends(get_matching_repository),
    mpi_service = Depends(get_mpi_service)
) -> MatchingService:
    """Get matching service instance"""
    return MatchingService(repository, mpi_service)
"""
Dependency injection for the application
"""

from typing import AsyncGenerator
from fastapi import Request, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
import redis.asyncio as redis

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


# Database dependencies
async def get_database(request: Request) -> AsyncIOMotorDatabase:
    """Get MongoDB database instance"""
    return request.app.state.mpi_service.db


async def get_redis(request: Request) -> redis.Redis:
    """Get Redis client instance"""
    return request.app.state.mpi_service.redis


async def get_mpi_service(request: Request):
    """Get MPI service instance"""
    return request.app.state.mpi_service


# Repository dependencies
async def get_patient_repository(
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> PatientRepository:
    """Get patient repository instance"""
    return PatientRepository(db)


async def get_admin_repository(
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> AdminRepository:
    """Get admin repository instance"""
    return AdminRepository(db)


async def get_monitoring_repository(
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> MonitoringRepository:
    """Get monitoring repository instance"""
    return MonitoringRepository(db)


async def get_config_repository(
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> ConfigRepository:
    """Get config repository instance"""
    return ConfigRepository(db)


async def get_matching_repository(
    db: AsyncIOMotorDatabase = Depends(get_database),
    redis_client: redis.Redis = Depends(get_redis)
) -> MatchingRepository:
    """Get matching repository instance"""
    return MatchingRepository(db, redis_client)


# Service dependencies
async def get_patient_service(
    repository: PatientRepository = Depends(get_patient_repository),
    redis_client: redis.Redis = Depends(get_redis)
) -> PatientService:
    """Get patient service instance"""
    return PatientService(repository, redis_client)


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
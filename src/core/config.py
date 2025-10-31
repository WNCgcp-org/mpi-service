"""
Centralized configuration management for MPI Service
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration settings"""
    uri: str = field(default_factory=lambda: os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    name: str = field(default_factory=lambda: os.getenv("MPI_DB", "mpi_service"))
    max_pool_size: int = field(default_factory=lambda: int(os.getenv("MONGO_POOL_SIZE", "50")))
    min_pool_size: int = field(default_factory=lambda: int(os.getenv("MONGO_MIN_POOL_SIZE", "10")))
    max_idle_time_ms: int = field(default_factory=lambda: int(os.getenv("MONGO_MAX_IDLE_TIME_MS", "10000")))
    server_selection_timeout_ms: int = field(default_factory=lambda: int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000")))

    # Collection names
    mpi_identifiers_collection: str = "mpi_identifiers"
    identifier_mappings_collection: str = "identifier_mappings"
    patient_audit_collection: str = "patient_audit"
    patient_links_collection: str = "patient_links"
    cache_collection: str = "cache"
    metrics_collection: str = "metrics"


@dataclass
class RedisConfig:
    """Redis configuration settings"""
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    password: Optional[str] = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    max_connections: int = field(default_factory=lambda: int(os.getenv("REDIS_POOL_SIZE", "50")))
    socket_timeout: int = field(default_factory=lambda: int(os.getenv("REDIS_SOCKET_TIMEOUT", "30")))
    socket_connect_timeout: int = field(default_factory=lambda: int(os.getenv("REDIS_CONNECT_TIMEOUT", "30")))
    decode_responses: bool = False  # We want bytes for orjson serialization

    # Cache TTL settings
    default_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("CACHE_DEFAULT_TTL", "3600")))
    match_cache_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("MATCH_CACHE_TTL", "3600")))
    metrics_retention_days: int = field(default_factory=lambda: int(os.getenv("METRICS_RETENTION_DAYS", "30")))


@dataclass
class HTTPConfig:
    """HTTP client configuration settings"""
    total_timeout: int = field(default_factory=lambda: int(os.getenv("HTTP_TOTAL_TIMEOUT", "30")))
    connect_timeout: int = field(default_factory=lambda: int(os.getenv("HTTP_CONNECT_TIMEOUT", "10")))
    max_pool_size: int = field(default_factory=lambda: int(os.getenv("CONNECTION_POOL_SIZE", "100")))
    max_per_host: int = field(default_factory=lambda: int(os.getenv("HTTP_MAX_PER_HOST", "30")))
    ttl_dns_cache: int = field(default_factory=lambda: int(os.getenv("HTTP_DNS_CACHE_TTL", "300")))


@dataclass
class MPIProviderConfig:
    """MPI provider configuration settings"""
    provider_name: str = field(default_factory=lambda: os.getenv("MPI_PROVIDER", "internal"))

    # Verato specific
    verato_api_key: Optional[str] = field(default_factory=lambda: os.getenv("VERATO_API_KEY"))
    verato_endpoint: Optional[str] = field(default_factory=lambda: os.getenv("VERATO_ENDPOINT"))
    verato_timeout: int = field(default_factory=lambda: int(os.getenv("VERATO_TIMEOUT", "30")))

    # Hybrid provider settings
    primary_threshold: float = field(default_factory=lambda: float(os.getenv("HYBRID_PRIMARY_THRESHOLD", "0.9")))
    fallback_enabled: bool = field(default_factory=lambda: os.getenv("HYBRID_FALLBACK_ENABLED", "true").lower() == "true")


@dataclass
class SecurityConfig:
    """Security configuration settings"""
    jwt_secret_key: str = field(default_factory=lambda: os.getenv("JWT_SECRET_KEY", "dev-secret-key"))
    jwt_algorithm: str = field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    jwt_expiration_minutes: int = field(default_factory=lambda: int(os.getenv("JWT_EXPIRATION_MINUTES", "30")))

    # Rate limiting
    rate_limit_requests: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_REQUESTS", "100")))
    rate_limit_window: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_WINDOW", "60")))

    # CORS settings
    cors_origins: list = field(default_factory=lambda: os.getenv("CORS_ORIGINS", "*").split(","))
    cors_allow_credentials: bool = field(default_factory=lambda: os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true")


@dataclass
class LoggingConfig:
    """Logging configuration settings"""
    level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    format: str = field(default_factory=lambda: os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

    # File logging
    log_file: Optional[str] = field(default_factory=lambda: os.getenv("LOG_FILE"))
    max_file_size: int = field(default_factory=lambda: int(os.getenv("LOG_MAX_FILE_SIZE", "10485760")))  # 10MB
    backup_count: int = field(default_factory=lambda: int(os.getenv("LOG_BACKUP_COUNT", "5")))


@dataclass
class PerformanceConfig:
    """Performance and monitoring configuration"""
    enable_metrics: bool = field(default_factory=lambda: os.getenv("ENABLE_METRICS", "true").lower() == "true")
    metrics_interval_seconds: int = field(default_factory=lambda: int(os.getenv("METRICS_INTERVAL", "60")))

    # Request timeouts
    api_timeout: int = field(default_factory=lambda: int(os.getenv("API_TIMEOUT", "30")))
    database_timeout: int = field(default_factory=lambda: int(os.getenv("DATABASE_TIMEOUT", "30")))

    # Batch processing
    batch_size: int = field(default_factory=lambda: int(os.getenv("BATCH_SIZE", "1000")))
    max_concurrent_requests: int = field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_REQUESTS", "100")))


@dataclass
class ApplicationConfig:
    """Main application configuration"""
    # Basic app settings
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "MPI Service"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "2.0.0"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    # Server settings
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    workers: int = field(default_factory=lambda: int(os.getenv("WORKERS", str(os.cpu_count() or 1))))

    # Component configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    http: HTTPConfig = field(default_factory=HTTPConfig)
    mpi_provider: MPIProviderConfig = field(default_factory=MPIProviderConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)

    def __post_init__(self):
        """Validate configuration after initialization"""
        self.validate()

    def validate(self):
        """Validate configuration settings"""
        errors = []

        # Database validation
        if not self.database.uri:
            errors.append("Database URI is required")
        if not self.database.name:
            errors.append("Database name is required")

        # Redis validation
        if not self.redis.host:
            errors.append("Redis host is required")
        if not (1 <= self.redis.port <= 65535):
            errors.append("Redis port must be between 1 and 65535")

        # Provider validation
        if self.mpi_provider.provider_name == "verato":
            if not self.mpi_provider.verato_api_key:
                errors.append("Verato API key is required when using Verato provider")
            if not self.mpi_provider.verato_endpoint:
                errors.append("Verato endpoint is required when using Verato provider")

        # Security validation
        if not self.security.jwt_secret_key or self.security.jwt_secret_key == "dev-secret-key":
            if self.environment == "production":
                errors.append("JWT secret key must be set in production")

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

    def get_database_collections(self) -> Dict[str, str]:
        """Get all database collection names"""
        return {
            "mpi_identifiers": self.database.mpi_identifiers_collection,
            "identifier_mappings": self.database.identifier_mappings_collection,
            "patient_audit": self.database.patient_audit_collection,
            "patient_links": self.database.patient_links_collection,
            "cache": self.database.cache_collection,
            "metrics": self.database.metrics_collection,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (for logging/debugging)"""
        config_dict = {}
        for field_name, field_value in self.__dict__.items():
            if hasattr(field_value, '__dict__'):
                config_dict[field_name] = field_value.__dict__.copy()
                # Mask sensitive values
                if field_name == 'security':
                    config_dict[field_name]['jwt_secret_key'] = '***masked***'
                elif field_name == 'mpi_provider':
                    if 'verato_api_key' in config_dict[field_name]:
                        config_dict[field_name]['verato_api_key'] = '***masked***'
                elif field_name == 'redis':
                    if 'password' in config_dict[field_name] and config_dict[field_name]['password']:
                        config_dict[field_name]['password'] = '***masked***'
            else:
                config_dict[field_name] = field_value
        return config_dict


@lru_cache(maxsize=1)
def get_config() -> ApplicationConfig:
    """
    Get application configuration singleton.
    Uses LRU cache to ensure same instance is returned.
    """
    config = ApplicationConfig()
    logger.info(f"Configuration loaded for environment: {config.environment}")
    return config


def load_config_from_file(file_path: str) -> ApplicationConfig:
    """
    Load configuration from a file (JSON/YAML).
    This is useful for testing or when environment variables aren't preferred.
    """
    import json

    try:
        with open(file_path, 'r') as f:
            config_data = json.load(f)

        # Override environment variables with file values
        for key, value in config_data.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    env_key = f"{key.upper()}_{sub_key.upper()}"
                    os.environ[env_key] = str(sub_value)
            else:
                os.environ[key.upper()] = str(value)

        # Clear cached config and reload
        get_config.cache_clear()
        return get_config()

    except FileNotFoundError:
        logger.error(f"Configuration file not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file: {e}")
        raise


# Convenience functions for common config access patterns
def get_database_config() -> DatabaseConfig:
    """Get database configuration"""
    return get_config().database


def get_redis_config() -> RedisConfig:
    """Get Redis configuration"""
    return get_config().redis


def get_security_config() -> SecurityConfig:
    """Get security configuration"""
    return get_config().security


def get_performance_config() -> PerformanceConfig:
    """Get performance configuration"""
    return get_config().performance


def is_development() -> bool:
    """Check if running in development environment"""
    return get_config().environment.lower() == "development"


def is_production() -> bool:
    """Check if running in production environment"""
    return get_config().environment.lower() == "production"
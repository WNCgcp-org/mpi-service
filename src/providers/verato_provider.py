"""
Verato MPI Provider

Updated Verato provider that follows the standardized provider interface.
This wraps the existing VeratoModule to maintain compatibility while
providing the new interface.
"""

import os
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .base_provider import BaseMPIProvider, MPIResult, ProviderConfig
from .verato import VeratoModule, VeratoConfig

logger = logging.getLogger(__name__)


@dataclass
class VeratoProviderConfig(ProviderConfig):
    """Configuration for Verato MPI Provider"""

    # Verato API settings
    api_key: str = os.getenv('VERATO_API_KEY', '')
    endpoint: str = os.getenv('VERATO_ENDPOINT', 'https://api.verato.com')
    verato_timeout: int = int(os.getenv('VERATO_TIMEOUT', '5000'))
    max_retries: int = int(os.getenv('VERATO_MAX_RETRIES', '3'))

    # Cache settings
    cache_ttl: int = int(os.getenv('VERATO_CACHE_TTL', '86400'))  # 24 hours

    # MongoDB settings
    mongo_uri: str = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    mongo_db: str = os.getenv('MPI_DB', 'mpi_service')
    mongo_collection: str = os.getenv('MPI_COLLECTION', 'verato_ids')

    # Redis settings
    redis_host: str = os.getenv('REDIS_HOST', 'localhost')
    redis_port: int = int(os.getenv('REDIS_PORT', '6379'))
    redis_db: int = int(os.getenv('REDIS_DB', '0'))

    def to_verato_config(self) -> VeratoConfig:
        """Convert to legacy VeratoConfig format"""
        return VeratoConfig(
            api_key=self.api_key,
            endpoint=self.endpoint,
            timeout=self.verato_timeout,
            max_retries=self.max_retries,
            cache_ttl=self.cache_ttl,
            mongo_uri=self.mongo_uri,
            mongo_db=self.mongo_db,
            mongo_collection=self.mongo_collection,
            redis_host=self.redis_host,
            redis_port=self.redis_port,
            redis_db=self.redis_db
        )


class VeratoProvider(BaseMPIProvider):
    """
    Standardized Verato MPI Provider

    This provider wraps the existing VeratoModule to provide
    the standardized interface while maintaining all existing
    Verato functionality.
    """

    def __init__(self, config: VeratoProviderConfig = None, api_key: str = None, endpoint: str = None):
        super().__init__(config or VeratoProviderConfig())
        self.config: VeratoProviderConfig = self.config

        # Allow override of key parameters
        if api_key:
            self.config.api_key = api_key
        if endpoint:
            self.config.endpoint = endpoint

        # Wrapped Verato module
        self.verato_module = None

        # Statistics
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.cache_hits = 0
        self.api_calls = 0

    async def initialize(self) -> None:
        """Initialize the Verato module"""
        try:
            # Create legacy config
            verato_config = self.config.to_verato_config()

            # Initialize the wrapped module
            self.verato_module = VeratoModule(verato_config)

            self._initialized = True
            logger.info("Verato Provider initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Verato Provider: {e}")
            raise

    async def get_mpi_id(self, patient_data: Dict[str, Any]) -> MPIResult:
        """
        Get Verato MPI ID for a patient

        Args:
            patient_data: Standardized patient demographic data

        Returns:
            MPIResult with Verato ID and metadata
        """
        self.total_calls += 1

        try:
            # Validate input
            self._validate_patient_data(patient_data)

            # Standardize data
            standardized_data = self._standardize_patient_data(patient_data)

            # Call the wrapped Verato module
            verato_result = await self.verato_module.get_mpi_id(standardized_data)

            # Convert to standardized format
            if verato_result.get('error'):
                self.failed_calls += 1
                return MPIResult(
                    mpi_id=None,
                    confidence=0.0,
                    provider='verato',
                    source=verato_result.get('source', 'error'),
                    error=verato_result['error'],
                    metadata={
                        'tracking_id': verato_result.get('tracking_id'),
                        'raw_response': verato_result
                    }
                )
            else:
                self.successful_calls += 1

                # Track cache hits vs API calls
                if verato_result.get('source') in ['cache', 'database']:
                    self.cache_hits += 1
                elif verato_result.get('source') == 'api':
                    self.api_calls += 1

                return MPIResult(
                    mpi_id=verato_result.get('verato_id'),
                    confidence=verato_result.get('confidence', 0.95),
                    provider='verato',
                    source=verato_result.get('source', 'api'),
                    metadata={
                        'tracking_id': verato_result.get('tracking_id'),
                        'raw_response': verato_result
                    }
                )

        except Exception as e:
            self.failed_calls += 1
            logger.error(f"Verato provider error: {e}")
            return MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='verato',
                source='exception',
                error=str(e)
            )

    async def batch_process(self, patient_records: List[Dict[str, Any]],
                          max_concurrent: int = 40) -> List[MPIResult]:
        """
        Process multiple patient records using Verato's batch processing
        """
        try:
            # Standardize all patient data
            standardized_records = []
            for patient in patient_records:
                try:
                    self._validate_patient_data(patient)
                    standardized = self._standardize_patient_data(patient)
                    standardized_records.append(standardized)
                except Exception as e:
                    logger.warning(f"Skipping invalid patient record: {e}")
                    standardized_records.append(None)

            # Filter out None records for batch processing
            valid_records = [r for r in standardized_records if r is not None]
            valid_indices = [i for i, r in enumerate(standardized_records) if r is not None]

            # Use Verato's batch processing
            if valid_records:
                verato_results = await self.verato_module.batch_process(valid_records, max_concurrent)
            else:
                verato_results = []

            # Convert results to standardized format
            standardized_results = []
            valid_result_index = 0

            for i, original_record in enumerate(standardized_records):
                if original_record is None:
                    # Invalid record
                    standardized_results.append(MPIResult(
                        mpi_id=None,
                        confidence=0.0,
                        provider='verato',
                        source='validation_error',
                        error='Invalid patient data'
                    ))
                else:
                    # Valid record - get corresponding result
                    if valid_result_index < len(verato_results):
                        verato_result = verato_results[valid_result_index]
                        valid_result_index += 1

                        if verato_result.get('error'):
                            standardized_results.append(MPIResult(
                                mpi_id=None,
                                confidence=0.0,
                                provider='verato',
                                source=verato_result.get('source', 'error'),
                                error=verato_result['error'],
                                metadata={'raw_response': verato_result}
                            ))
                        else:
                            standardized_results.append(MPIResult(
                                mpi_id=verato_result.get('verato_id'),
                                confidence=verato_result.get('confidence', 0.95),
                                provider='verato',
                                source=verato_result.get('source', 'api'),
                                metadata={'raw_response': verato_result}
                            ))
                    else:
                        # Missing result
                        standardized_results.append(MPIResult(
                            mpi_id=None,
                            confidence=0.0,
                            provider='verato',
                            source='batch_error',
                            error='Missing result from batch processing'
                        ))

            return standardized_results

        except Exception as e:
            logger.error(f"Verato batch processing error: {e}")
            # Return error results for all records
            return [MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='verato',
                source='batch_exception',
                error=str(e)
            ) for _ in patient_records]

    async def health_check(self) -> Dict[str, Any]:
        """Check Verato provider health"""
        try:
            # Test with minimal data
            test_patient = {
                'first_name': 'TEST',
                'last_name': 'PATIENT',
                'dob': '2000-01-01'
            }

            result = await self.get_mpi_id(test_patient)

            return {
                'status': 'healthy' if not result.error else 'unhealthy',
                'provider': 'verato',
                'test_successful': result.error is None,
                'error': result.error,
                'api_endpoint': self.config.endpoint,
                'has_api_key': bool(self.config.api_key)
            }

        except Exception as e:
            return {
                'status': 'unhealthy',
                'provider': 'verato',
                'test_successful': False,
                'error': str(e),
                'api_endpoint': self.config.endpoint,
                'has_api_key': bool(self.config.api_key)
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get Verato provider statistics"""
        base_stats = super().get_stats()

        # Calculate rates
        success_rate = self.successful_calls / max(self.total_calls, 1)
        error_rate = self.failed_calls / max(self.total_calls, 1)
        cache_hit_rate = self.cache_hits / max(self.total_calls, 1)

        verato_stats = {
            'total_calls': self.total_calls,
            'successful_calls': self.successful_calls,
            'failed_calls': self.failed_calls,
            'cache_hits': self.cache_hits,
            'api_calls': self.api_calls,
            'success_rate': success_rate,
            'error_rate': error_rate,
            'cache_hit_rate': cache_hit_rate,
            'api_endpoint': self.config.endpoint,
            'has_api_key': bool(self.config.api_key),
            'timeout_ms': self.config.verato_timeout,
            'cache_ttl_seconds': self.config.cache_ttl
        }

        # Include wrapped module stats if available
        if self.verato_module:
            module_stats = self.verato_module.get_stats()
            verato_stats['module_stats'] = module_stats

        base_stats.update(verato_stats)
        return base_stats

    async def cleanup(self) -> None:
        """Cleanup Verato provider resources"""
        if self.verato_module:
            try:
                # Close connections in the wrapped module
                if hasattr(self.verato_module, 'mongo_client'):
                    self.verato_module.mongo_client.close()

                if hasattr(self.verato_module, 'redis_client'):
                    self.verato_module.redis_client.close()
            except Exception as e:
                logger.warning(f"Error cleaning up Verato module: {e}")

        await super().cleanup()

    def _convert_for_verato(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert standardized patient data to format expected by Verato

        The existing VeratoModule expects specific field names, so we may need
        to map our standardized fields to what it expects.
        """
        # The existing VeratoModule should handle standardized field names,
        # but we can add any specific conversions here if needed
        return patient_data
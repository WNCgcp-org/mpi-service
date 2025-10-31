"""
Base MPI Provider Interface

Defines the standard interface that all MPI providers must implement.
This ensures consistent integration with the main MPI service.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class MPIResult:
    """Standardized MPI result structure"""
    mpi_id: Optional[str]
    confidence: float
    provider: str
    source: str  # 'api', 'cache', 'database', 'probabilistic', etc.
    metadata: Dict[str, Any] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'mpi_id': self.mpi_id,
            'confidence': self.confidence,
            'provider': self.provider,
            'source': self.source,
            'metadata': self.metadata
        }
        if self.error:
            result['error'] = self.error
        return result


@dataclass
class ProviderConfig:
    """Base configuration for providers"""
    timeout_seconds: int = 30
    max_retries: int = 3
    confidence_threshold: float = 0.8
    cache_ttl_seconds: int = 3600

    def __post_init__(self):
        # Validate configuration
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if self.cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds must be positive")


class BaseMPIProvider(ABC):
    """
    Abstract base class for all MPI providers

    This defines the standard interface that all providers must implement
    to ensure consistent integration with the MPI service.
    """

    def __init__(self, config: ProviderConfig = None):
        self.config = config or ProviderConfig()
        self.provider_name = self.__class__.__name__.replace('Provider', '').lower()
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the provider

        This method should set up any necessary connections,
        authentication, or resources needed by the provider.
        """
        pass

    @abstractmethod
    async def get_mpi_id(self, patient_data: Dict[str, Any]) -> MPIResult:
        """
        Get MPI ID for a patient

        Args:
            patient_data: Standardized patient demographic data

        Returns:
            MPIResult with MPI ID and metadata
        """
        pass

    async def batch_process(self, patient_records: List[Dict[str, Any]],
                          max_concurrent: int = 40) -> List[MPIResult]:
        """
        Process multiple patient records concurrently

        Default implementation processes sequentially.
        Providers can override this for optimized batch processing.

        Args:
            patient_records: List of patient data dictionaries
            max_concurrent: Maximum concurrent requests

        Returns:
            List of MPIResult objects
        """
        results = []
        for patient in patient_records:
            try:
                result = await self.get_mpi_id(patient)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch processing error for patient: {e}")
                results.append(MPIResult(
                    mpi_id=None,
                    confidence=0.0,
                    provider=self.provider_name,
                    source='error',
                    error=str(e)
                ))
        return results

    async def health_check(self) -> Dict[str, Any]:
        """
        Check provider health status

        Returns:
            Dictionary with health status information
        """
        try:
            # Basic test - try to process minimal test data
            test_patient = {
                'first_name': 'TEST',
                'last_name': 'PATIENT',
                'dob': '2000-01-01'
            }

            result = await self.get_mpi_id(test_patient)

            return {
                'status': 'healthy',
                'provider': self.provider_name,
                'test_successful': result.error is None,
                'error': result.error
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'provider': self.provider_name,
                'test_successful': False,
                'error': str(e)
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get provider statistics

        Default implementation returns basic stats.
        Providers should override to provide detailed metrics.

        Returns:
            Dictionary with provider statistics
        """
        return {
            'provider': self.provider_name,
            'initialized': self._initialized,
            'config': {
                'timeout_seconds': self.config.timeout_seconds,
                'max_retries': self.config.max_retries,
                'confidence_threshold': self.config.confidence_threshold
            }
        }

    async def cleanup(self) -> None:
        """
        Cleanup provider resources

        This method should clean up any connections or resources
        when the provider is being shut down.
        """
        self._initialized = False

    def _validate_patient_data(self, patient_data: Dict[str, Any]) -> None:
        """
        Validate patient data contains required fields

        Args:
            patient_data: Patient demographic data

        Raises:
            ValueError: If required fields are missing
        """
        required_fields = ['first_name', 'last_name']
        missing_fields = [field for field in required_fields
                         if not patient_data.get(field)]

        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

    def _standardize_patient_data(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardize patient data format

        Args:
            patient_data: Raw patient data

        Returns:
            Standardized patient data
        """
        standardized = {}

        # Standard field mappings
        field_mappings = {
            # Name fields
            'patient_first_name': 'first_name',
            'firstName': 'first_name',
            'first': 'first_name',
            'patient_last_name': 'last_name',
            'lastName': 'last_name',
            'last': 'last_name',
            'patient_middle_name': 'middle_name',
            'middleName': 'middle_name',
            'middle': 'middle_name',

            # DOB fields
            'patient_dob': 'dob',
            'dateOfBirth': 'dob',
            'birth_date': 'dob',
            'birthdate': 'dob',

            # SSN fields
            'patient_ssn': 'ssn',
            'social_security_number': 'ssn',
            'social_security': 'ssn',

            # Address fields
            'patient_address': 'address_1',
            'patient_address_1': 'address_1',
            'address': 'address_1',
            'addressLine1': 'address_1',
            'patient_city': 'city',
            'patient_state': 'state',
            'patient_zip': 'zip',
            'postal_code': 'zip',
            'postalCode': 'zip',
            'zipcode': 'zip',

            # Contact fields
            'patient_phone': 'home_phone',
            'phone': 'home_phone',
            'phoneNumber': 'home_phone',
            'patient_email': 'email',
            'email_address': 'email',

            # Gender
            'patient_gender': 'gender',
            'sex': 'gender',

            # ID fields
            'patient_id': 'patient_id',
            'member_id': 'patient_id',
            'unique_id': 'patient_id'
        }

        # Apply mappings
        for original_key, value in patient_data.items():
            standard_key = field_mappings.get(original_key, original_key)
            if value and str(value).lower() not in ['', 'nan', 'none', 'null', 'not-provided']:
                standardized[standard_key] = value

        # Clean up name fields
        for name_field in ['first_name', 'last_name', 'middle_name']:
            if name_field in standardized:
                standardized[name_field] = str(standardized[name_field]).strip().title()

        # Clean up SSN
        if 'ssn' in standardized:
            ssn = str(standardized['ssn']).replace('-', '').replace(' ', '')
            if ssn.isdigit() and len(ssn) == 9:
                standardized['ssn'] = f"{ssn[:3]}-{ssn[3:5]}-{ssn[5:]}"
            else:
                # Invalid SSN format, remove it
                del standardized['ssn']

        # Clean up phone numbers
        for phone_field in ['home_phone', 'work_phone', 'cell_phone']:
            if phone_field in standardized:
                phone = ''.join(filter(str.isdigit, str(standardized[phone_field])))
                if len(phone) == 10:
                    standardized[phone_field] = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
                elif len(phone) == 11 and phone[0] == '1':
                    standardized[phone_field] = f"({phone[1:4]}) {phone[4:7]}-{phone[7:]}"
                else:
                    # Invalid phone format, remove it
                    del standardized[phone_field]

        return standardized
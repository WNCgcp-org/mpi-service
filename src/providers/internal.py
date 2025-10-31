"""
Internal MPI Provider

Provides local/probabilistic patient matching using internal algorithms.
This provider is used when external services like Verato are not available
or for fallback scenarios.
"""

import os
import hashlib
import uuid
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

import pymongo
from pymongo import MongoClient
import redis.asyncio as redis
from fuzzywuzzy import fuzz
import pandas as pd
import numpy as np

from .base_provider import BaseMPIProvider, MPIResult, ProviderConfig

logger = logging.getLogger(__name__)


@dataclass
class InternalProviderConfig(ProviderConfig):
    """Configuration for Internal MPI Provider"""

    # Database settings
    mongo_uri: str = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    mongo_db: str = os.getenv('MPI_DB', 'mpi_service')
    mongo_collection: str = os.getenv('INTERNAL_MPI_COLLECTION', 'internal_mpi')

    # Redis settings
    redis_host: str = os.getenv('REDIS_HOST', 'localhost')
    redis_port: int = int(os.getenv('REDIS_PORT', '6379'))
    redis_db: int = int(os.getenv('REDIS_DB', '1'))  # Use different DB than Verato

    # Matching algorithm settings
    fuzzy_threshold: float = 85.0  # Fuzzy string matching threshold
    exact_match_fields: List[str] = None  # Fields that must match exactly
    probabilistic_weights: Dict[str, float] = None  # Field weights for scoring

    # Performance settings
    enable_ml_matching: bool = os.getenv('FEATURE_ML_MATCHING', 'false').lower() == 'true'
    cache_enabled: bool = True

    def __post_init__(self):
        super().__post_init__()

        if self.exact_match_fields is None:
            self.exact_match_fields = ['ssn']

        if self.probabilistic_weights is None:
            self.probabilistic_weights = {
                'ssn': 0.4,
                'first_name': 0.15,
                'last_name': 0.20,
                'dob': 0.15,
                'address': 0.05,
                'phone': 0.05
            }


class InternalMPIProvider(BaseMPIProvider):
    """
    Internal MPI Provider using probabilistic matching

    This provider implements local patient matching using:
    1. Exact matching on key identifiers (SSN)
    2. Fuzzy string matching on names and addresses
    3. Probabilistic scoring algorithms
    4. Optional ML-based matching (future enhancement)
    """

    def __init__(self, config: InternalProviderConfig = None, mpi_service=None):
        super().__init__(config or InternalProviderConfig())
        self.config: InternalProviderConfig = self.config
        self.mpi_service = mpi_service  # Reference to main service for shared resources

        # Connection objects
        self.mongo_client = None
        self.db = None
        self.collection = None
        self.redis_client = None

        # Statistics
        self.exact_matches = 0
        self.fuzzy_matches = 0
        self.no_matches = 0
        self.total_queries = 0

    async def initialize(self) -> None:
        """Initialize database connections and indexes"""
        try:
            # Use shared connections if available from main service
            if self.mpi_service and hasattr(self.mpi_service, 'mongo_client'):
                self.mongo_client = self.mpi_service.mongo_client
                self.db = self.mpi_service.db
                self.redis_client = self.mpi_service.redis_client
            else:
                # Create our own connections
                self.mongo_client = MongoClient(self.config.mongo_uri)
                self.db = self.mongo_client[self.config.mongo_db]

                # Redis connection
                self.redis_client = redis.Redis(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    db=self.config.redis_db,
                    decode_responses=True
                )

            # Set up our collection
            self.collection = self.db[self.config.mongo_collection]

            # Create optimized indexes
            await self._create_indexes()

            self._initialized = True
            logger.info("Internal MPI Provider initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Internal MPI Provider: {e}")
            raise

    async def _create_indexes(self):
        """Create MongoDB indexes for optimal performance"""
        try:
            # Exact match indexes
            await asyncio.get_event_loop().run_in_executor(
                None, self.collection.create_index, 'ssn_hash'
            )
            await asyncio.get_event_loop().run_in_executor(
                None, self.collection.create_index, 'internal_mpi_id'
            )

            # Fuzzy match indexes
            await asyncio.get_event_loop().run_in_executor(
                None, self.collection.create_index,
                [('last_name_soundex', 1), ('first_name_soundex', 1), ('dob', 1)]
            )

            # Performance indexes
            await asyncio.get_event_loop().run_in_executor(
                None, self.collection.create_index, 'created_at'
            )
            await asyncio.get_event_loop().run_in_executor(
                None, self.collection.create_index, 'confidence_score'
            )

        except Exception as e:
            logger.warning(f"Could not create indexes: {e}")

    async def get_mpi_id(self, patient_data: Dict[str, Any]) -> MPIResult:
        """
        Get MPI ID using internal matching algorithms

        Matching strategy:
        1. Check cache first
        2. Try exact SSN match
        3. Try fuzzy name + DOB matching
        4. Generate new internal MPI ID if no match
        """
        self.total_queries += 1
        start_time = datetime.utcnow()

        try:
            # Validate and standardize input
            self._validate_patient_data(patient_data)
            standardized_data = self._standardize_patient_data(patient_data)

            # Check cache first
            if self.config.cache_enabled:
                cached_result = await self._get_cached_result(standardized_data)
                if cached_result:
                    return cached_result

            # Try exact matches first (fastest)
            exact_match = await self._exact_match(standardized_data)
            if exact_match:
                self.exact_matches += 1
                result = MPIResult(
                    mpi_id=exact_match['internal_mpi_id'],
                    confidence=exact_match.get('confidence_score', 1.0),
                    provider='internal',
                    source='exact_match',
                    metadata={
                        'match_type': 'exact',
                        'matched_field': exact_match.get('matched_field', 'ssn'),
                        'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                    }
                )
                await self._cache_result(standardized_data, result)
                return result

            # Try fuzzy/probabilistic matching
            fuzzy_match = await self._fuzzy_match(standardized_data)
            if fuzzy_match and fuzzy_match['confidence'] >= self.config.confidence_threshold:
                self.fuzzy_matches += 1
                result = MPIResult(
                    mpi_id=fuzzy_match['internal_mpi_id'],
                    confidence=fuzzy_match['confidence'],
                    provider='internal',
                    source='fuzzy_match',
                    metadata={
                        'match_type': 'fuzzy',
                        'matched_fields': fuzzy_match.get('matched_fields', []),
                        'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                    }
                )
                await self._cache_result(standardized_data, result)
                return result

            # No match found - generate new internal MPI ID
            self.no_matches += 1
            new_mpi_id = self._generate_internal_mpi_id()

            # Store new patient record
            await self._store_new_patient(standardized_data, new_mpi_id)

            result = MPIResult(
                mpi_id=new_mpi_id,
                confidence=1.0,  # New patient, perfect confidence in new ID
                provider='internal',
                source='new_patient',
                metadata={
                    'match_type': 'new',
                    'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                }
            )

            await self._cache_result(standardized_data, result)
            return result

        except Exception as e:
            logger.error(f"Internal MPI matching error: {e}")
            return MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='internal',
                source='error',
                error=str(e),
                metadata={
                    'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                }
            )

    async def _get_cached_result(self, patient_data: Dict[str, Any]) -> Optional[MPIResult]:
        """Get result from cache if available"""
        try:
            cache_key = self._build_cache_key(patient_data)
            cached = await self.redis_client.get(cache_key)

            if cached:
                import json
                data = json.loads(cached)
                return MPIResult(**data)

        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")

        return None

    async def _cache_result(self, patient_data: Dict[str, Any], result: MPIResult):
        """Cache the result"""
        try:
            if not self.config.cache_enabled:
                return

            cache_key = self._build_cache_key(patient_data)
            import json

            # Convert result to dict for caching
            result_dict = result.to_dict()

            await self.redis_client.setex(
                cache_key,
                self.config.cache_ttl_seconds,
                json.dumps(result_dict)
            )

        except Exception as e:
            logger.warning(f"Cache storage error: {e}")

    def _build_cache_key(self, patient_data: Dict[str, Any]) -> str:
        """Build cache key from patient data"""
        key_fields = {
            'ssn': patient_data.get('ssn', ''),
            'first_name': patient_data.get('first_name', '').lower(),
            'last_name': patient_data.get('last_name', '').lower(),
            'dob': patient_data.get('dob', '')
        }

        import json
        key_string = json.dumps(key_fields, sort_keys=True)
        key_hash = hashlib.blake2b(key_string.encode(), digest_size=16).hexdigest()
        return f"internal_mpi:{key_hash}"

    async def _exact_match(self, patient_data: Dict[str, Any]) -> Optional[Dict]:
        """Try exact matching on key fields"""

        # SSN exact match (highest priority)
        ssn = patient_data.get('ssn')
        if ssn:
            ssn_hash = self._hash_ssn(ssn)
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.collection.find_one, {'ssn_hash': ssn_hash}
            )
            if result:
                result['matched_field'] = 'ssn'
                return result

        # Add other exact match strategies here if needed
        return None

    async def _fuzzy_match(self, patient_data: Dict[str, Any]) -> Optional[Dict]:
        """Fuzzy/probabilistic matching algorithm"""

        first_name = patient_data.get('first_name', '').strip()
        last_name = patient_data.get('last_name', '').strip()
        dob = patient_data.get('dob', '')

        if not (first_name and last_name):
            return None

        # Search for potential matches using soundex
        last_soundex = self._soundex(last_name)
        first_soundex = self._soundex(first_name)

        # Find candidates
        query = {'last_name_soundex': last_soundex}
        if dob:
            # Allow slight DOB variations (common data entry errors)
            query['dob'] = {'$in': self._get_dob_variations(dob)}

        candidates = await asyncio.get_event_loop().run_in_executor(
            None, lambda: list(self.collection.find(query).limit(100))
        )

        best_match = None
        best_score = 0.0
        best_matched_fields = []

        for candidate in candidates:
            score, matched_fields = self._calculate_match_score(patient_data, candidate)

            if score > best_score and score >= self.config.fuzzy_threshold:
                best_score = score
                best_match = candidate
                best_matched_fields = matched_fields

        if best_match:
            # Convert score to confidence (0-1 range)
            confidence = min(best_score / 100.0, 1.0)

            return {
                'internal_mpi_id': best_match['internal_mpi_id'],
                'confidence': confidence,
                'matched_fields': best_matched_fields
            }

        return None

    def _calculate_match_score(self, patient_data: Dict, candidate: Dict) -> tuple:
        """Calculate weighted similarity score between patient data and candidate"""
        total_score = 0.0
        total_weight = 0.0
        matched_fields = []

        for field, weight in self.config.probabilistic_weights.items():
            patient_value = str(patient_data.get(field, '')).strip().lower()
            candidate_value = str(candidate.get(field, '')).strip().lower()

            if patient_value and candidate_value:
                if field in ['first_name', 'last_name']:
                    # Use fuzzy string matching for names
                    similarity = fuzz.ratio(patient_value, candidate_value)
                elif field == 'dob':
                    # Exact match for dates (already handled variations in query)
                    similarity = 100.0 if patient_value == candidate_value else 0.0
                elif field == 'ssn':
                    # Exact match for SSN
                    similarity = 100.0 if patient_value == candidate_value else 0.0
                else:
                    # Fuzzy match for other fields
                    similarity = fuzz.partial_ratio(patient_value, candidate_value)

                if similarity > 70:  # Only count reasonably good matches
                    total_score += similarity * weight
                    total_weight += weight
                    matched_fields.append(field)

        # Normalize score
        if total_weight > 0:
            final_score = total_score / total_weight
        else:
            final_score = 0.0

        return final_score, matched_fields

    def _generate_internal_mpi_id(self) -> str:
        """Generate a new internal MPI ID"""
        # Use prefix to distinguish from external provider IDs
        return f"INT-{uuid.uuid4().hex[:12].upper()}"

    async def _store_new_patient(self, patient_data: Dict[str, Any], mpi_id: str):
        """Store new patient record in database"""
        document = {
            'internal_mpi_id': mpi_id,
            'ssn_hash': self._hash_ssn(patient_data.get('ssn', '')),
            'first_name': patient_data.get('first_name', ''),
            'last_name': patient_data.get('last_name', ''),
            'first_name_soundex': self._soundex(patient_data.get('first_name', '')),
            'last_name_soundex': self._soundex(patient_data.get('last_name', '')),
            'dob': patient_data.get('dob', ''),
            'gender': patient_data.get('gender', ''),
            'address_1': patient_data.get('address_1', ''),
            'city': patient_data.get('city', ''),
            'state': patient_data.get('state', ''),
            'zip': patient_data.get('zip', ''),
            'home_phone': patient_data.get('home_phone', ''),
            'email': patient_data.get('email', ''),
            'confidence_score': 1.0,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self.collection.insert_one, document
            )
            logger.info(f"Stored new patient with Internal MPI ID: {mpi_id}")
        except Exception as e:
            logger.error(f"Failed to store new patient: {e}")

    def _hash_ssn(self, ssn: str) -> str:
        """Create a hash of SSN for storage"""
        if not ssn:
            return ''
        clean_ssn = ''.join(filter(str.isdigit, ssn))
        return hashlib.sha256(clean_ssn.encode()).hexdigest()[:16]

    def _soundex(self, word: str) -> str:
        """Simple Soundex implementation for phonetic matching"""
        if not word:
            return ''

        word = word.upper()
        soundex_map = {
            'BFPV': '1', 'CGJKQSXZ': '2', 'DT': '3', 'L': '4', 'MN': '5', 'R': '6'
        }

        # Keep first letter
        result = word[0]

        # Replace consonants with digits
        for char in word[1:]:
            for key, value in soundex_map.items():
                if char in key:
                    if result[-1] != value:  # Avoid consecutive duplicates
                        result += value
                    break
            else:
                if char in 'AEIOUY':
                    result += '0'

        # Remove zeros and pad/truncate to 4 characters
        result = result.replace('0', '')
        return (result + '000')[:4]

    def _get_dob_variations(self, dob: str) -> List[str]:
        """Get DOB variations to account for common data entry errors"""
        variations = [dob]

        try:
            # Parse date and create variations
            from datetime import datetime
            parsed_date = datetime.strptime(dob, '%Y-%m-%d')

            # Common format variations
            variations.extend([
                parsed_date.strftime('%m/%d/%Y'),
                parsed_date.strftime('%m-%d-%Y'),
                parsed_date.strftime('%Y/%m/%d'),
                parsed_date.strftime('%d/%m/%Y'),  # International format
            ])

            # Year variations (2-digit vs 4-digit years)
            variations.extend([
                parsed_date.strftime('%m/%d/%y'),
                parsed_date.strftime('%m-%d-%y'),
            ])

        except ValueError:
            # If parsing fails, just return original
            pass

        return list(set(variations))  # Remove duplicates

    async def batch_process(self, patient_records: List[Dict[str, Any]],
                          max_concurrent: int = 40) -> List[MPIResult]:
        """
        Optimized batch processing for internal provider
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_limit(patient_data):
            async with semaphore:
                return await self.get_mpi_id(patient_data)

        tasks = [process_with_limit(patient) for patient in patient_records]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch processing error for record {i}: {result}")
                processed_results.append(MPIResult(
                    mpi_id=None,
                    confidence=0.0,
                    provider='internal',
                    source='batch_error',
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        return processed_results

    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics"""
        base_stats = super().get_stats()

        # Calculate success rate
        success_rate = 0.0
        if self.total_queries > 0:
            success_rate = (self.exact_matches + self.fuzzy_matches) / self.total_queries

        internal_stats = {
            'total_queries': self.total_queries,
            'exact_matches': self.exact_matches,
            'fuzzy_matches': self.fuzzy_matches,
            'no_matches': self.no_matches,
            'success_rate': success_rate,
            'cache_enabled': self.config.cache_enabled,
            'fuzzy_threshold': self.config.fuzzy_threshold,
            'ml_matching_enabled': self.config.enable_ml_matching
        }

        base_stats.update(internal_stats)
        return base_stats

    async def cleanup(self) -> None:
        """Cleanup resources"""
        if self.redis_client and not self.mpi_service:
            # Only close if we own the connection
            await self.redis_client.close()

        if self.mongo_client and not self.mpi_service:
            # Only close if we own the connection
            self.mongo_client.close()

        await super().cleanup()
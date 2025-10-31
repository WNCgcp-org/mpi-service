"""
Matching service - business logic for patient matching
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from uuid import uuid4
import time
import asyncio
import logging

from ..models.matching import (
    MatchResult,
    BulkMatchResult,
    BulkMatchResponse,
    PatientWithCorrelationId
)
from ..repositories.matching_repository import MatchingRepository


logger = logging.getLogger(__name__)


class MatchingService:
    """Service layer for matching operations"""

    def __init__(self, repository: MatchingRepository, mpi_service):
        self.repository = repository
        self.mpi_service = mpi_service
        self.memory_cache = {}  # L1 cache

    async def match_single_patient(
        self,
        patient_data: Dict[str, Any]
    ) -> MatchResult:
        """Match a single patient and return MPI ID"""
        start_time = time.perf_counter()
        cache_hit = False

        try:
            # Generate cache key
            cache_key = self.repository.generate_cache_key(patient_data)

            # L1: Memory cache
            if cache_key in self.memory_cache:
                cache_hit = True
                result = self.memory_cache[cache_key]
            else:
                # L2/L3: Redis/MongoDB cache
                cached = await self.repository.get_cached_match(cache_key)
                if cached:
                    cache_hit = True
                    result = cached
                    # Populate L1 cache
                    self.memory_cache[cache_key] = cached
                else:
                    # Call provider
                    result = await self._call_provider(patient_data)

                    # Cache result
                    if result and not result.get("error"):
                        await self.repository.set_cache(cache_key, result)
                        self.memory_cache[cache_key] = result

            # Record metrics
            processing_time = (time.perf_counter() - start_time) * 1000
            await self.repository.record_metric(
                "/mpi/match",
                processing_time,
                cache_hit,
                "success" if not result.get("error") else "error"
            )

            return MatchResult(
                mpi_id=result.get("mpi_id"),
                confidence=result.get("confidence"),
                provider=result.get("provider"),
                source=result.get("source"),
                error=result.get("error"),
                processing_time_ms=processing_time
            )

        except Exception as e:
            logger.error(f"Error matching patient: {e}")
            processing_time = (time.perf_counter() - start_time) * 1000

            await self.repository.record_metric(
                "/mpi/match",
                processing_time,
                False,
                "error"
            )

            return MatchResult(
                error=str(e),
                processing_time_ms=processing_time
            )

    async def bulk_match_patients(
        self,
        patients: List[PatientWithCorrelationId],
        return_phi: bool = False
    ) -> BulkMatchResponse:
        """Process bulk patient matching with correlation IDs"""
        start_time = time.perf_counter()
        request_id = str(uuid4())

        logger.info(f"Bulk match request {request_id} with {len(patients)} records")

        results = []
        successful = 0
        failed = 0

        # Process in optimized batches
        batch_size = 100  # Configurable based on provider capacity

        for i in range(0, len(patients), batch_size):
            batch = patients[i:i + batch_size]

            # Process batch concurrently
            batch_tasks = []
            for patient_record in batch:
                batch_tasks.append(
                    self._process_single_with_correlation(
                        patient_record.correlation_id,
                        patient_record.patient_data
                    )
                )

            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Collect results
            for result in batch_results:
                if isinstance(result, Exception):
                    failed += 1
                    results.append(BulkMatchResult(
                        correlation_id="unknown",
                        status="error",
                        error_message=str(result)
                    ))
                else:
                    if result.status == "success":
                        successful += 1
                    else:
                        failed += 1
                    results.append(result)

        total_time = (time.perf_counter() - start_time) * 1000

        # Record bulk operation metric
        await self.repository.record_metric(
            "/mpi/bulk-match",
            total_time,
            False,
            "success" if failed == 0 else "partial"
        )

        return BulkMatchResponse(
            request_id=request_id,
            total_records=len(patients),
            successful=successful,
            failed=failed,
            results=results,
            total_processing_time_ms=total_time
        )

    async def _process_single_with_correlation(
        self,
        correlation_id: str,
        patient_data: Dict[str, Any]
    ) -> BulkMatchResult:
        """Process a single patient with correlation ID"""
        start_time = time.perf_counter()

        try:
            # Match patient
            result = await self.match_single_patient(patient_data)

            processing_time = (time.perf_counter() - start_time) * 1000

            if result.mpi_id:
                return BulkMatchResult(
                    correlation_id=correlation_id,
                    mpi_id=result.mpi_id,
                    confidence=result.confidence,
                    status="success",
                    processing_time_ms=processing_time
                )
            elif result.error:
                return BulkMatchResult(
                    correlation_id=correlation_id,
                    status="error",
                    error_message=result.error,
                    processing_time_ms=processing_time
                )
            else:
                return BulkMatchResult(
                    correlation_id=correlation_id,
                    status="no_match",
                    processing_time_ms=processing_time
                )

        except Exception as e:
            logger.error(f"Error processing patient {correlation_id}: {e}")
            return BulkMatchResult(
                correlation_id=correlation_id,
                status="error",
                error_message=str(e),
                processing_time_ms=(time.perf_counter() - start_time) * 1000
            )

    async def _call_provider(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """Call the configured provider for matching"""
        try:
            # Use the configured provider
            if hasattr(self.mpi_service.provider, 'get_mpi_id'):
                result = await self.mpi_service.provider.get_mpi_id(patient_data)

                # Handle different response formats
                if hasattr(result, 'to_dict'):
                    return result.to_dict()
                elif hasattr(result, 'dict'):
                    return result.dict()
                else:
                    return result
            else:
                # Fallback to direct MPI service call
                return await self.mpi_service.get_mpi_id(patient_data)

        except Exception as e:
            logger.error(f"Provider call failed: {e}")
            return {"error": str(e)}

    async def get_streaming_results(
        self,
        patients: List[PatientWithCorrelationId]
    ):
        """Generate streaming results for large datasets"""
        request_id = str(uuid4())

        yield {"type": "start", "request_id": request_id}

        for patient_record in patients:
            result = await self._process_single_with_correlation(
                patient_record.correlation_id,
                patient_record.patient_data
            )
            yield {"type": "result", "result": result.dict()}

        yield {"type": "complete", "request_id": request_id}

    def clear_memory_cache(self):
        """Clear the in-memory cache"""
        self.memory_cache.clear()
        logger.info("Memory cache cleared")
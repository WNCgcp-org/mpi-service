"""
Hybrid MPI Provider

Combines multiple MPI providers (Verato + Internal) for optimal matching.
Provides fallback capability and consensus-based matching.
"""

import os
import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from .base_provider import BaseMPIProvider, MPIResult, ProviderConfig
from .verato import VeratoModule
from .internal import InternalMPIProvider, InternalProviderConfig

logger = logging.getLogger(__name__)


class HybridStrategy(Enum):
    """Hybrid matching strategies"""
    VERATO_FIRST = "verato_first"      # Try Verato first, fallback to internal
    INTERNAL_FIRST = "internal_first"  # Try internal first, fallback to Verato
    PARALLEL = "parallel"              # Run both in parallel, use consensus
    CONSENSUS = "consensus"            # Require agreement between providers
    BEST_CONFIDENCE = "best_confidence"  # Use result with highest confidence


@dataclass
class HybridProviderConfig(ProviderConfig):
    """Configuration for Hybrid MPI Provider"""

    # Strategy configuration
    strategy: HybridStrategy = HybridStrategy.VERATO_FIRST
    require_consensus: bool = False
    consensus_threshold: float = 0.1  # Maximum confidence difference for consensus

    # Provider configurations
    verato_config: Dict[str, Any] = None
    internal_config: InternalProviderConfig = None

    # Fallback settings
    enable_fallback: bool = True
    fallback_on_low_confidence: bool = True
    fallback_confidence_threshold: float = 0.7

    # Performance settings
    parallel_timeout_seconds: int = 10
    enable_cross_validation: bool = True

    def __post_init__(self):
        super().__post_init__()

        if self.verato_config is None:
            self.verato_config = {}

        if self.internal_config is None:
            self.internal_config = InternalProviderConfig()


class HybridMPIProvider(BaseMPIProvider):
    """
    Hybrid MPI Provider that combines multiple providers

    Features:
    - Multiple matching strategies (fallback, parallel, consensus)
    - Cross-validation between providers
    - Intelligent provider selection based on data quality
    - Performance optimization with configurable timeouts
    """

    def __init__(self, config: HybridProviderConfig = None, mpi_service=None):
        super().__init__(config or HybridProviderConfig())
        self.config: HybridProviderConfig = self.config
        self.mpi_service = mpi_service

        # Provider instances
        self.verato_provider = None
        self.internal_provider = None

        # Statistics
        self.verato_calls = 0
        self.internal_calls = 0
        self.consensus_matches = 0
        self.disagreements = 0
        self.fallback_used = 0

    async def initialize(self) -> None:
        """Initialize both provider instances"""
        try:
            # Initialize Verato provider
            self.verato_provider = VeratoModule()

            # Initialize Internal provider
            self.internal_provider = InternalMPIProvider(
                config=self.config.internal_config,
                mpi_service=self.mpi_service
            )
            await self.internal_provider.initialize()

            self._initialized = True
            logger.info(f"Hybrid MPI Provider initialized with strategy: {self.config.strategy.value}")

        except Exception as e:
            logger.error(f"Failed to initialize Hybrid MPI Provider: {e}")
            raise

    async def get_mpi_id(self, patient_data: Dict[str, Any]) -> MPIResult:
        """
        Get MPI ID using hybrid strategy
        """
        try:
            # Validate and standardize input
            self._validate_patient_data(patient_data)
            standardized_data = self._standardize_patient_data(patient_data)

            # Select strategy
            if self.config.strategy == HybridStrategy.VERATO_FIRST:
                return await self._verato_first_strategy(standardized_data)
            elif self.config.strategy == HybridStrategy.INTERNAL_FIRST:
                return await self._internal_first_strategy(standardized_data)
            elif self.config.strategy == HybridStrategy.PARALLEL:
                return await self._parallel_strategy(standardized_data)
            elif self.config.strategy == HybridStrategy.CONSENSUS:
                return await self._consensus_strategy(standardized_data)
            elif self.config.strategy == HybridStrategy.BEST_CONFIDENCE:
                return await self._best_confidence_strategy(standardized_data)
            else:
                raise ValueError(f"Unknown hybrid strategy: {self.config.strategy}")

        except Exception as e:
            logger.error(f"Hybrid MPI matching error: {e}")
            return MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='hybrid',
                source='error',
                error=str(e)
            )

    async def _verato_first_strategy(self, patient_data: Dict[str, Any]) -> MPIResult:
        """Try Verato first, fallback to internal if needed"""
        start_time = datetime.utcnow()

        # Try Verato first
        verato_result = await self._call_verato(patient_data)
        self.verato_calls += 1

        # Check if Verato result is acceptable
        if (verato_result.mpi_id and
            verato_result.confidence >= self.config.confidence_threshold):

            # Optionally cross-validate with internal
            if self.config.enable_cross_validation:
                internal_result = await self._call_internal(patient_data)
                self.internal_calls += 1

                if self._validate_cross_results(verato_result, internal_result):
                    self.consensus_matches += 1
                else:
                    self.disagreements += 1

            verato_result.metadata.update({
                'strategy': 'verato_first',
                'primary_provider': 'verato',
                'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
            })
            return verato_result

        # Fallback to internal if enabled
        if self.config.enable_fallback:
            self.fallback_used += 1
            internal_result = await self._call_internal(patient_data)
            self.internal_calls += 1

            internal_result.metadata.update({
                'strategy': 'verato_first_fallback',
                'primary_provider': 'verato',
                'fallback_provider': 'internal',
                'fallback_reason': 'low_confidence' if verato_result.mpi_id else 'no_match',
                'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
            })
            return internal_result

        # Return Verato result even if low confidence
        verato_result.metadata.update({
            'strategy': 'verato_first_no_fallback',
            'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
        })
        return verato_result

    async def _internal_first_strategy(self, patient_data: Dict[str, Any]) -> MPIResult:
        """Try internal first, fallback to Verato if needed"""
        start_time = datetime.utcnow()

        # Try internal first
        internal_result = await self._call_internal(patient_data)
        self.internal_calls += 1

        # Check if internal result is acceptable
        if (internal_result.mpi_id and
            internal_result.confidence >= self.config.confidence_threshold):

            # Optionally cross-validate with Verato
            if self.config.enable_cross_validation:
                verato_result = await self._call_verato(patient_data)
                self.verato_calls += 1

                if self._validate_cross_results(internal_result, verato_result):
                    self.consensus_matches += 1
                else:
                    self.disagreements += 1

            internal_result.metadata.update({
                'strategy': 'internal_first',
                'primary_provider': 'internal',
                'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
            })
            return internal_result

        # Fallback to Verato if enabled
        if self.config.enable_fallback:
            self.fallback_used += 1
            verato_result = await self._call_verato(patient_data)
            self.verato_calls += 1

            verato_result.metadata.update({
                'strategy': 'internal_first_fallback',
                'primary_provider': 'internal',
                'fallback_provider': 'verato',
                'fallback_reason': 'low_confidence' if internal_result.mpi_id else 'no_match',
                'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
            })
            return verato_result

        # Return internal result even if low confidence
        internal_result.metadata.update({
            'strategy': 'internal_first_no_fallback',
            'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
        })
        return internal_result

    async def _parallel_strategy(self, patient_data: Dict[str, Any]) -> MPIResult:
        """Run both providers in parallel and choose best result"""
        start_time = datetime.utcnow()

        try:
            # Run both providers concurrently with timeout
            verato_task = asyncio.create_task(self._call_verato(patient_data))
            internal_task = asyncio.create_task(self._call_internal(patient_data))

            # Wait for both with timeout
            done, pending = await asyncio.wait(
                [verato_task, internal_task],
                timeout=self.config.parallel_timeout_seconds,
                return_when=asyncio.ALL_COMPLETED
            )

            # Cancel any pending tasks
            for task in pending:
                task.cancel()

            # Get results
            verato_result = None
            internal_result = None

            if verato_task in done:
                verato_result = await verato_task
                self.verato_calls += 1

            if internal_task in done:
                internal_result = await internal_task
                self.internal_calls += 1

            # Choose best result
            best_result = self._choose_best_result(verato_result, internal_result)

            if best_result:
                best_result.metadata.update({
                    'strategy': 'parallel',
                    'providers_called': [p for p in ['verato', 'internal']
                                       if p in [r.provider if r else None
                                              for r in [verato_result, internal_result]]],
                    'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                })
                return best_result

            # No good results
            return MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='hybrid',
                source='parallel_no_results',
                metadata={
                    'strategy': 'parallel',
                    'timeout_occurred': len(pending) > 0,
                    'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                }
            )

        except Exception as e:
            logger.error(f"Parallel strategy error: {e}")
            return MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='hybrid',
                source='parallel_error',
                error=str(e),
                metadata={
                    'strategy': 'parallel',
                    'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                }
            )

    async def _consensus_strategy(self, patient_data: Dict[str, Any]) -> MPIResult:
        """Require consensus between providers"""
        start_time = datetime.utcnow()

        # Run both providers
        verato_result = await self._call_verato(patient_data)
        internal_result = await self._call_internal(patient_data)

        self.verato_calls += 1
        self.internal_calls += 1

        # Check for consensus
        if self._check_consensus(verato_result, internal_result):
            self.consensus_matches += 1

            # Use the result with higher confidence
            best_result = verato_result if verato_result.confidence >= internal_result.confidence else internal_result

            best_result.metadata.update({
                'strategy': 'consensus',
                'consensus_achieved': True,
                'both_providers_agree': True,
                'verato_confidence': verato_result.confidence,
                'internal_confidence': internal_result.confidence,
                'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
            })
            return best_result
        else:
            self.disagreements += 1

            # No consensus - return disagreement result
            return MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='hybrid',
                source='consensus_failed',
                metadata={
                    'strategy': 'consensus',
                    'consensus_achieved': False,
                    'verato_mpi_id': verato_result.mpi_id,
                    'internal_mpi_id': internal_result.mpi_id,
                    'verato_confidence': verato_result.confidence,
                    'internal_confidence': internal_result.confidence,
                    'confidence_difference': abs(verato_result.confidence - internal_result.confidence),
                    'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                }
            )

    async def _best_confidence_strategy(self, patient_data: Dict[str, Any]) -> MPIResult:
        """Run both and return result with highest confidence"""
        start_time = datetime.utcnow()

        # Run both providers in parallel
        verato_result = await self._call_verato(patient_data)
        internal_result = await self._call_internal(patient_data)

        self.verato_calls += 1
        self.internal_calls += 1

        # Choose result with highest confidence
        if verato_result.confidence >= internal_result.confidence:
            best_result = verato_result
            other_confidence = internal_result.confidence
        else:
            best_result = internal_result
            other_confidence = verato_result.confidence

        best_result.metadata.update({
            'strategy': 'best_confidence',
            'chosen_provider': best_result.provider,
            'chosen_confidence': best_result.confidence,
            'other_confidence': other_confidence,
            'confidence_difference': abs(verato_result.confidence - internal_result.confidence),
            'processing_time_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
        })

        return best_result

    async def _call_verato(self, patient_data: Dict[str, Any]) -> MPIResult:
        """Call Verato provider with error handling"""
        try:
            # Convert to old format for compatibility
            old_result = await self.verato_provider.get_mpi_id(patient_data)

            return MPIResult(
                mpi_id=old_result.get('verato_id'),
                confidence=old_result.get('confidence', 0.0),
                provider='verato',
                source=old_result.get('source', 'api'),
                metadata=old_result.get('metadata', {}),
                error=old_result.get('error')
            )
        except Exception as e:
            logger.error(f"Verato provider error: {e}")
            return MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='verato',
                source='error',
                error=str(e)
            )

    async def _call_internal(self, patient_data: Dict[str, Any]) -> MPIResult:
        """Call internal provider with error handling"""
        try:
            return await self.internal_provider.get_mpi_id(patient_data)
        except Exception as e:
            logger.error(f"Internal provider error: {e}")
            return MPIResult(
                mpi_id=None,
                confidence=0.0,
                provider='internal',
                source='error',
                error=str(e)
            )

    def _choose_best_result(self, verato_result: Optional[MPIResult],
                           internal_result: Optional[MPIResult]) -> Optional[MPIResult]:
        """Choose the best result from available results"""

        # Filter out error results
        valid_results = [r for r in [verato_result, internal_result]
                        if r and r.mpi_id and not r.error]

        if not valid_results:
            return None

        # Return result with highest confidence
        return max(valid_results, key=lambda x: x.confidence)

    def _check_consensus(self, result1: MPIResult, result2: MPIResult) -> bool:
        """Check if two results represent consensus"""

        # Both must have MPI IDs
        if not (result1.mpi_id and result2.mpi_id):
            return False

        # MPI IDs must match OR confidence difference must be within threshold
        if result1.mpi_id == result2.mpi_id:
            return True

        # Check confidence difference (both should be high confidence)
        confidence_diff = abs(result1.confidence - result2.confidence)
        return (confidence_diff <= self.config.consensus_threshold and
                min(result1.confidence, result2.confidence) >= self.config.confidence_threshold)

    def _validate_cross_results(self, primary: MPIResult, secondary: MPIResult) -> bool:
        """Validate that cross-validation results agree"""

        if not (primary.mpi_id and secondary.mpi_id):
            return True  # No conflict if one has no result

        # Check if they agree on the MPI ID or are within acceptable confidence range
        return (primary.mpi_id == secondary.mpi_id or
                abs(primary.confidence - secondary.confidence) <= self.config.consensus_threshold)

    async def batch_process(self, patient_records: List[Dict[str, Any]],
                          max_concurrent: int = 40) -> List[MPIResult]:
        """Optimized batch processing for hybrid provider"""

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
                logger.error(f"Hybrid batch processing error for record {i}: {result}")
                processed_results.append(MPIResult(
                    mpi_id=None,
                    confidence=0.0,
                    provider='hybrid',
                    source='batch_error',
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        return processed_results

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive hybrid provider statistics"""
        base_stats = super().get_stats()

        total_calls = self.verato_calls + self.internal_calls
        consensus_rate = self.consensus_matches / max(self.verato_calls, 1)
        disagreement_rate = self.disagreements / max(self.verato_calls, 1)
        fallback_rate = self.fallback_used / max(total_calls, 1)

        hybrid_stats = {
            'strategy': self.config.strategy.value,
            'total_calls': total_calls,
            'verato_calls': self.verato_calls,
            'internal_calls': self.internal_calls,
            'consensus_matches': self.consensus_matches,
            'disagreements': self.disagreements,
            'fallback_used': self.fallback_used,
            'consensus_rate': consensus_rate,
            'disagreement_rate': disagreement_rate,
            'fallback_rate': fallback_rate,
            'cross_validation_enabled': self.config.enable_cross_validation,
            'parallel_timeout': self.config.parallel_timeout_seconds
        }

        # Include sub-provider stats
        if self.verato_provider:
            hybrid_stats['verato_stats'] = getattr(self.verato_provider, 'get_stats', lambda: {})()

        if self.internal_provider:
            hybrid_stats['internal_stats'] = self.internal_provider.get_stats()

        base_stats.update(hybrid_stats)
        return base_stats

    async def health_check(self) -> Dict[str, Any]:
        """Check health of both providers"""
        health_status = {
            'status': 'healthy',
            'provider': 'hybrid',
            'strategy': self.config.strategy.value,
            'providers': {}
        }

        # Check Verato provider
        try:
            if self.verato_provider:
                # Test with minimal data
                test_result = await self._call_verato({
                    'first_name': 'TEST',
                    'last_name': 'PATIENT',
                    'dob': '2000-01-01'
                })
                health_status['providers']['verato'] = {
                    'status': 'healthy' if not test_result.error else 'unhealthy',
                    'error': test_result.error
                }
            else:
                health_status['providers']['verato'] = {
                    'status': 'not_initialized'
                }
        except Exception as e:
            health_status['providers']['verato'] = {
                'status': 'unhealthy',
                'error': str(e)
            }

        # Check Internal provider
        try:
            if self.internal_provider:
                internal_health = await self.internal_provider.health_check()
                health_status['providers']['internal'] = internal_health
            else:
                health_status['providers']['internal'] = {
                    'status': 'not_initialized'
                }
        except Exception as e:
            health_status['providers']['internal'] = {
                'status': 'unhealthy',
                'error': str(e)
            }

        # Overall status
        provider_statuses = [p.get('status') for p in health_status['providers'].values()]
        if 'unhealthy' in provider_statuses:
            health_status['status'] = 'degraded'
        elif 'not_initialized' in provider_statuses:
            health_status['status'] = 'partial'

        return health_status

    async def cleanup(self) -> None:
        """Cleanup all provider resources"""
        if self.internal_provider:
            await self.internal_provider.cleanup()

        # Verato provider doesn't have async cleanup
        if self.verato_provider:
            try:
                if hasattr(self.verato_provider, 'mongo_client'):
                    self.verato_provider.mongo_client.close()
                if hasattr(self.verato_provider, 'redis_client'):
                    self.verato_provider.redis_client.close()
            except Exception as e:
                logger.warning(f"Error cleaning up Verato provider: {e}")

        await super().cleanup()
"""
Matching controller - HTTP endpoint handlers for matching operations
"""

from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
import json
import logging

from ..models.matching import (
    PatientMatchRequest,
    BulkMatchRequest,
    MatchResult,
    BulkMatchResponse
)
from ..services.matching_service import MatchingService
from ....core.dependencies import get_matching_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mpi", tags=["matching"])


@router.post("/match", response_model=MatchResult)
async def match_patient(
    request: PatientMatchRequest,
    service: MatchingService = Depends(get_matching_service)
) -> MatchResult:
    """
    Match a single patient and return MPI ID

    This endpoint accepts patient demographic data and returns
    the assigned MPI ID along with confidence score.
    """
    try:
        result = await service.match_single_patient(request.patient_data)
        return result

    except Exception as e:
        logger.error(f"Error in single match: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-match", response_model=BulkMatchResponse)
async def bulk_match(
    request: BulkMatchRequest,
    service: MatchingService = Depends(get_matching_service)
) -> BulkMatchResponse:
    """
    Bulk patient matching with correlation IDs

    This endpoint:
    1. Accepts patients with correlation IDs
    2. Processes them in parallel batches
    3. Returns only MPI IDs and correlation IDs (no PHI)
    4. Maintains audit trail internally
    """
    try:
        response = await service.bulk_match_patients(
            request.patients,
            request.return_phi
        )
        return response

    except Exception as e:
        logger.error(f"Error in bulk match: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-match-stream")
async def bulk_match_streaming(
    request: BulkMatchRequest,
    service: MatchingService = Depends(get_matching_service)
):
    """
    Streaming version of bulk match for very large datasets

    Returns results as they're processed using Server-Sent Events.
    Ideal for processing thousands of records without timeout issues.
    """
    async def generate():
        try:
            async for result in service.get_streaming_results(request.patients):
                yield f"data: {json.dumps(result)}\n\n"
        except Exception as e:
            logger.error(f"Error in streaming match: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/cache/stats")
async def get_cache_statistics(
    service: MatchingService = Depends(get_matching_service)
) -> Dict[str, Any]:
    """
    Get cache statistics and performance metrics

    Returns hit rates and performance data for the last 24 hours.
    """
    try:
        metrics = await service.repository.get_metrics_summary(hours=24)

        return {
            "metrics": metrics,
            "memory_cache_size": len(service.memory_cache),
            "timestamp": datetime.utcnow()
        }

    except Exception as e:
        logger.error(f"Error fetching cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_cache(
    service: MatchingService = Depends(get_matching_service)
) -> Dict[str, str]:
    """
    Clear the in-memory cache

    Useful for testing or when cache invalidation is needed.
    """
    try:
        service.clear_memory_cache()
        return {"status": "Cache cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
"""
Patient controller - HTTP endpoint handlers
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Path, Depends
import logging

from ..models.patient import (
    PatientSearchRequest,
    PatientResponse,
    PatientHistory,
    PatientIdentifier
)
from ..services.patient_service import PatientService
from ....core.dependencies import get_patient_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


@router.get("/{mpi_id}", response_model=PatientResponse)
async def get_patient_by_mpi(
    mpi_id: str = Path(..., description="MPI ID"),
    service: PatientService = Depends(get_patient_service)
) -> PatientResponse:
    """
    Fetch a patient by MPI ID

    Returns patient information including confidence score and source.
    """
    try:
        patient = await service.get_patient_by_mpi(mpi_id)

        if not patient:
            raise HTTPException(status_code=404, detail=f"Patient {mpi_id} not found")

        return patient

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching patient {mpi_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=List[PatientResponse])
async def search_patients(
    search_request: PatientSearchRequest,
    limit: int = Query(default=10, le=100, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Skip records"),
    service: PatientService = Depends(get_patient_service)
) -> List[PatientResponse]:
    """
    Search for patients using various criteria

    Supports exact and fuzzy matching with configurable confidence thresholds.
    Returns a list of matching patients sorted by confidence score.
    """
    try:
        results = await service.search_patients(
            search_request,
            limit=limit,
            offset=offset
        )

        return results

    except Exception as e:
        logger.error(f"Error searching patients: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{mpi_id}/identifiers", response_model=List[PatientIdentifier])
async def get_patient_identifiers(
    mpi_id: str = Path(..., description="MPI ID"),
    system: Optional[str] = Query(None, description="Filter by system"),
    service: PatientService = Depends(get_patient_service)
) -> List[PatientIdentifier]:
    """
    Get all identifiers for a patient

    Returns all known identifiers (MRN, SSN, Insurance ID, etc.)
    optionally filtered by system.
    """
    try:
        identifiers = await service.get_patient_identifiers(mpi_id, system)

        if not identifiers:
            raise HTTPException(
                status_code=404,
                detail=f"No identifiers found for patient {mpi_id}"
            )

        return identifiers

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching identifiers for {mpi_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{mpi_id}/history", response_model=List[PatientHistory])
async def get_patient_history(
    mpi_id: str = Path(..., description="MPI ID"),
    days: int = Query(default=30, description="Days of history"),
    service: PatientService = Depends(get_patient_service)
) -> List[PatientHistory]:
    """
    Get patient history and audit trail

    Returns a chronological list of all changes and actions
    performed on this patient record.
    """
    try:
        history = await service.get_patient_history(mpi_id, days)

        return history

    except Exception as e:
        logger.error(f"Error fetching history for {mpi_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{mpi_id}/links")
async def get_patient_links(
    mpi_id: str = Path(..., description="MPI ID"),
    service: PatientService = Depends(get_patient_service)
):
    """
    Get all linked patient records

    Returns information about merged records, duplicate candidates,
    and family member links.
    """
    try:
        links = await service.get_patient_links(mpi_id)

        return links

    except Exception as e:
        logger.error(f"Error fetching links for {mpi_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{mpi_id}/verify")
async def verify_patient(
    mpi_id: str = Path(..., description="MPI ID"),
    service: PatientService = Depends(get_patient_service)
):
    """
    Verify/re-verify a patient's information

    Triggers re-validation of patient data and updates confidence scores.
    """
    try:
        result = await service.verify_patient(mpi_id)

        if not result["verified"]:
            raise HTTPException(
                status_code=404,
                detail=result.get("error", "Verification failed")
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying patient {mpi_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
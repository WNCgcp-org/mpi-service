"""
Patient service - business logic layer
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import fuzzy

from ..models.patient import (
    PatientSearchRequest,
    PatientResponse,
    PatientHistory,
    PatientIdentifier,
    PatientEntity
)
from ..repositories.patient_repository import PatientRepository


logger = logging.getLogger(__name__)


class PatientService:
    """Service layer for patient operations"""

    def __init__(self, repository: PatientRepository, cache_service=None):
        self.repository = repository
        self.cache = cache_service
        self.soundex = fuzzy.Soundex(4)

    async def get_patient_by_mpi(self, mpi_id: str) -> Optional[PatientResponse]:
        """Fetch patient by MPI ID"""
        # Try cache first
        if self.cache:
            cached = await self.cache.get(f"patient:{mpi_id}")
            if cached:
                return PatientResponse(**cached)

        # Get from repository
        patient = await self.repository.find_by_mpi_id(mpi_id)

        if patient:
            response = PatientResponse(
                mpi_id=patient.mpi_id,
                confidence=patient.confidence,
                source=patient.source,
                created_at=patient.created_at,
                updated_at=patient.updated_at
            )

            # Cache result
            if self.cache:
                await self.cache.set(
                    f"patient:{mpi_id}",
                    response.dict(),
                    ttl=3600
                )

            return response

        return None

    async def search_patients(
        self,
        request: PatientSearchRequest,
        limit: int = 10,
        offset: int = 0
    ) -> List[PatientResponse]:
        """Search for patients with various criteria"""
        # Build search parameters
        search_params = {}

        if request.ssn:
            search_params["ssn_hash"] = PatientRepository.hash_ssn(request.ssn)

        if request.fuzzy_match:
            if request.first_name:
                search_params["first_name_soundex"] = self.soundex(request.first_name)
            if request.last_name:
                search_params["last_name_soundex"] = self.soundex(request.last_name)

        if request.dob:
            search_params["dob"] = request.dob

        # Search repository
        patients = await self.repository.search(
            search_params,
            fuzzy=request.fuzzy_match,
            limit=limit,
            offset=offset
        )

        # Filter by confidence threshold and convert to response
        results = []
        for patient in patients:
            if patient.confidence >= request.confidence_threshold:
                results.append(PatientResponse(
                    mpi_id=patient.mpi_id,
                    confidence=patient.confidence,
                    source=patient.source,
                    created_at=patient.created_at,
                    updated_at=patient.updated_at
                ))

        # Sort by confidence
        results.sort(key=lambda x: x.confidence or 0, reverse=True)

        return results

    async def get_patient_identifiers(
        self,
        mpi_id: str,
        system: Optional[str] = None
    ) -> List[PatientIdentifier]:
        """Get all identifiers for a patient"""
        identifiers = await self.repository.get_identifiers(mpi_id, system)

        return [
            PatientIdentifier(
                system=id["system"],
                value=id["value"]
            )
            for id in identifiers
        ]

    async def get_patient_history(
        self,
        mpi_id: str,
        days: int = 30
    ) -> List[PatientHistory]:
        """Get patient history and audit trail"""
        history = await self.repository.get_history(mpi_id, days)

        return [
            PatientHistory(
                timestamp=entry["timestamp"],
                action=entry["action"],
                user=entry.get("user")
            )
            for entry in history
        ]

    async def get_patient_links(self, mpi_id: str) -> Dict[str, Any]:
        """Get all linked patient records"""
        return await self.repository.get_links(mpi_id)

    async def verify_patient(self, mpi_id: str) -> Dict[str, Any]:
        """Verify/re-verify patient information"""
        patient = await self.repository.find_by_mpi_id(mpi_id)

        if not patient:
            return {
                "mpi_id": mpi_id,
                "verified": False,
                "error": "Patient not found"
            }

        # Update last verified timestamp
        await self.repository.update(
            mpi_id,
            {"last_verified": datetime.utcnow()}
        )

        return {
            "mpi_id": mpi_id,
            "verified": True,
            "timestamp": datetime.utcnow(),
            "confidence": patient.confidence
        }

    async def create_or_match_patient(
        self,
        patient_data: Dict[str, Any]
    ) -> PatientResponse:
        """Create new patient or return existing match"""
        # Check for existing match
        if patient_data.get("ssn"):
            ssn_hash = PatientRepository.hash_ssn(patient_data["ssn"])
            existing = await self.repository.find_by_ssn_hash(ssn_hash)

            if existing:
                return PatientResponse(
                    mpi_id=existing.mpi_id,
                    confidence=existing.confidence,
                    source=existing.source
                )

        # Create new patient
        import uuid

        match_keys = {
            "first_name_soundex": self.soundex(patient_data.get("first_name", "")),
            "last_name_soundex": self.soundex(patient_data.get("last_name", "")),
            "dob": patient_data.get("dob", ""),
            "ssn_last4": patient_data.get("ssn", "")[-4:] if patient_data.get("ssn") else ""
        }

        patient = PatientEntity(
            mpi_id=f"MPI-{uuid.uuid4().hex[:8].upper()}",
            ssn_hash=PatientRepository.hash_ssn(patient_data.get("ssn", "")),
            match_keys=match_keys,
            confidence=0.95,
            source="internal",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_accessed=datetime.utcnow()
        )

        await self.repository.create(patient)

        return PatientResponse(
            mpi_id=patient.mpi_id,
            confidence=patient.confidence,
            source=patient.source,
            created_at=patient.created_at
        )
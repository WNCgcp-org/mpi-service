"""
Patient repository - handles data persistence
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging
import hashlib

from ..models.patient import PatientEntity
from core.database import BaseRepository, DatabaseManager
from core.cache import CacheManager, cache_patient_data, get_cached_patient_data, invalidate_patient_cache


logger = logging.getLogger(__name__)


class PatientRepository(BaseRepository):
    """Repository for patient data persistence"""

    def __init__(self, db_manager: DatabaseManager, cache_manager: Optional[CacheManager] = None):
        super().__init__(db_manager, "mpi_identifiers")
        self.cache_manager = cache_manager

        # Get collections using the database manager
        self.mappings_collection = db_manager.get_collection("identifier_mappings")
        self.audit_collection = db_manager.get_collection("patient_audit")
        self.links_collection = db_manager.get_collection("patient_links")


    async def find_by_mpi_id(self, mpi_id: str) -> Optional[PatientEntity]:
        """Find patient by MPI ID"""
        # Try cache first if available
        if self.cache_manager:
            cached_data = await get_cached_patient_data(mpi_id)
            if cached_data:
                return self._doc_to_entity(cached_data)

        doc = await self.find_one({"mpi_id": mpi_id})

        if doc:
            # Update last accessed
            await self.update_one(
                {"mpi_id": mpi_id},
                {"$set": {"last_accessed": datetime.utcnow()}}
            )

            # Cache the result if cache manager is available
            if self.cache_manager:
                await cache_patient_data(mpi_id, doc)

            return self._doc_to_entity(doc)

        return None

    async def find_by_ssn_hash(self, ssn_hash: str) -> Optional[PatientEntity]:
        """Find patient by SSN hash"""
        doc = await self.find_one({"ssn_hash": ssn_hash})
        return self._doc_to_entity(doc) if doc else None

    async def search(
        self,
        search_params: Dict[str, Any],
        fuzzy: bool = True,
        limit: int = 10,
        offset: int = 0
    ) -> List[PatientEntity]:
        """Search for patients with various criteria"""
        query = {}

        # Build search query
        if search_params.get("ssn_hash"):
            query["ssn_hash"] = search_params["ssn_hash"]

        if fuzzy and search_params.get("last_name_soundex"):
            query["match_keys.last_name_soundex"] = search_params["last_name_soundex"]
            if search_params.get("first_name_soundex"):
                query["match_keys.first_name_soundex"] = search_params["first_name_soundex"]

        if search_params.get("dob"):
            query["match_keys.dob"] = search_params["dob"]

        # Execute search using BaseRepository method
        docs = await self.find_many(
            query,
            skip=offset,
            limit=limit
        )

        return [self._doc_to_entity(doc) for doc in docs]

    async def create(self, patient: PatientEntity) -> str:
        """Create new patient record"""
        doc = patient.to_dict()
        result_id = await self.insert_one(doc)

        # Audit log
        await self._audit_log(
            patient.mpi_id,
            "created",
            {"source": patient.source}
        )

        # Cache the new patient data
        if self.cache_manager:
            await cache_patient_data(patient.mpi_id, doc)

        return result_id

    async def update(self, mpi_id: str, updates: Dict[str, Any]) -> bool:
        """Update patient record"""
        success = await self.update_one(
            {"mpi_id": mpi_id},
            {"$set": updates}
        )

        if success:
            await self._audit_log(
                mpi_id,
                "updated",
                {"fields": list(updates.keys())}
            )

            # Invalidate cache
            if self.cache_manager:
                await invalidate_patient_cache(mpi_id)

            return True

        return False

    async def get_identifiers(self, mpi_id: str, system: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all identifiers for a patient"""
        query = {"mpi_id": mpi_id}
        if system:
            query["external_system"] = system

        docs = await self.mappings_collection.find(query).to_list(length=None)
        identifiers = []

        for doc in docs:
            identifiers.append({
                "system": doc["external_system"],
                "value": doc["external_id"],
                "created_at": doc.get("created_at")
            })

        return identifiers

    async def add_identifier_mapping(
        self,
        mpi_id: str,
        external_id: str,
        external_system: str
    ) -> bool:
        """Add external identifier mapping"""
        try:
            await self.mappings_collection.insert_one({
                "mpi_id": mpi_id,
                "external_id": external_id,
                "external_system": external_system,
                "created_at": datetime.utcnow()
            })

            await self._audit_log(
                mpi_id,
                "identifier_added",
                {"system": external_system, "id": external_id}
            )

            return True
        except Exception as e:
            logger.error(f"Error adding identifier mapping: {e}")
            return False

    async def get_history(
        self,
        mpi_id: str,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get patient history/audit trail"""
        start_date = datetime.utcnow() - timedelta(days=days)

        docs = await self.audit_collection.find({
            "mpi_id": mpi_id,
            "timestamp": {"$gte": start_date}
        }).sort("timestamp", -1).limit(limit).to_list(length=limit)

        history = []
        for entry in docs:
            history.append({
                "timestamp": entry["timestamp"],
                "action": entry["action"],
                "details": entry.get("details", {}),
                "user": entry.get("user")
            })

        return history

    async def get_links(self, mpi_id: str) -> Dict[str, List[Any]]:
        """Get all linked patient records"""
        links = {
            "merged_from": [],
            "potential_duplicates": [],
            "family_members": []
        }

        # Find merged records
        merged = await self.links_collection.find({
            "survivor_id": mpi_id,
            "type": "merge"
        }).to_list(None)

        links["merged_from"] = [l["retired_id"] for l in merged]

        # Find potential duplicates
        duplicates = await self.links_collection.find({
            "$or": [{"mpi_id_1": mpi_id}, {"mpi_id_2": mpi_id}],
            "type": "potential_duplicate",
            "resolved": False
        }).to_list(None)

        for dup in duplicates:
            other_id = dup["mpi_id_1"] if dup["mpi_id_2"] == mpi_id else dup["mpi_id_2"]
            links["potential_duplicates"].append({
                "mpi_id": other_id,
                "confidence": dup.get("confidence", 0),
                "detected_date": dup.get("created_at")
            })

        return links

    async def _audit_log(self, mpi_id: str, action: str, details: Dict[str, Any]):
        """Create audit log entry"""
        await self.audit_collection.insert_one({
            "mpi_id": mpi_id,
            "action": action,
            "timestamp": datetime.utcnow(),
            "details": details
        })

    def _doc_to_entity(self, doc: Dict[str, Any]) -> PatientEntity:
        """Convert MongoDB document to entity"""
        return PatientEntity(
            mpi_id=doc["mpi_id"],
            ssn_hash=doc.get("ssn_hash", ""),
            match_keys=doc.get("match_keys", {}),
            confidence=doc.get("confidence", 0),
            source=doc.get("source", ""),
            created_at=doc.get("created_at", datetime.utcnow()),
            updated_at=doc.get("updated_at", datetime.utcnow()),
            last_accessed=doc.get("last_accessed", datetime.utcnow())
        )

    @staticmethod
    def hash_ssn(ssn: str) -> str:
        """Hash SSN for storage"""
        clean_ssn = ''.join(filter(str.isdigit, ssn))
        return hashlib.blake2b(clean_ssn.encode(), digest_size=16).hexdigest()
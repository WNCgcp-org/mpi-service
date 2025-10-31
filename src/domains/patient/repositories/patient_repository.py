"""
Patient repository - handles data persistence
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
import hashlib

from ..models.patient import PatientEntity


logger = logging.getLogger(__name__)


class PatientRepository:
    """Repository for patient data persistence"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["mpi_identifiers"]
        self.mappings_collection = db["identifier_mappings"]
        self.audit_collection = db["patient_audit"]
        self.links_collection = db["patient_links"]

    async def initialize(self):
        """Create indexes for optimal performance"""
        # Primary indexes
        await self.collection.create_index([("mpi_id", 1)], unique=True)
        await self.collection.create_index([("ssn_hash", 1)])
        await self.collection.create_index([("last_accessed", 1)])

        # Compound indexes for matching
        await self.collection.create_index([
            ("match_keys.ssn_last4", 1),
            ("match_keys.dob", 1)
        ])
        await self.collection.create_index([
            ("match_keys.last_name_soundex", 1),
            ("match_keys.first_name_soundex", 1),
            ("match_keys.dob", 1)
        ])

        # Mapping indexes
        await self.mappings_collection.create_index([
            ("external_id", 1),
            ("external_system", 1)
        ], unique=True)
        await self.mappings_collection.create_index([("mpi_id", 1)])

        # Audit index
        await self.audit_collection.create_index([("mpi_id", 1)])
        await self.audit_collection.create_index([("timestamp", -1)])

    async def find_by_mpi_id(self, mpi_id: str) -> Optional[PatientEntity]:
        """Find patient by MPI ID"""
        doc = await self.collection.find_one({"mpi_id": mpi_id})

        if doc:
            # Update last accessed
            await self.collection.update_one(
                {"mpi_id": mpi_id},
                {"$set": {"last_accessed": datetime.utcnow()}}
            )
            return self._doc_to_entity(doc)

        return None

    async def find_by_ssn_hash(self, ssn_hash: str) -> Optional[PatientEntity]:
        """Find patient by SSN hash"""
        doc = await self.collection.find_one({"ssn_hash": ssn_hash})
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

        # Execute search
        cursor = self.collection.find(query).skip(offset).limit(limit)
        results = []

        async for doc in cursor:
            results.append(self._doc_to_entity(doc))

        return results

    async def create(self, patient: PatientEntity) -> str:
        """Create new patient record"""
        doc = patient.to_dict()
        result = await self.collection.insert_one(doc)

        # Audit log
        await self._audit_log(
            patient.mpi_id,
            "created",
            {"source": patient.source}
        )

        return str(result.inserted_id)

    async def update(self, mpi_id: str, updates: Dict[str, Any]) -> bool:
        """Update patient record"""
        updates["updated_at"] = datetime.utcnow()

        result = await self.collection.update_one(
            {"mpi_id": mpi_id},
            {"$set": updates}
        )

        if result.modified_count > 0:
            await self._audit_log(
                mpi_id,
                "updated",
                {"fields": list(updates.keys())}
            )
            return True

        return False

    async def get_identifiers(self, mpi_id: str, system: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all identifiers for a patient"""
        query = {"mpi_id": mpi_id}
        if system:
            query["external_system"] = system

        cursor = self.mappings_collection.find(query)
        identifiers = []

        async for doc in cursor:
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

        cursor = self.audit_collection.find({
            "mpi_id": mpi_id,
            "timestamp": {"$gte": start_date}
        }).sort("timestamp", -1).limit(limit)

        history = []
        async for entry in cursor:
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
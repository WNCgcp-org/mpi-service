"""
Patient domain models
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from dataclasses import dataclass


class PatientIdentifier(BaseModel):
    """Patient identifier model"""
    system: str = Field(..., description="Identifier system (e.g., SSN, MRN, Insurance)")
    value: str = Field(..., description="Identifier value")
    type: Optional[str] = Field(None, description="Identifier type")
    issuer: Optional[str] = Field(None, description="Issuing organization")


class PatientSearchRequest(BaseModel):
    """Search request parameters"""
    ssn: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[str] = None
    mrn: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    fuzzy_match: bool = Field(default=True, description="Enable fuzzy matching")
    confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class PatientResponse(BaseModel):
    """Patient response model"""
    mpi_id: str
    confidence: Optional[float] = None
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_verified: Optional[datetime] = None


class PatientHistory(BaseModel):
    """Patient history entry"""
    timestamp: datetime
    action: str
    changed_fields: Optional[List[str]] = None
    previous_values: Optional[Dict[str, Any]] = None
    user: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class PatientEntity:
    """Internal patient entity for repository"""
    mpi_id: str
    ssn_hash: str
    match_keys: Dict[str, str]
    confidence: float
    source: str
    created_at: datetime
    updated_at: datetime
    last_accessed: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mpi_id": self.mpi_id,
            "ssn_hash": self.ssn_hash,
            "match_keys": self.match_keys,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed": self.last_accessed
        }
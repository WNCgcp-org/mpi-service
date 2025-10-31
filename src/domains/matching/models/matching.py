"""
Matching domain models
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class PatientMatchRequest(BaseModel):
    """Single patient match request"""
    patient_data: Dict[str, Any] = Field(..., description="Patient demographic data")


class PatientWithCorrelationId(BaseModel):
    """Patient data with correlation ID for tracking"""
    correlation_id: str = Field(..., description="Unique ID to correlate request/response")
    patient_data: Dict[str, Any] = Field(..., description="Patient demographic data")


class BulkMatchRequest(BaseModel):
    """Bulk match request with correlation IDs"""
    patients: List[PatientWithCorrelationId] = Field(
        ...,
        description="List of patients with correlation IDs",
        min_items=1,
        max_items=10000
    )
    return_phi: bool = Field(
        default=False,
        description="Whether to return PHI in response (default: False for security)"
    )


class MatchResult(BaseModel):
    """Single match result"""
    mpi_id: Optional[str] = None
    confidence: Optional[float] = None
    provider: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None


class BulkMatchResult(BaseModel):
    """Single match result with correlation ID"""
    correlation_id: str = Field(..., description="Correlation ID from request")
    mpi_id: Optional[str] = Field(None, description="Assigned MPI ID")
    confidence: Optional[float] = Field(None, description="Match confidence score")
    status: str = Field(..., description="Success, error, or no_match")
    error_message: Optional[str] = Field(None, description="Error details if failed")
    processing_time_ms: Optional[float] = Field(None, description="Processing time")


class BulkMatchResponse(BaseModel):
    """Bulk match response with correlation IDs only"""
    request_id: str = Field(..., description="Unique request ID for tracking")
    total_records: int = Field(..., description="Total records processed")
    successful: int = Field(..., description="Successfully matched records")
    failed: int = Field(..., description="Failed records")
    results: List[BulkMatchResult] = Field(..., description="Individual results")
    total_processing_time_ms: float = Field(..., description="Total processing time")
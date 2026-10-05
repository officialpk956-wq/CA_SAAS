from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import ConfigDict

class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class ClientResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class RegistrationCreate(BaseModel):
    gstin: str
    legal_name: Optional[str] = None

class RegistrationResponse(BaseModel):
    id: UUID
    gstin: str
    legal_name: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class PeriodCreate(BaseModel):
    period_code: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

class PeriodResponse(BaseModel):
    id: UUID
    period_code: str
    status: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ImportBatchResponse(BaseModel):
    commit_note: Optional[str] = None
    id: UUID
    source_type: str
    status: str
    record_count: int
    invalid_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
        
class ReconciliationRunCreate(BaseModel):
    purchase_batch_id: UUID
    statement_batch_id: UUID

class ReconciliationResultResponse(BaseModel):
    id: UUID
    result_id: str
    status: str
    reason: str
    purchase_record_ids: Optional[List[str]] = None
    statement_record_ids: Optional[List[str]] = None
    differences: Dict[str, str] = Field(default_factory=dict)
    purchase_records: List[Dict[str, Any]] = Field(default_factory=list)
    statement_records: List[Dict[str, Any]] = Field(default_factory=list)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    review_status: str = "unresolved"  # computed from ExceptionResolution

    model_config = ConfigDict(from_attributes=True)

class ReconciliationRunResponse(BaseModel):
    purchase_batch_id: UUID
    statement_batch_id: UUID
    id: UUID
    status: str
    error_message: Optional[str] = None
    summary_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ResolutionCreate(BaseModel):
    decision: str
    note: str = Field(min_length=1, max_length=4000)

class ResolutionResponse(BaseModel):
    id: UUID
    result_id: str
    decision: str
    note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

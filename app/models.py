"""Pydantic request and response schemas."""
from typing import Optional

from pydantic import BaseModel


class VisitRequest(BaseModel):
    patient_id: str
    symptoms: str
    notes: Optional[str] = ""
    use_memory: bool = True  # toggle memory for with/without demo


class DispenseRequest(BaseModel):
    prescription_id: str


class ApproveRequest(BaseModel):
    prescription_id: str
    medicine_name: Optional[str] = None  # doctor may edit before approving
    dosage: Optional[str] = None         # doctor may edit before approving


class RejectRequest(BaseModel):
    prescription_id: str


class MedicineQuery(BaseModel):
    medicine_name: str

import uuid
from datetime import date
from pydantic import BaseModel, ConfigDict

class LeaveCreate(BaseModel):
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    reason: str | None = None

class LeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    status: str
    reason: str | None = None

class TypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    days_per_year: int

class BalanceOut(BaseModel):
    leave_type: str
    remaining_days: int

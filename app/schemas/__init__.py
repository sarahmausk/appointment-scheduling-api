from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import AppointmentStatus, UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: UserRole = UserRole.patient
    specialty: Optional[str] = None
    phone: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole


class DoctorCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    specialty: str
    bio: Optional[str] = None


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    specialty: str
    bio: Optional[str]
    user: UserOut


class SlotCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    starts_at: datetime
    ends_at: datetime
    is_booked: bool


class AppointmentCreate(BaseModel):
    slot_id: int
    notes: Optional[str] = None


class AppointmentReschedule(BaseModel):
    slot_id: int
    notes: Optional[str] = None


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    patient_id: int
    slot_id: int
    status: AppointmentStatus
    notes: Optional[str]
    created_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_user_id: Optional[int]
    entity_type: str
    entity_id: int
    action: str
    detail: Optional[str]
    created_at: datetime

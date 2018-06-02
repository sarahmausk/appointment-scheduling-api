from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import get_current_user, hash_password, require_roles
from app.models.user import (
    Appointment,
    AuditEntry,
    AvailabilitySlot,
    DoctorProfile,
    PatientProfile,
    User,
    UserRole,
)
from app.schemas import (
    AppointmentCreate,
    AppointmentOut,
    AppointmentReschedule,
    AuditOut,
    DoctorCreate,
    DoctorOut,
    SlotCreate,
    SlotOut,
    UserOut,
)
from app.services.appointments import book_appointment, cancel_appointment, reschedule_appointment
from app.services.audit import write_audit

doctors_router = APIRouter(prefix="/doctors", tags=["doctors"])
appointments_router = APIRouter(prefix="/appointments", tags=["appointments"])
audit_router = APIRouter(prefix="/audit", tags=["audit"])


@doctors_router.get("", response_model=list[DoctorOut])
def list_doctors(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(DoctorProfile).options(joinedload(DoctorProfile.user)).all()


@doctors_router.post("", response_model=DoctorOut, status_code=status.HTTP_201_CREATED)
def create_doctor(
    payload: DoctorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.doctor,
    )
    db.add(user)
    db.flush()
    doctor = DoctorProfile(user_id=user.id, specialty=payload.specialty, bio=payload.bio)
    db.add(doctor)
    db.flush()
    write_audit(db, actor_user_id=_.id, entity_type="doctor", entity_id=doctor.id, action="create")
    db.commit()
    return db.query(DoctorProfile).options(joinedload(DoctorProfile.user)).get(doctor.id)


@doctors_router.get("/{doctor_id}/availability", response_model=list[SlotOut])
def list_availability(
    doctor_id: int,
    only_open: bool = Query(True),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(AvailabilitySlot).filter(AvailabilitySlot.doctor_id == doctor_id)
    if only_open:
        q = q.filter(AvailabilitySlot.is_booked.is_(False))
        q = q.filter(AvailabilitySlot.starts_at > datetime.now(timezone.utc))
    return q.order_by(AvailabilitySlot.starts_at).all()


@doctors_router.post(
    "/{doctor_id}/availability",
    response_model=SlotOut,
    status_code=status.HTTP_201_CREATED,
)
def create_availability(
    doctor_id: int,
    payload: SlotCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.doctor)),
):
    doctor = db.get(DoctorProfile, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if user.role == UserRole.doctor and (not user.doctor_profile or user.doctor_profile.id != doctor_id):
        raise HTTPException(status_code=403, detail="Cannot manage another doctor's availability")
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")

    slot = AvailabilitySlot(
        doctor_id=doctor_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def _patient_profile(user: User, db: Session) -> PatientProfile:
    profile = user.patient_profile or db.query(PatientProfile).filter_by(user_id=user.id).first()
    if not profile:
        raise HTTPException(status_code=400, detail="Patient profile required")
    return profile


def _can_view_appointment(user: User, appt: Appointment) -> bool:
    if user.role == UserRole.admin:
        return True
    if user.role == UserRole.doctor and user.doctor_profile and user.doctor_profile.id == appt.doctor_id:
        return True
    if user.role == UserRole.patient and user.patient_profile and user.patient_profile.id == appt.patient_id:
        return True
    return False


@appointments_router.get("", response_model=list[AppointmentOut])
def list_appointments(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Appointment)
    if user.role == UserRole.patient:
        profile = _patient_profile(user, db)
        q = q.filter(Appointment.patient_id == profile.id)
    elif user.role == UserRole.doctor:
        if not user.doctor_profile:
            return []
        q = q.filter(Appointment.doctor_id == user.doctor_profile.id)
    return q.order_by(Appointment.created_at.desc()).all()


@appointments_router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.patient, UserRole.admin)),
):
    if user.role == UserRole.admin:
        raise HTTPException(status_code=400, detail="Admins cannot book as patients; use a patient account")
    patient = _patient_profile(user, db)
    return book_appointment(db, patient=patient, actor=user, slot_id=payload.slot_id, notes=payload.notes)


@appointments_router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    appt = db.get(Appointment, appointment_id)
    if not appt or not _can_view_appointment(user, appt):
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@appointments_router.patch("/{appointment_id}", response_model=AppointmentOut)
def patch_appointment(
    appointment_id: int,
    payload: AppointmentReschedule,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    appt = db.get(Appointment, appointment_id)
    if not appt or not _can_view_appointment(user, appt):
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == UserRole.doctor:
        raise HTTPException(status_code=403, detail="Doctors cannot reschedule patient bookings")
    if user.role == UserRole.patient and user.patient_profile.id != appt.patient_id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    return reschedule_appointment(
        db, appointment=appt, actor=user, new_slot_id=payload.slot_id, notes=payload.notes
    )


@appointments_router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(
    appointment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    appt = db.get(Appointment, appointment_id)
    if not appt or not _can_view_appointment(user, appt):
        raise HTTPException(status_code=404, detail="Appointment not found")
    if user.role == UserRole.patient and user.patient_profile.id != appt.patient_id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    return cancel_appointment(db, appointment=appt, actor=user)


@audit_router.get("", response_model=list[AuditOut])
def list_audit(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    return db.query(AuditEntry).order_by(AuditEntry.created_at.desc()).limit(200).all()

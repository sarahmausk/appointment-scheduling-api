from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import (
    Appointment,
    AppointmentStatus,
    AvailabilitySlot,
    PatientProfile,
    User,
)
from app.services.audit import write_audit


def _ensure_future(slot: AvailabilitySlot) -> None:
    now = datetime.now(timezone.utc)
    starts = slot.starts_at if slot.starts_at.tzinfo else slot.starts_at.replace(tzinfo=timezone.utc)
    if starts <= now:
        raise HTTPException(status_code=400, detail="Cannot book a past slot")


def book_appointment(
    db: Session,
    *,
    patient: PatientProfile,
    actor: User,
    slot_id: int,
    notes: str | None = None,
) -> Appointment:
    # SELECT FOR UPDATE serializes concurrent bookers on the same slot row
    slot = db.execute(
        select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id).with_for_update()
    ).scalar_one_or_none()
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.is_booked:
        raise HTTPException(status_code=409, detail="Slot already booked")
    _ensure_future(slot)

    appointment = Appointment(
        doctor_id=slot.doctor_id,
        patient_id=patient.id,
        slot_id=slot.id,
        status=AppointmentStatus.booked,
        notes=notes,
    )
    slot.is_booked = True
    db.add(appointment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Slot already booked") from exc

    write_audit(
        db,
        actor_user_id=actor.id,
        entity_type="appointment",
        entity_id=appointment.id,
        action="book",
        detail=f"slot={slot.id}",
    )
    db.commit()
    db.refresh(appointment)
    return appointment


def cancel_appointment(db: Session, *, appointment: Appointment, actor: User) -> Appointment:
    if appointment.status != AppointmentStatus.booked:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel appointment in status {appointment.status.value}",
        )
    appointment.status = AppointmentStatus.cancelled
    slot = db.get(AvailabilitySlot, appointment.slot_id)
    if slot:
        slot.is_booked = False
    write_audit(
        db,
        actor_user_id=actor.id,
        entity_type="appointment",
        entity_id=appointment.id,
        action="cancel",
    )
    db.commit()
    db.refresh(appointment)
    return appointment


def reschedule_appointment(
    db: Session,
    *,
    appointment: Appointment,
    actor: User,
    new_slot_id: int,
    notes: str | None = None,
) -> Appointment:
    if appointment.status != AppointmentStatus.booked:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reschedule appointment in status {appointment.status.value}",
        )

    old_slot = db.execute(
        select(AvailabilitySlot).where(AvailabilitySlot.id == appointment.slot_id).with_for_update()
    ).scalar_one()
    new_slot = db.execute(
        select(AvailabilitySlot).where(AvailabilitySlot.id == new_slot_id).with_for_update()
    ).scalar_one_or_none()
    if new_slot is None:
        raise HTTPException(status_code=404, detail="New slot not found")
    if new_slot.doctor_id != appointment.doctor_id:
        raise HTTPException(status_code=400, detail="New slot must belong to the same doctor")
    if new_slot.is_booked:
        raise HTTPException(status_code=409, detail="New slot already booked")
    _ensure_future(new_slot)

    old_slot.is_booked = False
    new_slot.is_booked = True
    appointment.slot_id = new_slot.id
    if notes is not None:
        appointment.notes = notes
    write_audit(
        db,
        actor_user_id=actor.id,
        entity_type="appointment",
        entity_id=appointment.id,
        action="reschedule",
        detail=f"from_slot={old_slot.id} to_slot={new_slot.id}",
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="New slot already booked") from exc
    db.refresh(appointment)
    return appointment

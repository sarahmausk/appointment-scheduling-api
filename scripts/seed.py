"""Seed demo users, doctor availability, and one sample appointment."""

from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import (
    Appointment,
    AppointmentStatus,
    AvailabilitySlot,
    DoctorProfile,
    PatientProfile,
    User,
    UserRole,
)


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "admin@clinic.test").first():
            print("Seed data already present — skipping")
            return

        admin = User(
            email="admin@clinic.test",
            hashed_password=hash_password("adminpass123"),
            full_name="Clinic Admin",
            role=UserRole.admin,
        )
        doctor_user = User(
            email="doctor@clinic.test",
            hashed_password=hash_password("doctorpass123"),
            full_name="Dr. Ada Lovelace",
            role=UserRole.doctor,
        )
        patient_user = User(
            email="patient@clinic.test",
            hashed_password=hash_password("patientpass123"),
            full_name="Alan Turing",
            role=UserRole.patient,
        )
        patient2 = User(
            email="patient2@clinic.test",
            hashed_password=hash_password("patientpass123"),
            full_name="Grace Hopper",
            role=UserRole.patient,
        )
        db.add_all([admin, doctor_user, patient_user, patient2])
        db.flush()

        doctor = DoctorProfile(user_id=doctor_user.id, specialty="General Practice", bio="Primary care")
        p1 = PatientProfile(user_id=patient_user.id, phone="+15550001")
        p2 = PatientProfile(user_id=patient2.id, phone="+15550002")
        db.add_all([doctor, p1, p2])
        db.flush()

        now = datetime.now(timezone.utc).replace(microsecond=0)
        slots = []
        for day in range(1, 6):
            start = now + timedelta(days=day, hours=9)
            end = start + timedelta(minutes=30)
            slots.append(AvailabilitySlot(doctor_id=doctor.id, starts_at=start, ends_at=end))
        db.add_all(slots)
        db.flush()

        slots[0].is_booked = True
        db.add(
            Appointment(
                doctor_id=doctor.id,
                patient_id=p1.id,
                slot_id=slots[0].id,
                status=AppointmentStatus.booked,
                notes="Annual checkup",
            )
        )
        db.commit()
        print("Seed complete")
        print("  admin@clinic.test / adminpass123")
        print("  doctor@clinic.test / doctorpass123")
        print("  patient@clinic.test / patientpass123")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

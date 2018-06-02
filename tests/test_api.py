import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@db:5432/appointments_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")

from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.user import AvailabilitySlot, DoctorProfile, PatientProfile, User, UserRole

TEST_DB = os.environ["DATABASE_URL"]


def _ensure_test_db():
    admin_url = TEST_DB.rsplit("/", 1)[0] + "/postgres"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'appointments_test'")
        ).scalar()
        if not exists:
            conn.execute(text("CREATE DATABASE appointments_test"))
    engine.dispose()


_ensure_test_db()
engine = create_engine(TEST_DB, poolclass=NullPool)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Mirror production partial unique index
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_appointment_booked_slot "
                "ON appointments (slot_id) WHERE status = 'booked'"
            )
        )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _create_user(db, email, password, role, specialty=None):
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=email.split("@")[0],
        role=role,
    )
    db.add(user)
    db.flush()
    if role == UserRole.doctor:
        db.add(DoctorProfile(user_id=user.id, specialty=specialty or "GP"))
    elif role == UserRole.patient:
        db.add(PatientProfile(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user


def _login(client, email, password):
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_patient_cannot_see_others_appointments(client, db):
    doctor_u = _create_user(db, "doc@t.test", "password123", UserRole.doctor)
    p1 = _create_user(db, "p1@t.test", "password123", UserRole.patient)
    p2 = _create_user(db, "p2@t.test", "password123", UserRole.patient)
    doctor = db.query(DoctorProfile).filter_by(user_id=doctor_u.id).one()
    start = datetime.now(timezone.utc) + timedelta(days=2)
    slot = AvailabilitySlot(
        doctor_id=doctor.id, starts_at=start, ends_at=start + timedelta(minutes=30)
    )
    db.add(slot)
    db.commit()

    t1 = _login(client, "p1@t.test", "password123")
    book = client.post(
        "/appointments",
        json={"slot_id": slot.id},
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert book.status_code == 201
    appt_id = book.json()["id"]

    t2 = _login(client, "p2@t.test", "password123")
    other = client.get(f"/appointments/{appt_id}", headers={"Authorization": f"Bearer {t2}"})
    assert other.status_code == 404

    listed = client.get("/appointments", headers={"Authorization": f"Bearer {t2}"})
    assert listed.status_code == 200
    assert listed.json() == []


def test_doctor_cannot_access_audit(client, db):
    _create_user(db, "doc@t.test", "password123", UserRole.doctor)
    token = _login(client, "doc@t.test", "password123")
    r = client.get("/audit", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_can_access_audit(client, db):
    _create_user(db, "admin@t.test", "password123", UserRole.admin)
    token = _login(client, "admin@t.test", "password123")
    r = client.get("/audit", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_cannot_book_past_slot(client, db):
    doctor_u = _create_user(db, "doc@t.test", "password123", UserRole.doctor)
    _create_user(db, "p1@t.test", "password123", UserRole.patient)
    doctor = db.query(DoctorProfile).filter_by(user_id=doctor_u.id).one()
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    slot = AvailabilitySlot(
        doctor_id=doctor.id, starts_at=start, ends_at=start + timedelta(minutes=30)
    )
    db.add(slot)
    db.commit()

    token = _login(client, "p1@t.test", "password123")
    r = client.post(
        "/appointments",
        json={"slot_id": slot.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "past" in r.json()["detail"].lower()


def test_cancel_invalid_transition(client, db):
    doctor_u = _create_user(db, "doc@t.test", "password123", UserRole.doctor)
    _create_user(db, "p1@t.test", "password123", UserRole.patient)
    doctor = db.query(DoctorProfile).filter_by(user_id=doctor_u.id).one()
    start = datetime.now(timezone.utc) + timedelta(days=1)
    slot = AvailabilitySlot(
        doctor_id=doctor.id, starts_at=start, ends_at=start + timedelta(minutes=30)
    )
    db.add(slot)
    db.commit()

    token = _login(client, "p1@t.test", "password123")
    book = client.post(
        "/appointments",
        json={"slot_id": slot.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    appt_id = book.json()["id"]
    assert client.post(
        f"/appointments/{appt_id}/cancel", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 200
    again = client.post(
        f"/appointments/{appt_id}/cancel", headers={"Authorization": f"Bearer {token}"}
    )
    assert again.status_code == 400


def test_concurrent_booking_one_winner(client, db):
    doctor_u = _create_user(db, "doc@t.test", "password123", UserRole.doctor)
    _create_user(db, "p1@t.test", "password123", UserRole.patient)
    _create_user(db, "p2@t.test", "password123", UserRole.patient)
    doctor = db.query(DoctorProfile).filter_by(user_id=doctor_u.id).one()
    start = datetime.now(timezone.utc) + timedelta(days=3)
    slot = AvailabilitySlot(
        doctor_id=doctor.id, starts_at=start, ends_at=start + timedelta(minutes=30)
    )
    db.add(slot)
    db.commit()
    slot_id = slot.id

    t1 = _login(client, "p1@t.test", "password123")
    t2 = _login(client, "p2@t.test", "password123")

    def book(token):
        # Each thread needs its own TestClient / connection for real concurrency
        with TestClient(app) as c:
            return c.post(
                "/appointments",
                json={"slot_id": slot_id},
                headers={"Authorization": f"Bearer {token}"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(as_completed([pool.submit(book, t1), pool.submit(book, t2)]))
        codes = sorted(f.result() for f in results)

    assert codes.count(201) == 1
    assert codes.count(409) == 1

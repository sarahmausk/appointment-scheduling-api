# Appointment Scheduling API

Clinic scheduling API with JWT roles (`admin`, `doctor`, `patient`). Booking uses row locks and a partial unique index so the same slot cannot be double-booked.

## Setup

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000 · Docs: http://localhost:8000/docs

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres URL |
| `SECRET_KEY` | JWT secret |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL (default 60) |

## API

| Method | Path |
|--------|------|
| POST | `/auth/register`, `/auth/login` |
| GET/POST | `/doctors`, `/doctors/{id}/availability` |
| GET/POST/PATCH | `/appointments` |
| POST | `/appointments/{id}/cancel` |
| GET | `/audit` (admin) |

## Tests

```bash
docker compose up -d db
docker compose run --rm -e DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/appointments_test -e SECRET_KEY=test-secret api pytest -q
```

## Seed

```bash
docker compose run --rm api python scripts/seed.py
```

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.routes import appointments_router, audit_router, doctors_router

app = FastAPI(
    title="Appointment Scheduling API",
    description="Clinic scheduling with JWT RBAC and concurrency-safe booking",
    version="1.0.0",
)

app.include_router(auth_router)
app.include_router(doctors_router)
app.include_router(appointments_router)
app.include_router(audit_router)


@app.get("/health")
def health():
    return {"status": "ok"}

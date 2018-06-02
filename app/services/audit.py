from sqlalchemy.orm import Session

from app.models.user import AuditEntry


def write_audit(
    db: Session,
    *,
    actor_user_id: int | None,
    entity_type: str,
    entity_id: int,
    action: str,
    detail: str | None = None,
) -> AuditEntry:
    entry = AuditEntry(
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        detail=detail,
    )
    db.add(entry)
    return entry

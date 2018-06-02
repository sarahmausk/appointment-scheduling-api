"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role = sa.Enum("admin", "doctor", "patient", name="user_role")
    appointment_status = sa.Enum(
        "booked", "cancelled", "completed", "rescheduled", name="appointment_status"
    )
    user_role.create(op.get_bind(), checkfirst=True)
    appointment_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "doctor_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True),
        sa.Column("specialty", sa.String(128), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
    )

    op.create_table(
        "patient_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True),
        sa.Column("phone", sa.String(32), nullable=True),
    )

    op.create_table(
        "availability_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor_profiles.id", ondelete="CASCADE")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_booked", sa.Boolean(), server_default=sa.text("false")),
        sa.UniqueConstraint("doctor_id", "starts_at", name="uq_doctor_slot_start"),
    )
    op.create_index("ix_availability_slots_doctor_id", "availability_slots", ["doctor_id"])
    op.create_index("ix_availability_slots_starts_at", "availability_slots", ["starts_at"])
    op.create_index("ix_availability_slots_is_booked", "availability_slots", ["is_booked"])

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctor_profiles.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patient_profiles.id"), nullable=False),
        sa.Column("slot_id", sa.Integer(), sa.ForeignKey("availability_slots.id"), nullable=False),
        sa.Column("status", appointment_status, nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_appointments_doctor_id", "appointments", ["doctor_id"])
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])
    op.create_index("ix_appointments_slot_id", "appointments", ["slot_id"])
    # Only one active (booked) appointment per slot — cancelled rows may share history
    op.execute(
        "CREATE UNIQUE INDEX uq_appointment_booked_slot ON appointments (slot_id) "
        "WHERE status = 'booked'"
    )

    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_entries_entity_id", "audit_entries", ["entity_id"])


def downgrade() -> None:
    op.drop_table("audit_entries")
    op.execute("DROP INDEX IF EXISTS uq_appointment_booked_slot")
    op.drop_table("appointments")
    op.drop_table("availability_slots")
    op.drop_table("patient_profiles")
    op.drop_table("doctor_profiles")
    op.drop_table("users")
    sa.Enum(name="appointment_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)

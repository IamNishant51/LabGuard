"""M3 audit log: audit_logs table for administrative audit events.

Revision ID: 0002_m3_audit_logs
Revises: 0001_m2_core (M2 core schema; never edited).
Reviewed by hand against models.AuditLog: table/column names, PK, FK
with SET NULL, and index names match the ORM metadata so that
`alembic check` reports no unexpected operations. No device columns
change in M3: the M2 devices table already carries the identity fields.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_m3_audit_logs"
down_revision = "0001_m2_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)
    op.create_index(
        "ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")

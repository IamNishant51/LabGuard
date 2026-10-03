"""M4 enrollment and heartbeat: agent_credentials, metrics, metric_volumes.

Revision ID: 0003_m4_enrollment_heartbeat
Revises: 0002_m3_audit_logs (never edited).
Reviewed by hand against models.AgentCredential/Metric/MetricVolume:
table/column names, PKs, FKs with CASCADE, unique token hash, and index
names match the ORM metadata so that `alembic check` reports no
unexpected operations.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_m4_enrollment_heartbeat"
down_revision = "0002_m3_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_agent_credentials_device_id", "agent_credentials", ["device_id"], unique=False
    )
    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cpu_percent", sa.Float(), nullable=False),
        sa.Column("memory_percent", sa.Float(), nullable=False),
        sa.Column("memory_used_bytes", sa.BigInteger(), nullable=True),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_percent", sa.Float(), nullable=True),
        sa.Column("disk_used_bytes", sa.BigInteger(), nullable=True),
        sa.Column("disk_total_bytes", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "cpu_percent >= 0 AND cpu_percent <= 100", name="ck_metrics_cpu_range"
        ),
        sa.CheckConstraint(
            "memory_percent >= 0 AND memory_percent <= 100",
            name="ck_metrics_memory_range",
        ),
        sa.CheckConstraint(
            "disk_percent IS NULL OR (disk_percent >= 0 AND disk_percent <= 100)",
            name="ck_metrics_disk_range",
        ),
        sa.CheckConstraint(
            "memory_used_bytes IS NULL OR memory_used_bytes >= 0",
            name="ck_metrics_memory_used_nonneg",
        ),
        sa.CheckConstraint(
            "memory_total_bytes IS NULL OR memory_total_bytes >= 0",
            name="ck_metrics_memory_total_nonneg",
        ),
        sa.CheckConstraint(
            "disk_used_bytes IS NULL OR disk_used_bytes >= 0",
            name="ck_metrics_disk_used_nonneg",
        ),
        sa.CheckConstraint(
            "disk_total_bytes IS NULL OR disk_total_bytes >= 0",
            name="ck_metrics_disk_total_nonneg",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_metrics_device_recorded", "metrics", ["device_id", "recorded_at"], unique=False
    )
    op.create_table(
        "metric_volumes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("disk_percent", sa.Float(), nullable=False),
        sa.Column("used_bytes", sa.BigInteger(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "disk_percent >= 0 AND disk_percent <= 100",
            name="ck_metric_volumes_disk_range",
        ),
        sa.CheckConstraint("used_bytes >= 0", name="ck_metric_volumes_used_nonneg"),
        sa.CheckConstraint("total_bytes >= 0", name="ck_metric_volumes_total_nonneg"),
        sa.ForeignKeyConstraint(["metric_id"], ["metrics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metric_volumes_metric_id", "metric_volumes", ["metric_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_metric_volumes_metric_id", table_name="metric_volumes")
    op.drop_table("metric_volumes")
    op.drop_index("ix_metrics_device_recorded", table_name="metrics")
    op.drop_table("metrics")
    op.drop_index("ix_agent_credentials_device_id", table_name="agent_credentials")
    op.drop_table("agent_credentials")

"""Migration tests: 0001 builds the M2 schema, 0002 adds M3 audit logs,
0003 adds M4 enrollment credentials and heartbeat metrics."""

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_initial_migration_creates_m2_tables(tmp_path) -> None:
    db_file = tmp_path / "migrate-test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
    try:
        cfg = Config(os.path.join(API_DIR, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))
        command.upgrade(cfg, "head")
        try:
            tables = set(inspect(create_engine(f"sqlite:///{db_file}")).get_table_names())
            assert {"users", "labs", "lab_memberships", "devices", "user_sessions"} <= tables
            assert "alembic_version" in tables
        finally:
            command.downgrade(cfg, "base")
    finally:
        del os.environ["DATABASE_URL"]


def _tables(db_file: object) -> set[str]:
    return set(inspect(create_engine(f"sqlite:///{db_file}")).get_table_names())


def test_m3_migration_adds_reversible_audit_logs(tmp_path) -> None:
    db_file = tmp_path / "migrate-m3-test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
    try:
        cfg = Config(os.path.join(API_DIR, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))
        command.upgrade(cfg, "head")
        try:
            assert "audit_logs" in _tables(db_file)
            columns = {
                c["name"]
                for c in inspect(create_engine(f"sqlite:///{db_file}")).get_columns("audit_logs")
            }
            assert columns == {
                "id", "actor_user_id", "action", "entity_type",
                "entity_id", "metadata", "created_at",
            }
            command.downgrade(cfg, "0001_m2_core")
            tables = _tables(db_file)
            assert "audit_logs" not in tables
            assert {"users", "labs", "lab_memberships", "devices", "user_sessions"} <= tables
            command.upgrade(cfg, "head")
            assert "audit_logs" in _tables(db_file)
        finally:
            command.downgrade(cfg, "base")
    finally:
        del os.environ["DATABASE_URL"]


def test_m4_migration_adds_reversible_enrollment_tables(tmp_path) -> None:
    db_file = tmp_path / "migrate-m4-test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_file}"
    try:
        cfg = Config(os.path.join(API_DIR, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(API_DIR, "alembic"))
        command.upgrade(cfg, "head")
        try:
            engine = create_engine(f"sqlite:///{db_file}")
            tables = set(inspect(engine).get_table_names())
            assert {"agent_credentials", "metrics", "metric_volumes"} <= tables
            assert {
                c["name"] for c in inspect(engine).get_columns("agent_credentials")
            } == {
                "id", "device_id", "token_hash", "created_at",
                "expires_at", "revoked_at", "last_used_at",
            }
            assert {
                c["name"] for c in inspect(engine).get_columns("metrics")
            } == {
                "id", "device_id", "recorded_at", "agent_timestamp", "cpu_percent",
                "memory_percent", "memory_used_bytes", "memory_total_bytes",
                "disk_percent", "disk_used_bytes", "disk_total_bytes",
            }
            command.downgrade(cfg, "0002_m3_audit_logs")
            tables = _tables(db_file)
            assert not {"agent_credentials", "metrics", "metric_volumes"} & tables
            assert {"users", "labs", "lab_memberships", "devices", "user_sessions",
                    "audit_logs"} <= tables
            command.upgrade(cfg, "head")
            assert {"agent_credentials", "metrics", "metric_volumes"} <= _tables(db_file)
        finally:
            command.downgrade(cfg, "base")
    finally:
        del os.environ["DATABASE_URL"]

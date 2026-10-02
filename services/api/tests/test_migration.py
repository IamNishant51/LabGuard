"""Migration test: 0001 upgrades a fresh database to the M2 schema."""

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

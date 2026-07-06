"""initial schema

Creates the full ORCHESTRA schema: enum types, tables, indexes, updated_at
triggers and Row Level Security policies. The upgrade applies the canonical
``schema.sql`` (which is the single source of truth and is kept in sync with
``orchestra/database/models.py``); the downgrade tears everything back down.

Revision ID: 001_initial_schema
Revises:
Create Date: 2024-01-01 00:00:00
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Path to the canonical schema (….../orchestra/database/schema.sql).
_SCHEMA_SQL = Path(__file__).resolve().parents[2] / "schema.sql"

# Tables in reverse dependency order for a clean teardown.
_TABLES = [
    "model_cache",
    "whatsapp_sessions",
    "learning_data",
    "communication_logs",
    "escalations",
    "tasks",
    "project_stages",
    "teams",
    "projects",
    "workflows",
    "companies",
]

# Enum types created by schema.sql.
_ENUMS = [
    "webhook_status",
    "message_direction",
    "escalation_status",
    "escalation_priority",
    "task_status",
    "stage_status",
    "project_status",
]


def upgrade() -> None:
    """Apply the full schema from ``schema.sql``."""

    sql = _SCHEMA_SQL.read_text(encoding="utf-8")
    op.execute(sql)


def downgrade() -> None:
    """Drop every object created by :func:`upgrade`."""

    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS current_company_id() CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE;")
    for enum_name in _ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum_name} CASCADE;")

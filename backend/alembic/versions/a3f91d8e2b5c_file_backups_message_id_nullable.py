"""Make file_backups.message_id nullable

Revision ID: a3f91d8e2b5c
Revises: c1b78449f80c
Create Date: 2026-08-20

The initial migration created file_backups.message_id as NOT NULL, but the
SQLAlchemy model defines it as nullable=True. Subagents that call write_file
before they have an active_message_id (i.e. on their very first tool call)
were hitting:

    sqlite3.IntegrityError: NOT NULL constraint failed: file_backups.message_id

This migration aligns the DB schema with the model.
"""
from alembic import op
import sqlalchemy as sa


revision = "a3f91d8e2b5c"
down_revision = "c1b78449f80c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite does not support ALTER COLUMN directly.
    # We recreate the table with the corrected nullability.
    with op.batch_alter_table("file_backups") as batch_op:
        batch_op.alter_column(
            "message_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("file_backups") as batch_op:
        batch_op.alter_column(
            "message_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )

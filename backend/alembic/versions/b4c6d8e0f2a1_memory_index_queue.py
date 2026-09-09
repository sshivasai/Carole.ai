"""Durable retry queue for the derived memory index."""
from alembic import op
import sqlalchemy as sa

revision = "b4c6d8e0f2a1"
down_revision = "f3b8c2d1e4a5"
branch_labels = None
depends_on = None


def upgrade():
    # create_all bootstraps new installations before migration.
    if "memory_index_jobs" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table("memory_index_jobs",
                        sa.Column("id", sa.Uuid(), primary_key=True),
                        sa.Column("learning_id", sa.Uuid(), nullable=False),
                        sa.Column("attempts", sa.Integer(), nullable=False),
                        sa.Column("created_at", sa.DateTime(timezone=True)))
        op.create_index("ix_memory_index_jobs_learning_id", "memory_index_jobs", ["learning_id"])


def downgrade():
    op.drop_table("memory_index_jobs")

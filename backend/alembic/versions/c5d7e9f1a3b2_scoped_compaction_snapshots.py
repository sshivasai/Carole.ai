"""Persist complete, agent-scoped compaction snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "c5d7e9f1a3b2"
down_revision = "b4c6d8e0f2a1"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("compaction_events")}
    with op.batch_alter_table("compaction_events") as batch:
        if "owner_agent_id" not in columns:
            batch.add_column(sa.Column("owner_agent_id", sa.String(100)))
        if "snapshot" not in columns:
            batch.add_column(sa.Column("snapshot", sa.JSON()))


def downgrade():
    with op.batch_alter_table("compaction_events") as batch:
        batch.drop_column("snapshot")
        batch.drop_column("owner_agent_id")

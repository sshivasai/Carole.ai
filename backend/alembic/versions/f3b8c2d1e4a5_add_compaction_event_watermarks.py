"""Add covered_through watermarks to compaction_events

Revision ID: f3b8c2d1e4a5
Revises: e9a3f2b7c841
Create Date: 2026-09-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3b8c2d1e4a5'
down_revision: Union[str, None] = 'e9a3f2b7c841'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('compaction_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('covered_through_message_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('covered_through_timestamp', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('compaction_events', schema=None) as batch_op:
        batch_op.drop_column('covered_through_timestamp')
        batch_op.drop_column('covered_through_message_id')

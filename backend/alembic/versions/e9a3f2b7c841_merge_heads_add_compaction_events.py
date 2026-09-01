"""Merge dual heads and add compaction_events table

Revision ID: e9a3f2b7c841
Revises: a3f91d8e2b5c, c1371da95782
Create Date: 2026-08-27

This migration:
1. Merges the two divergent heads (a3f91d8e2b5c file_backups_nullable and c1371da95782 notifications)
2. Adds the compaction_events table for persistent context compaction checkpoints

The compaction_events table stores LLM-generated summaries that act as
conversation checkpoints. When an agent loads conversation history, it checks
for the most recent CompactionEvent and loads only messages AFTER that point,
using the stored summary as a synthetic first message. This makes rolling
compaction persist across server restarts.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e9a3f2b7c841'
down_revision: Union[str, Sequence[str]] = ('a3f91d8e2b5c', 'c1371da95782')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'compaction_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('team_id', sa.Uuid(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('message_count_before', sa.Integer(), nullable=True),
        sa.Column('triggered_by', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_compaction_events_team_id',
        'compaction_events',
        ['team_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_compaction_events_team_id', table_name='compaction_events')
    op.drop_table('compaction_events')

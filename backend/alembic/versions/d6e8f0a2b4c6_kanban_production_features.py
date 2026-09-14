"""Kanban production features: outbox, watchers, cursors, activities, preferences, metrics, revision.

Revision ID: d6e8f0a2b4c6
Revises: c5d7e9f1a3b2
Create Date: 2026-09-09 01:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6e8f0a2b4c6'
down_revision = 'c5d7e9f1a3b2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Add revision to tasks if not present
    if 'tasks' in existing_tables:
        task_cols = {col['name'] for col in inspector.get_columns('tasks')}
        if 'revision' not in task_cols:
            with op.batch_alter_table('tasks') as batch_op:
                batch_op.add_column(sa.Column('revision', sa.Integer(), nullable=False, server_default='1'))

    # 2. task_outbox_events
    if 'task_outbox_events' not in existing_tables:
        op.create_table(
            'task_outbox_events',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('event_id', sa.String(length=255), nullable=False),
            sa.Column('team_id', sa.Uuid(), nullable=False),
            sa.Column('task_id', sa.Uuid(), nullable=False),
            sa.Column('agent_id', sa.Uuid(), nullable=False),
            sa.Column('reason', sa.String(length=50), nullable=False),
            sa.Column('actor_id', sa.String(length=100), nullable=True),
            sa.Column('actor_name', sa.String(length=100), nullable=False, server_default='System'),
            sa.Column('comment', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
            sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('lease_timeout', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('event_id')
        )
        op.create_index('ix_task_outbox_status_lease', 'task_outbox_events', ['status', 'lease_timeout'])
        op.create_index('ix_task_outbox_event_id', 'task_outbox_events', ['event_id'])
        op.create_index('ix_task_outbox_team_id', 'task_outbox_events', ['team_id'])

    # 3. task_watchers
    if 'task_watchers' not in existing_tables:
        op.create_table(
            'task_watchers',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('task_id', sa.Uuid(), nullable=False),
            sa.Column('user_id', sa.String(length=100), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_task_watchers_task_user', 'task_watchers', ['task_id', 'user_id'], unique=True)

    # 4. task_read_cursors
    if 'task_read_cursors' not in existing_tables:
        op.create_table(
            'task_read_cursors',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('task_id', sa.Uuid(), nullable=False),
            sa.Column('user_id', sa.String(length=100), nullable=False),
            sa.Column('last_read_comment_id', sa.Uuid(), nullable=True),
            sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_task_read_cursors_task_user', 'task_read_cursors', ['task_id', 'user_id'], unique=True)

    # 5. task_activities
    if 'task_activities' not in existing_tables:
        op.create_table(
            'task_activities',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('task_id', sa.Uuid(), nullable=False),
            sa.Column('team_id', sa.Uuid(), nullable=False),
            sa.Column('actor_id', sa.String(length=100), nullable=False),
            sa.Column('actor_name', sa.String(length=100), nullable=False),
            sa.Column('activity_type', sa.String(length=50), nullable=False),
            sa.Column('old_value', sa.JSON(), nullable=True),
            sa.Column('new_value', sa.JSON(), nullable=True),
            sa.Column('details', sa.String(length=500), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_task_activities_task_created', 'task_activities', ['task_id', 'created_at'])
        op.create_index('ix_task_activities_team_created', 'task_activities', ['team_id', 'created_at'])

    # 6. agent_notification_preferences
    if 'agent_notification_preferences' not in existing_tables:
        op.create_table(
            'agent_notification_preferences',
            sa.Column('agent_id', sa.Uuid(), nullable=False),
            sa.Column('notify_on_assignment', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('notify_on_mention', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('notify_on_all_comments', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('muted_task_ids', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('agent_id')
        )

    # 7. task_metrics
    if 'task_metrics' not in existing_tables:
        op.create_table(
            'task_metrics',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('team_id', sa.Uuid(), nullable=False),
            sa.Column('task_id', sa.Uuid(), nullable=True),
            sa.Column('agent_id', sa.Uuid(), nullable=True),
            sa.Column('metric_type', sa.String(length=50), nullable=False),
            sa.Column('value', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('details', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_task_metrics_team_type', 'task_metrics', ['team_id', 'metric_type'])
        op.create_index('ix_task_metrics_task_id', 'task_metrics', ['task_id'])


def downgrade():
    op.drop_table('task_metrics')
    op.drop_table('agent_notification_preferences')
    op.drop_table('task_activities')
    op.drop_table('task_read_cursors')
    op.drop_table('task_watchers')
    op.drop_table('task_outbox_events')
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.drop_column('revision')

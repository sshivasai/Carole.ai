"""Request identity and provider-normalized accounting (nullable for old rows)."""
from alembic import op
import sqlalchemy as sa

revision = "e7f9a1b3c5d7"
down_revision = "d6e8f0a2b4c6"
branch_labels = None
depends_on = None


def upgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "context_checkpoint_heads" not in tables:
        op.create_table("context_checkpoint_heads", sa.Column("scope", sa.String(80), primary_key=True),
                        sa.Column("version", sa.Integer(), nullable=False))
    if "run_token_budgets" not in tables:
        op.create_table("run_token_budgets", sa.Column("id", sa.String(36), primary_key=True),
                        sa.Column("token_limit", sa.Integer(), nullable=False),
                        sa.Column("spent", sa.Integer(), nullable=False),
                        sa.Column("reserved", sa.Integer(), nullable=False),
                        sa.Column("created_at", sa.DateTime(timezone=True)))
    if "token_reservations" not in tables:
        op.create_table("token_reservations", sa.Column("id", sa.String(36), primary_key=True),
                        sa.Column("run_id", sa.String(36), sa.ForeignKey("run_token_budgets.id", ondelete="CASCADE"), nullable=False),
                        sa.Column("amount", sa.Integer(), nullable=False),
                        sa.Column("settled", sa.Boolean(), nullable=False))
        op.create_index("ix_token_reservations_run_id", "token_reservations", ["run_id"])
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("token_usage")}
    with op.batch_alter_table("token_usage") as batch:
        for name, typ in (("call_id", sa.String(36)), ("run_id", sa.String(36)),
                          ("purpose", sa.String(32)), ("accounting", sa.JSON())):
            if name not in existing:
                batch.add_column(sa.Column(name, typ, nullable=True))
        if "call_id" not in existing:
            batch.create_unique_constraint("uq_token_usage_call_id", ["call_id"])
        if "run_id" not in existing:
            batch.create_index("ix_token_usage_run_id", ["run_id"])


def downgrade():
    op.drop_table("context_checkpoint_heads")
    op.drop_table("token_reservations")
    op.drop_table("run_token_budgets")
    with op.batch_alter_table("token_usage") as batch:
        batch.drop_index("ix_token_usage_run_id")
        batch.drop_constraint("uq_token_usage_call_id", type_="unique")
        for name in ("accounting", "purpose", "run_id", "call_id"):
            batch.drop_column(name)

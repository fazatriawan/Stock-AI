"""add insider_transactions table

Revision ID: 004_insider_transactions
Revises: 003_investment_policies
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "004_insider_transactions"
down_revision = "003_investment_policies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insider_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False, index=True),
        sa.Column("insider_name", sa.String(200), nullable=False),
        sa.Column("insider_role", sa.String(50), nullable=False),
        sa.Column("transaction_type", sa.String(10), nullable=False),
        sa.Column("transaction_date", sa.Date, nullable=False, index=True),
        sa.Column("shares", sa.BigInteger, nullable=False),
        sa.Column("price_per_share", sa.Numeric(20, 4)),
        sa.Column("total_value", sa.Numeric(30, 2)),
        sa.Column("currency", sa.String(3), nullable=False, server_default="IDR"),
        sa.Column("shares_owned_after", sa.BigInteger),
        sa.Column("ownership_pct_after", sa.Numeric(8, 4)),
        sa.Column("disclosure_date", sa.Date),
        sa.Column("source_url", sa.String(500)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("instrument_id", "insider_name", "transaction_date", "shares", name="uq_insider_tx"),
    )


def downgrade() -> None:
    op.drop_table("insider_transactions")

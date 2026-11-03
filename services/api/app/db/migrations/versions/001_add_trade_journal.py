"""add trade_journal table

Revision ID: 001_trade_journal
Revises:
Create Date: 2024-01-15 00:00:00.000000

Phase 5 — Decision Journal untuk mencatat alasan keputusan investasi.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001_trade_journal"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_journal",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_symbol", sa.String(20), nullable=False, index=True),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("invalidation", sa.Text(), nullable=True),
        sa.Column("price_at_decision", sa.Numeric(12, 4), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_trade_journal_symbol", "trade_journal", ["canonical_symbol"])
    op.create_index("ix_trade_journal_date", "trade_journal", ["decision_date"])


def downgrade() -> None:
    op.drop_index("ix_trade_journal_date", "trade_journal")
    op.drop_index("ix_trade_journal_symbol", "trade_journal")
    op.drop_table("trade_journal")

"""add research_notes table

Revision ID: 002_research_notes
Revises: 001_trade_journal
Create Date: 2024-01-16 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002_research_notes"
down_revision = "001_trade_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("canonical_symbol", sa.String(20), nullable=True, index=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_research_notes_symbol", "research_notes", ["canonical_symbol"])
    op.create_index("ix_research_notes_created", "research_notes", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_research_notes_created", "research_notes")
    op.drop_index("ix_research_notes_symbol", "research_notes")
    op.drop_table("research_notes")

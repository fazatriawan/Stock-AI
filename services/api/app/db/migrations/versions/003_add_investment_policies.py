"""add investment_policies table

Revision ID: 003_investment_policies
Revises: 002_research_notes
Create Date: 2026-11-04 00:00:00.000000

Menyimpan Investment Policy Statement (IPS) yang bisa diubah user.
Setiap row mewakili satu profil kebijakan — saat ini hanya ada "default".
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003_investment_policies"
down_revision = "002_research_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("profile_name", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("mode", sa.String(20), nullable=False, server_default="BALANCED"),
        sa.Column("max_position_weight", sa.Numeric(5, 4), nullable=False, server_default="0.1000"),
        sa.Column("max_sector_weight", sa.Numeric(5, 4), nullable=False, server_default="0.3000"),
        sa.Column("buy_score_threshold", sa.Numeric(5, 2), nullable=False, server_default="60.00"),
        sa.Column("min_core_coverage", sa.Numeric(4, 3), nullable=False, server_default="0.600"),
        sa.Column("max_staleness_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("horizon", sa.String(50), nullable=False, server_default="3-12 months"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("investment_policies")

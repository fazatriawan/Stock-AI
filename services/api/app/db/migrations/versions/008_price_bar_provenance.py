"""008 price_bar provenance — freshness_status + source_id

Revision ID: 008_price_bar_provenance
Revises: 007_backtest_history
Create Date: 2026-11-13

Tambahkan kolom provenance ke price_bars sesuai FREE-02:
- freshness_status: FRESH / STALE / NOT_COVERED / UNAVAILABLE / CONFLICTED /
                    QUOTA_EXHAUSTED / LICENSE_BLOCKED
- source_id: FK ke sources.id (nullable — baris lama tidak punya source)
"""
from alembic import op
import sqlalchemy as sa

revision = "008_price_bar_provenance"
down_revision = "007_backtest_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_bars",
        sa.Column(
            "freshness_status",
            sa.String(20),
            nullable=False,
            server_default="FRESH",
        ),
    )
    op.add_column(
        "price_bars",
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_price_bars_freshness_status", "price_bars", ["freshness_status"])
    op.create_index("ix_price_bars_source_id", "price_bars", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_price_bars_source_id", table_name="price_bars")
    op.drop_index("ix_price_bars_freshness_status", table_name="price_bars")
    op.drop_column("price_bars", "source_id")
    op.drop_column("price_bars", "freshness_status")

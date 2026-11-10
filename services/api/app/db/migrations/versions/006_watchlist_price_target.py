"""006 watchlist price target

Revision ID: 006_watchlist_price_target
Revises: 005_alert_rules
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "006_watchlist_price_target"
down_revision = "005_alert_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlist_items", sa.Column("price_target", sa.Numeric(18, 4), nullable=True))
    op.add_column("watchlist_items", sa.Column("target_note", sa.Text(), nullable=True))
    op.add_column("watchlist_items", sa.Column("cost_basis", sa.Numeric(18, 4), nullable=True))
    op.add_column("watchlist_items", sa.Column("alert_on_target", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("watchlist_items", "alert_on_target")
    op.drop_column("watchlist_items", "cost_basis")
    op.drop_column("watchlist_items", "target_note")
    op.drop_column("watchlist_items", "price_target")

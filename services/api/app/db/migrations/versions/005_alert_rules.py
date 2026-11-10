"""R19 — Alert rules table.

Revision ID: 005_alert_rules
Revises: 004_insider_transactions
"""
from alembic import op
import sqlalchemy as sa

revision = "005_alert_rules"
down_revision = "004_insider_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_symbol", sa.String(20), nullable=True, index=True),
        sa.Column("rule_type", sa.String(40), nullable=False),
        # Kondisi: price_above, price_below, rsi_above, rsi_below,
        #          pct_change_1d, swing_breakout, swing_pullback, macro_inverted
        sa.Column("threshold_value", sa.Numeric(30, 6), nullable=True),
        sa.Column("direction", sa.String(10), nullable=True),   # ABOVE / BELOW
        sa.Column("cooldown_hours", sa.Integer, nullable=False, server_default="24"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fire_count", sa.Integer, nullable=False, server_default="0"),
        # Webhook: kosong = hanya simpan ke DB alert; diisi = POST ke URL
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column("webhook_secret", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("alert_rules")

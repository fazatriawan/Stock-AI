"""007 backtest history columns

Revision ID: 007_backtest_history
Revises: 006_watchlist_price_target
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "007_backtest_history"
down_revision = "006_watchlist_price_target"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("backtest_runs", sa.Column("symbol", sa.String(20), nullable=True))
    op.add_column("backtest_runs", sa.Column("strategy", sa.String(30), nullable=True))
    op.add_column("backtest_runs", sa.Column("bars_used", sa.Integer(), nullable=True))
    op.add_column("backtest_runs", sa.Column("total_return_pct", sa.Numeric(10, 4), nullable=True))
    op.add_column("backtest_runs", sa.Column("cagr_pct", sa.Numeric(10, 4), nullable=True))
    op.add_column("backtest_runs", sa.Column("sharpe_ratio", sa.Numeric(10, 4), nullable=True))
    op.add_column("backtest_runs", sa.Column("max_drawdown_pct", sa.Numeric(10, 4), nullable=True))
    op.add_column("backtest_runs", sa.Column("win_rate_pct", sa.Numeric(10, 4), nullable=True))
    op.add_column("backtest_runs", sa.Column("total_trades", sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in ["symbol", "strategy", "bars_used", "total_return_pct", "cagr_pct",
                "sharpe_ratio", "max_drawdown_pct", "win_rate_pct", "total_trades"]:
        op.drop_column("backtest_runs", col)

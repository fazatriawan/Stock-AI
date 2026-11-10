"""Initial schema — semua tabel inti selain trade_journal dan research_notes.

Revision ID: 000_initial_schema
Revises:
Create Date: 2026-11-04 00:00:00.000000

Menciptakan 24 tabel dari models.py yang belum pernah ada di migration sebelumnya.
trade_journal dan research_notes dibuat oleh 001 dan 002 masing-masing.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "000_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. sources — tidak ada FK, harus dibuat dulu
    # ------------------------------------------------------------------
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("publisher", sa.String(100), nullable=True),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("license_class", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("primary_or_secondary", sa.String(10), nullable=False, server_default="SECONDARY"),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="UNVERIFIED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 2. instruments
    # ------------------------------------------------------------------
    op.create_table(
        "instruments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("canonical_symbol", sa.String(20), nullable=False),
        sa.Column("local_symbol", sa.String(20), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("mic", sa.String(10), nullable=True),
        sa.Column("country", sa.String(5), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("asset_type", sa.String(20), nullable=False, server_default="EQUITY"),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("canonical_symbol", name="uq_instruments_canonical_symbol"),
    )
    op.create_index("ix_instruments_canonical_symbol", "instruments", ["canonical_symbol"])
    op.create_index("ix_instruments_local_symbol", "instruments", ["local_symbol"])

    # ------------------------------------------------------------------
    # 3. aliases (FK → instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "aliases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alias", sa.String(30), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("alias", "provider", name="uq_aliases_alias_provider"),
    )
    op.create_index("ix_aliases_alias", "aliases", ["alias"])

    # ------------------------------------------------------------------
    # 4. market_sessions (tidak ada FK)
    # ------------------------------------------------------------------
    op.create_table(
        "market_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("open_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("session_type", sa.String(20), nullable=False, server_default="REGULAR"),
        sa.Column("is_holiday", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("exchange", "session_date", name="uq_market_sessions_exchange_date"),
    )
    op.create_index("ix_market_sessions_exchange", "market_sessions", ["exchange"])
    op.create_index("ix_market_sessions_date", "market_sessions", ["session_date"])

    # ------------------------------------------------------------------
    # 5. price_bars (FK → instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "price_bars",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 6), nullable=True),
        sa.Column("high", sa.Numeric(20, 6), nullable=True),
        sa.Column("low", sa.Numeric(20, 6), nullable=True),
        sa.Column("close", sa.Numeric(20, 6), nullable=False),
        sa.Column("adj_close", sa.Numeric(20, 6), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("adjustment_version", sa.String(20), nullable=False, server_default="v1"),
        sa.Column("is_adjusted", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("instrument_id", "session_date", "provider", name="uq_price_bars_instrument_date_provider"),
    )
    op.create_index("ix_price_bars_instrument_id", "price_bars", ["instrument_id"])
    op.create_index("ix_price_bars_session_date", "price_bars", ["session_date"])

    # ------------------------------------------------------------------
    # 6. corporate_actions (FK → instruments, sources)
    # ------------------------------------------------------------------
    op.create_table(
        "corporate_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("effective_at", sa.Date(), nullable=False),
        sa.Column("announced_at", sa.Date(), nullable=True),
        sa.Column("ratio", sa.Numeric(20, 10), nullable=True),
        sa.Column("cash_amount", sa.Numeric(20, 6), nullable=True),
        sa.Column("currency", sa.String(5), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="CONFIRMED"),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_corporate_actions_instrument_id", "corporate_actions", ["instrument_id"])

    # ------------------------------------------------------------------
    # 7. financial_facts (FK → instruments, sources)
    # ------------------------------------------------------------------
    op.create_table(
        "financial_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("metric", sa.String(60), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("available_at", sa.Date(), nullable=True),
        sa.Column("value", sa.Numeric(30, 6), nullable=True),
        sa.Column("value_text", sa.String(200), nullable=True),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("currency", sa.String(5), nullable=True),
        sa.Column("accounting_basis", sa.String(20), nullable=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("revision_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("instrument_id", "metric", "period_end", "source_id", name="uq_financial_facts_instrument_metric_period_source"),
    )
    op.create_index("ix_financial_facts_instrument_id", "financial_facts", ["instrument_id"])
    op.create_index("ix_financial_facts_metric", "financial_facts", ["metric"])
    op.create_index("ix_financial_facts_period_end", "financial_facts", ["period_end"])

    # ------------------------------------------------------------------
    # 8. ownership_facts (FK → instruments, sources)
    # ------------------------------------------------------------------
    op.create_table(
        "ownership_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("holder_id", sa.String(100), nullable=False),
        sa.Column("holder_name", sa.String(200), nullable=True),
        sa.Column("percent", sa.Numeric(10, 6), nullable=True),
        sa.Column("share_count", sa.BigInteger(), nullable=True),
        sa.Column("report_period_end", sa.Date(), nullable=False),
        sa.Column("filed_at", sa.Date(), nullable=True),
        sa.Column("available_at", sa.Date(), nullable=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 9. macro_observations (FK → sources; immutable, no updated_at)
    # ------------------------------------------------------------------
    op.create_table(
        "macro_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("series_id", sa.String(60), nullable=False),
        sa.Column("observed_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(30, 8), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vintage_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("series_id", "observed_date", "vintage_at", name="uq_macro_observations_series_date_vintage"),
    )
    op.create_index("ix_macro_observations_series_id", "macro_observations", ["series_id"])

    # ------------------------------------------------------------------
    # 10. events (FK → sources)
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("country", sa.String(5), nullable=True),
        sa.Column("affected_sectors", sa.JSON(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_stage", sa.String(30), nullable=True),
        sa.Column("materiality", sa.String(20), nullable=False, server_default="LOW"),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_events_event_type", "events", ["event_type"])

    # ------------------------------------------------------------------
    # 11. event_company_impacts (FK → events, instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "event_company_impacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("mechanism", sa.Text(), nullable=True),
        sa.Column("exposure", sa.String(30), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("sign", sa.String(10), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=True),
        sa.Column("assumption", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="UNVERIFIED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_event_company_impacts_event_id", "event_company_impacts", ["event_id"])

    # ------------------------------------------------------------------
    # 12. portfolios
    # ------------------------------------------------------------------
    op.create_table(
        "portfolios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, server_default="Default"),
        sa.Column("base_currency", sa.String(5), nullable=False, server_default="IDR"),
        sa.Column("profile_id", sa.String(36), nullable=True),
        sa.Column("is_paper", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 13. trades (FK → portfolios, instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "trades",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("portfolio_id", sa.String(36), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("side", sa.String(5), nullable=False),
        sa.Column("shares", sa.Numeric(20, 4), nullable=False),
        sa.Column("price", sa.Numeric(20, 6), nullable=False),
        sa.Column("fee", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("tax", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(5), nullable=False),
        sa.Column("fx_to_base", sa.Numeric(20, 8), nullable=True),
        sa.Column("source_broker", sa.String(100), nullable=True),
        sa.Column("import_fingerprint", sa.String(64), nullable=True, unique=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_trades_portfolio_id", "trades", ["portfolio_id"])
    op.create_index("ix_trades_instrument_id", "trades", ["instrument_id"])

    # ------------------------------------------------------------------
    # 14. dividend_cashflows (FK → portfolios, instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "dividend_cashflows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("portfolio_id", sa.String(36), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("gross", sa.Numeric(20, 6), nullable=False),
        sa.Column("net", sa.Numeric(20, 6), nullable=False),
        sa.Column("currency", sa.String(5), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 15. positions_snapshot (FK → portfolios, instruments; immutable)
    # ------------------------------------------------------------------
    op.create_table(
        "positions_snapshot",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("portfolio_id", sa.String(36), sa.ForeignKey("portfolios.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("shares", sa.Numeric(20, 4), nullable=False),
        sa.Column("cost_basis", sa.Numeric(20, 6), nullable=False),
        sa.Column("market_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("exposure", sa.Numeric(10, 6), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("portfolio_id", "instrument_id", "as_of", name="uq_positions_snapshot_portfolio_instrument_date"),
    )

    # ------------------------------------------------------------------
    # 16. analysis_runs (tidak ada FK eksternal)
    # ------------------------------------------------------------------
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("data_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("rule_version", sa.String(20), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 17. factor_scores (FK → analysis_runs, instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "factor_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("factor_id", sa.String(40), nullable=False),
        sa.Column("raw_metric", sa.Numeric(20, 6), nullable=True),
        sa.Column("normalized_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("weight", sa.Numeric(6, 4), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=True),
        sa.Column("missing_flag", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_factor_scores_run_id", "factor_scores", ["run_id"])

    # ------------------------------------------------------------------
    # 18. recommendations (FK → analysis_runs, instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("horizon", sa.String(30), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=True),
        sa.Column("hard_gate_status", sa.String(30), nullable=False, server_default="PASS"),
        sa.Column("thesis", sa.JSON(), nullable=True),
        sa.Column("invalidation_rules", sa.JSON(), nullable=True),
        sa.Column("changed_factors", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_recommendations_run_id", "recommendations", ["run_id"])
    op.create_index("ix_recommendations_instrument_id", "recommendations", ["instrument_id"])

    # ------------------------------------------------------------------
    # 19. recommendation_evidence (FK → recommendations, sources)
    # ------------------------------------------------------------------
    op.create_table(
        "recommendation_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recommendation_id", sa.String(36), sa.ForeignKey("recommendations.id"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("claim_id", sa.String(36), nullable=True),
        sa.Column("fact_ref", sa.String(200), nullable=True),
    )
    op.create_index("ix_recommendation_evidence_rec_id", "recommendation_evidence", ["recommendation_id"])

    # ------------------------------------------------------------------
    # 20. decision_journal (FK → recommendations)
    # ------------------------------------------------------------------
    op.create_table(
        "decision_journal",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recommendation_id", sa.String(36), sa.ForeignKey("recommendations.id"), nullable=False),
        sa.Column("user_action", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_decision_journal_recommendation_id", "decision_journal", ["recommendation_id"])

    # ------------------------------------------------------------------
    # 21. alerts (FK → instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("materiality", sa.String(20), nullable=False, server_default="LOW"),
        sa.Column("dedup_key", sa.String(100), nullable=False, unique=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_event_type", "alerts", ["event_type"])

    # ------------------------------------------------------------------
    # 22. backtest_runs (tidak ada FK)
    # ------------------------------------------------------------------
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("universe_version", sa.String(50), nullable=True),
        sa.Column("train_start", sa.Date(), nullable=True),
        sa.Column("test_start", sa.Date(), nullable=True),
        sa.Column("test_end", sa.Date(), nullable=True),
        sa.Column("results_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 23. watchlists
    # ------------------------------------------------------------------
    op.create_table(
        "watchlists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 24. watchlist_items (FK → watchlists, instruments)
    # ------------------------------------------------------------------
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("watchlist_id", sa.String(36), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("instrument_id", sa.String(36), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("watchlist_id", "instrument_id", name="uq_watchlist_items_watchlist_instrument"),
    )


def downgrade() -> None:
    # Urutan terbalik dari upgrade — hapus yang paling punya FK terlebih dulu
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
    op.drop_table("backtest_runs")
    op.drop_table("alerts")
    op.drop_table("decision_journal")
    op.drop_table("recommendation_evidence")
    op.drop_table("recommendations")
    op.drop_table("factor_scores")
    op.drop_table("analysis_runs")
    op.drop_table("positions_snapshot")
    op.drop_table("dividend_cashflows")
    op.drop_table("trades")
    op.drop_table("portfolios")
    op.drop_table("event_company_impacts")
    op.drop_table("events")
    op.drop_table("macro_observations")
    op.drop_table("ownership_facts")
    op.drop_table("financial_facts")
    op.drop_table("corporate_actions")
    op.drop_table("price_bars")
    op.drop_table("market_sessions")
    op.drop_table("aliases")
    op.drop_index("ix_instruments_local_symbol", "instruments")
    op.drop_index("ix_instruments_canonical_symbol", "instruments")
    op.drop_table("instruments")
    op.drop_table("sources")

"""
Database models sesuai PRD §15.
Semua tabel memiliki created_at + updated_at kecuali yang immutable (price_bars, macro_observations).
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, func, JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


def new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Market universe
# ---------------------------------------------------------------------------

class Instrument(Base, TimestampMixin):
    __tablename__ = "instruments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    canonical_symbol: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    local_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    mic: Mapped[Optional[str]] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(5), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, default="EQUITY")
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(100))
    company_name: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")

    aliases: Mapped[list["InstrumentAlias"]] = relationship(back_populates="instrument")
    price_bars: Mapped[list["PriceBar"]] = relationship(back_populates="instrument")
    corporate_actions: Mapped[list["CorporateAction"]] = relationship(back_populates="instrument")
    financial_facts: Mapped[list["FinancialFact"]] = relationship(back_populates="instrument")


class InstrumentAlias(Base, TimestampMixin):
    __tablename__ = "aliases"
    __table_args__ = (UniqueConstraint("alias", "provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    alias: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    instrument: Mapped["Instrument"] = relationship(back_populates="aliases")


# ---------------------------------------------------------------------------
# Market calendar
# ---------------------------------------------------------------------------

class MarketSession(Base):
    __tablename__ = "market_sessions"
    __table_args__ = (UniqueConstraint("exchange", "session_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    close_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    session_type: Mapped[str] = mapped_column(String(20), nullable=False, default="REGULAR")
    is_holiday: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

class PriceBar(Base):
    """OHLCV harian. Immutable setelah ingested — tidak ada updated_at."""
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("instrument_id", "session_date", "provider"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    open: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    high: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    low: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    adj_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    adjustment_version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    is_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    instrument: Mapped["Instrument"] = relationship(back_populates="price_bars")


# ---------------------------------------------------------------------------
# Corporate actions
# ---------------------------------------------------------------------------

class CorporateAction(Base, TimestampMixin):
    __tablename__ = "corporate_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)  # SPLIT, DIVIDEND, RIGHTS, MERGER
    effective_at: Mapped[date] = mapped_column(Date, nullable=False)
    announced_at: Mapped[Optional[date]] = mapped_column(Date)
    ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 10))
    cash_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    currency: Mapped[Optional[str]] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="CONFIRMED")
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sources.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    instrument: Mapped["Instrument"] = relationship(back_populates="corporate_actions")


# ---------------------------------------------------------------------------
# Financial facts (fundamental data)
# ---------------------------------------------------------------------------

class FinancialFact(Base, TimestampMixin):
    __tablename__ = "financial_facts"
    __table_args__ = (
        UniqueConstraint("instrument_id", "metric", "period_end", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    filing_date: Mapped[Optional[date]] = mapped_column(Date)
    available_at: Mapped[Optional[date]] = mapped_column(Date)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 6))
    value_text: Mapped[Optional[str]] = mapped_column(String(200))
    unit: Mapped[Optional[str]] = mapped_column(String(30))
    currency: Mapped[Optional[str]] = mapped_column(String(5))
    accounting_basis: Mapped[Optional[str]] = mapped_column(String(20))
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sources.id"))
    revision_id: Mapped[Optional[str]] = mapped_column(String(36))

    instrument: Mapped["Instrument"] = relationship(back_populates="financial_facts")


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------

class OwnershipFact(Base, TimestampMixin):
    __tablename__ = "ownership_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    holder_id: Mapped[str] = mapped_column(String(100), nullable=False)
    holder_name: Mapped[Optional[str]] = mapped_column(String(200))
    percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    share_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    report_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filed_at: Mapped[Optional[date]] = mapped_column(Date)
    available_at: Mapped[Optional[date]] = mapped_column(Date)
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sources.id"))


# ---------------------------------------------------------------------------
# Macro
# ---------------------------------------------------------------------------

class MacroObservation(Base):
    """Immutable macro time series — tidak ada updated_at."""
    __tablename__ = "macro_observations"
    __table_args__ = (UniqueConstraint("series_id", "observed_date", "vintage_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    observed_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(30, 8))
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    vintage_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sources.id"))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Events / policy
# ---------------------------------------------------------------------------

class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    country: Mapped[Optional[str]] = mapped_column(String(5))
    affected_sectors: Mapped[Optional[list]] = mapped_column(JSON)
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    policy_stage: Mapped[Optional[str]] = mapped_column(String(30))
    materiality: Mapped[str] = mapped_column(String(20), nullable=False, default="LOW")
    title: Mapped[Optional[str]] = mapped_column(String(300))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sources.id"))

    company_impacts: Mapped[list["EventCompanyImpact"]] = relationship(back_populates="event")


class EventCompanyImpact(Base, TimestampMixin):
    __tablename__ = "event_company_impacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    mechanism: Mapped[Optional[str]] = mapped_column(Text)
    exposure: Mapped[Optional[str]] = mapped_column(String(30))
    hypothesis: Mapped[Optional[str]] = mapped_column(Text)
    sign: Mapped[Optional[str]] = mapped_column(String(10))
    confidence: Mapped[Optional[str]] = mapped_column(String(20))
    assumption: Mapped[Optional[str]] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNVERIFIED")

    event: Mapped["Event"] = relationship(back_populates="company_impacts")


# ---------------------------------------------------------------------------
# Sources (provenance)
# ---------------------------------------------------------------------------

class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    url: Mapped[Optional[str]] = mapped_column(String(500))
    publisher: Mapped[Optional[str]] = mapped_column(String(100))
    title: Mapped[Optional[str]] = mapped_column(String(300))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    license_class: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    checksum: Mapped[Optional[str]] = mapped_column(String(64))
    primary_or_secondary: Mapped[str] = mapped_column(String(10), nullable=False, default="SECONDARY")
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNVERIFIED")


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

class Portfolio(Base, TimestampMixin):
    __tablename__ = "portfolios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Default")
    base_currency: Mapped[str] = mapped_column(String(5), nullable=False, default="IDR")
    profile_id: Mapped[Optional[str]] = mapped_column(String(36))
    is_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    trades: Mapped[list["Trade"]] = relationship(back_populates="portfolio")
    dividend_cashflows: Mapped[list["DividendCashflow"]] = relationship(back_populates="portfolio")


class Trade(Base, TimestampMixin):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False)  # BUY / SELL
    shares: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(5), nullable=False)
    fx_to_base: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 8))
    source_broker: Mapped[Optional[str]] = mapped_column(String(100))
    import_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="trades")


class DividendCashflow(Base, TimestampMixin):
    __tablename__ = "dividend_cashflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    ex_date: Mapped[date] = mapped_column(Date, nullable=False)
    pay_date: Mapped[Optional[date]] = mapped_column(Date)
    gross: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    net: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), nullable=False)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="dividend_cashflows")


class PositionSnapshot(Base):
    __tablename__ = "positions_snapshot"
    __table_args__ = (UniqueConstraint("portfolio_id", "instrument_id", "as_of"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    market_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    exposure: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Analysis & recommendations
# ---------------------------------------------------------------------------

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_snapshot_hash: Mapped[Optional[str]] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    factor_scores: Mapped[list["FactorScore"]] = relationship(back_populates="run")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="run")


class FactorScore(Base):
    __tablename__ = "factor_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    factor_id: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_metric: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 6))
    normalized_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    weight: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    source_refs: Mapped[Optional[list]] = mapped_column(JSON)
    missing_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    run: Mapped["AnalysisRun"] = relationship(back_populates="factor_scores")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False, index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    horizon: Mapped[Optional[str]] = mapped_column(String(30))
    confidence: Mapped[Optional[str]] = mapped_column(String(20))
    hard_gate_status: Mapped[str] = mapped_column(String(30), nullable=False, default="PASS")
    thesis: Mapped[Optional[dict]] = mapped_column(JSON)
    invalidation_rules: Mapped[Optional[list]] = mapped_column(JSON)
    changed_factors: Mapped[Optional[list]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["AnalysisRun"] = relationship(back_populates="recommendations")
    evidence: Mapped[list["RecommendationEvidence"]] = relationship(back_populates="recommendation")
    decisions: Mapped[list["DecisionJournal"]] = relationship(back_populates="recommendation")


class RecommendationEvidence(Base):
    __tablename__ = "recommendation_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sources.id"))
    claim_id: Mapped[Optional[str]] = mapped_column(String(36))
    fact_ref: Mapped[Optional[str]] = mapped_column(String(200))

    recommendation: Mapped["Recommendation"] = relationship(back_populates="evidence")


class DecisionJournal(Base):
    __tablename__ = "decision_journal"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False, index=True)
    user_action: Mapped[str] = mapped_column(String(20), nullable=False)  # ACCEPT / REJECT / DEFER
    notes: Mapped[Optional[str]] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    recommendation: Mapped["Recommendation"] = relationship(back_populates="decisions")


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    instrument_id: Mapped[Optional[str]] = mapped_column(ForeignKey("instruments.id"))
    materiality: Mapped[str] = mapped_column(String(20), nullable=False, default="LOW")
    dedup_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    universe_version: Mapped[Optional[str]] = mapped_column(String(50))
    train_start: Mapped[Optional[date]] = mapped_column(Date)
    test_start: Mapped[Optional[date]] = mapped_column(Date)
    test_end: Mapped[Optional[date]] = mapped_column(Date)
    results_json: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

class Watchlist(Base, TimestampMixin):
    __tablename__ = "watchlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    items: Mapped[list["WatchlistItem"]] = relationship(back_populates="watchlist")


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "instrument_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    watchlist_id: Mapped[str] = mapped_column(ForeignKey("watchlists.id"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    watchlist: Mapped["Watchlist"] = relationship(back_populates="items")


# ---------------------------------------------------------------------------
# Trade Journal — Phase 5
# ---------------------------------------------------------------------------

class TradeJournal(Base, TimestampMixin):
    """Catatan alasan di balik keputusan investasi — standalone, tidak linked ke recommendation."""
    __tablename__ = "trade_journal"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    canonical_symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # BUY/SELL/HOLD/WATCH
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    # Thesis — diisi saat beli, direvisi saat jual
    thesis: Mapped[Optional[str]] = mapped_column(Text)
    # Invalidation triggers — kapan kita harus keluar
    invalidation: Mapped[Optional[str]] = mapped_column(Text)
    # Harga referensi saat membuat catatan
    price_at_decision: Mapped[Optional[float]] = mapped_column(Numeric(12, 4))
    # Review — diisi belakangan untuk evaluasi keputusan
    outcome: Mapped[Optional[str]] = mapped_column(String(20))   # CORRECT / INCORRECT / PENDING
    outcome_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

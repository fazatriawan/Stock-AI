"""
Daily Change Digest Engine — R12.

Menyusun ringkasan perubahan harian untuk portofolio:
- Pergerakan harga tiap posisi (return 1 hari)
- Market status dari calendar (IDX / NYSE)
- Alert dedup: satu alert per instrument per kategori per hari

Prinsip: deterministik, tidak ada LLM, gagal graceful.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from app.domain.calendar import MarketCalendar


# ---------------------------------------------------------------------------
# Alert system dengan dedup
# ---------------------------------------------------------------------------

ALERT_CATEGORIES = {
    "OVERWEIGHT",    # posisi > batas IPS
    "LOSS",          # unrealized loss > threshold
    "NO_PRICE",      # tidak ada harga terkini
    "STALE_PRICE",   # harga > _STALE_DAYS hari
    "STRONG_MOVE",   # harga bergerak > 3% dalam 1 hari
    "VOLUME_SPIKE",  # volume >> ADV (jika tersedia)
    "MARKET_CLOSED", # bursa tutup hari ini
}


@dataclass
class DigestAlert:
    category: str    # dari ALERT_CATEGORIES
    symbol: str      # canonical_symbol atau "" untuk alert global
    message: str
    severity: str    # "INFO" / "WARNING" / "CRITICAL"


def _dedup_alerts(alerts: list[DigestAlert]) -> list[DigestAlert]:
    """
    Hapus duplikat: satu alert per (category, symbol) per pemanggilan.
    Prioritaskan severity lebih tinggi jika ada duplikat.
    """
    severity_rank = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}
    seen: dict[tuple[str, str], DigestAlert] = {}
    for a in alerts:
        key = (a.category, a.symbol)
        if key not in seen or severity_rank.get(a.severity, 0) > severity_rank.get(seen[key].severity, 0):
            seen[key] = a
    return list(seen.values())


# ---------------------------------------------------------------------------
# Price change summary
# ---------------------------------------------------------------------------

@dataclass
class PositionChange:
    canonical_symbol: str
    company_name: Optional[str]
    exchange: str
    return_1d: Optional[float]       # (close_today - close_prev) / close_prev
    close_today: Optional[float]
    close_prev: Optional[float]
    days_since_price: int            # 0 = harga hari ini ada
    is_trading_day_today: bool


# ---------------------------------------------------------------------------
# Market session summary (multi-exchange)
# ---------------------------------------------------------------------------

@dataclass
class MarketSessionSummary:
    exchange: str
    is_trading_day: bool
    is_open_now: bool
    local_time_str: str              # jam lokal bursa saat ini (untuk display)
    next_trading_day: Optional[date] = None


def get_market_sessions(as_of: datetime) -> list[MarketSessionSummary]:
    """Ringkasan status semua bursa yang didukung."""
    summaries = []
    for exchange in ("IDX", "NYSE"):
        try:
            cal = MarketCalendar(exchange)
            today = as_of.astimezone(cal.tz).date()
            is_trading = cal.is_trading_day(today)
            # "open now" = antara open_time dan close_time lokal
            local_now = as_of.astimezone(cal.tz)
            open_h, open_m = cal.config["open_time"]
            close_h, close_m = cal.config["close_time"]
            is_open = (
                is_trading
                and (local_now.hour, local_now.minute) >= (open_h, open_m)
                and (local_now.hour, local_now.minute) < (close_h, close_m)
            )
            next_td = cal.next_trading_day(today) if not is_trading else None
            summaries.append(MarketSessionSummary(
                exchange=exchange,
                is_trading_day=is_trading,
                is_open_now=is_open,
                local_time_str=local_now.strftime("%H:%M %Z"),
                next_trading_day=next_td,
            ))
        except Exception:
            pass
    return summaries


# ---------------------------------------------------------------------------
# Main digest builder
# ---------------------------------------------------------------------------

@dataclass
class DailyDigest:
    """
    Hasil lengkap daily change digest.
    Semua data-driven — tidak ada angka LLM.
    """
    as_of: datetime
    market_sessions: list[MarketSessionSummary] = field(default_factory=list)
    position_changes: list[PositionChange] = field(default_factory=list)
    alerts: list[DigestAlert] = field(default_factory=list)

    # Summary stats
    gainers_count: int = 0
    losers_count: int = 0
    unchanged_count: int = 0
    no_data_count: int = 0

    # Convenience
    any_market_open: bool = False


def build_digest(
    *,
    as_of: datetime,
    # Posisi: {instrument_id: {symbol, company_name, exchange, weight, unrealized_pnl_pct}}
    positions: list[dict],
    # Harga: {instrument_id: {today: float|None, prev: float|None, session_date: date, prev_date: date|None}}
    price_data: dict[str, dict],
    max_position_weight: float = 0.10,
    loss_threshold: float = -0.15,
    strong_move_threshold: float = 0.03,
    stale_days: int = 3,
) -> DailyDigest:
    """
    Susun daily digest dari data yang sudah di-load.
    Alert dedup berjalan otomatis.
    """
    now = as_of or datetime.now(tz=timezone.utc)
    sessions = get_market_sessions(now)
    any_open = any(s.is_open_now for s in sessions)
    today = now.date()

    raw_alerts: list[DigestAlert] = []
    changes: list[PositionChange] = []

    for pos in positions:
        iid = pos["instrument_id"]
        symbol = pos.get("canonical_symbol", iid)
        short_sym = symbol.split(":")[-1]
        exchange = pos.get("exchange", "IDX")
        weight = pos.get("weight", 0.0)
        unrealized = pos.get("unrealized_pnl_pct")

        prices = price_data.get(iid, {})
        close_today = prices.get("today")
        close_prev = prices.get("prev")
        session_date = prices.get("session_date")

        # Hitung return 1 hari
        return_1d: Optional[float] = None
        if close_today and close_prev and close_prev > 0:
            return_1d = (close_today - close_prev) / close_prev

        # Days since price
        days_since = (today - session_date).days if session_date else 999

        # Is today a trading day for this exchange?
        try:
            cal = MarketCalendar(exchange if exchange in ("IDX", "NYSE", "NASDAQ") else "IDX")
            is_trading_today = cal.is_trading_day(today)
        except Exception:
            is_trading_today = today.weekday() < 5

        changes.append(PositionChange(
            canonical_symbol=symbol,
            company_name=pos.get("company_name"),
            exchange=exchange,
            return_1d=return_1d,
            close_today=close_today,
            close_prev=close_prev,
            days_since_price=days_since,
            is_trading_day_today=is_trading_today,
        ))

        # --- Alerts ---
        if close_today is None:
            raw_alerts.append(DigestAlert(
                category="NO_PRICE",
                symbol=short_sym,
                message=f"{short_sym}: tidak ada harga terkini",
                severity="WARNING",
            ))
        elif is_trading_today and days_since > stale_days:
            raw_alerts.append(DigestAlert(
                category="STALE_PRICE",
                symbol=short_sym,
                message=f"{short_sym}: harga terakhir {days_since} hari lalu",
                severity="WARNING",
            ))

        if return_1d is not None and abs(return_1d) >= strong_move_threshold:
            direction = "naik" if return_1d > 0 else "turun"
            raw_alerts.append(DigestAlert(
                category="STRONG_MOVE",
                symbol=short_sym,
                message=f"{short_sym} {direction} {abs(return_1d)*100:.1f}% hari ini",
                severity="INFO" if return_1d > 0 else "WARNING",
            ))

        if weight >= max_position_weight:
            raw_alerts.append(DigestAlert(
                category="OVERWEIGHT",
                symbol=short_sym,
                message=f"{short_sym} {weight*100:.0f}% portofolio — di atas batas {max_position_weight*100:.0f}%",
                severity="WARNING",
            ))

        if unrealized is not None and unrealized < loss_threshold:
            raw_alerts.append(DigestAlert(
                category="LOSS",
                symbol=short_sym,
                message=f"{short_sym} rugi {abs(unrealized)*100:.1f}% — cek Loss Analyzer",
                severity="CRITICAL" if unrealized < -0.25 else "WARNING",
            ))

    # Dedup alerts
    deduped_alerts = _dedup_alerts(raw_alerts)

    # Summary stats
    gainers = sum(1 for c in changes if c.return_1d is not None and c.return_1d > 0.001)
    losers = sum(1 for c in changes if c.return_1d is not None and c.return_1d < -0.001)
    unchanged = sum(1 for c in changes if c.return_1d is not None and abs(c.return_1d) <= 0.001)
    no_data = sum(1 for c in changes if c.return_1d is None)

    return DailyDigest(
        as_of=now,
        market_sessions=sessions,
        position_changes=sorted(
            changes,
            key=lambda c: (c.return_1d or 0),
            reverse=True,  # terbesar dulu
        ),
        alerts=sorted(deduped_alerts, key=lambda a: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}.get(a.severity, 3)),
        gainers_count=gainers,
        losers_count=losers,
        unchanged_count=unchanged,
        no_data_count=no_data,
        any_market_open=any_open,
    )

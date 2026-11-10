"""Unit tests untuk Daily Change Digest Engine (R12)."""
from datetime import datetime, timezone, date

from app.domain.digest import (
    build_digest,
    _dedup_alerts,
    get_market_sessions,
    DigestAlert,
)


def _make_dt(hour: int = 10, tz_str: str = "Asia/Jakarta") -> datetime:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(tz_str)
    return datetime(2026, 11, 4, hour, 0, 0, tzinfo=tz).astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Alert dedup
# ---------------------------------------------------------------------------

def test_dedup_removes_duplicate_category_symbol():
    alerts = [
        DigestAlert("OVERWEIGHT", "BBCA", "BBCA 15% — over", "WARNING"),
        DigestAlert("OVERWEIGHT", "BBCA", "BBCA 16% — over", "WARNING"),
    ]
    result = _dedup_alerts(alerts)
    assert len(result) == 1

def test_dedup_keeps_different_symbols():
    alerts = [
        DigestAlert("OVERWEIGHT", "BBCA", "BBCA over", "WARNING"),
        DigestAlert("OVERWEIGHT", "TLKM", "TLKM over", "WARNING"),
    ]
    result = _dedup_alerts(alerts)
    assert len(result) == 2

def test_dedup_keeps_higher_severity():
    alerts = [
        DigestAlert("LOSS", "BBCA", "BBCA -15%", "WARNING"),
        DigestAlert("LOSS", "BBCA", "BBCA -26%", "CRITICAL"),
    ]
    result = _dedup_alerts(alerts)
    assert len(result) == 1
    assert result[0].severity == "CRITICAL"

def test_dedup_different_categories_same_symbol():
    alerts = [
        DigestAlert("OVERWEIGHT", "BBCA", "overweight", "WARNING"),
        DigestAlert("LOSS", "BBCA", "loss", "WARNING"),
    ]
    result = _dedup_alerts(alerts)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Market sessions
# ---------------------------------------------------------------------------

def test_market_sessions_returns_idx_and_nyse():
    now = _make_dt(10)
    sessions = get_market_sessions(now)
    exchanges = {s.exchange for s in sessions}
    assert "IDX" in exchanges
    assert "NYSE" in exchanges

def test_idx_open_during_trading_hours():
    # Selasa 10:00 WIB = 03:00 UTC
    now = _make_dt(10, "Asia/Jakarta")
    sessions = get_market_sessions(now)
    idx = next(s for s in sessions if s.exchange == "IDX")
    # 10:00 WIB antara 09:00 dan 16:15 → open
    assert idx.is_trading_day is True
    assert idx.is_open_now is True

def test_idx_closed_on_weekend():
    from zoneinfo import ZoneInfo
    # Sabtu
    sat = datetime(2026, 11, 7, 10, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
    sessions = get_market_sessions(sat.astimezone(timezone.utc))
    idx = next(s for s in sessions if s.exchange == "IDX")
    assert idx.is_trading_day is False
    assert idx.is_open_now is False

def test_idx_closed_after_hours():
    # 20:00 WIB — setelah close 16:15
    now = _make_dt(20, "Asia/Jakarta")
    sessions = get_market_sessions(now)
    idx = next(s for s in sessions if s.exchange == "IDX")
    assert idx.is_trading_day is True   # hari bursa
    assert idx.is_open_now is False     # tapi sudah tutup


# ---------------------------------------------------------------------------
# Full digest
# ---------------------------------------------------------------------------

def _base_positions():
    return [
        {
            "instrument_id": "inst-001",
            "canonical_symbol": "IDX:BBCA",
            "company_name": "BCA",
            "exchange": "IDX",
            "weight": 0.08,
            "unrealized_pnl_pct": 0.05,
        },
        {
            "instrument_id": "inst-002",
            "canonical_symbol": "IDX:TLKM",
            "company_name": "Telkom",
            "exchange": "IDX",
            "weight": 0.05,
            "unrealized_pnl_pct": -0.03,
        },
    ]

def _base_prices():
    return {
        "inst-001": {
            "today": 9500.0,
            "prev": 9000.0,
            "session_date": date(2026, 11, 4),
            "prev_date": date(2026, 11, 3),
        },
        "inst-002": {
            "today": 3800.0,
            "prev": 3900.0,
            "session_date": date(2026, 11, 4),
            "prev_date": date(2026, 11, 3),
        },
    }


def test_digest_return_1d_calculated():
    now = _make_dt(10)
    digest = build_digest(as_of=now, positions=_base_positions(), price_data=_base_prices())
    bbca = next(c for c in digest.position_changes if "BBCA" in c.canonical_symbol)
    # (9500 - 9000) / 9000 ≈ 5.56%
    assert bbca.return_1d is not None
    assert abs(bbca.return_1d - 500/9000) < 0.001

def test_digest_gainer_loser_count():
    now = _make_dt(10)
    digest = build_digest(as_of=now, positions=_base_positions(), price_data=_base_prices())
    assert digest.gainers_count == 1   # BBCA naik
    assert digest.losers_count == 1    # TLKM turun

def test_digest_strong_move_alert():
    now = _make_dt(10)
    # BBCA naik ~5.56% → strong move alert
    digest = build_digest(as_of=now, positions=_base_positions(), price_data=_base_prices())
    strong_alerts = [a for a in digest.alerts if a.category == "STRONG_MOVE"]
    assert any("BBCA" in a.symbol for a in strong_alerts)

def test_digest_no_duplicate_alerts():
    now = _make_dt(10)
    digest = build_digest(as_of=now, positions=_base_positions(), price_data=_base_prices())
    # Tidak ada duplikat (category, symbol)
    keys = [(a.category, a.symbol) for a in digest.alerts]
    assert len(keys) == len(set(keys))

def test_digest_overweight_alert():
    now = _make_dt(10)
    positions = _base_positions()
    positions[0]["weight"] = 0.15  # di atas 10%
    digest = build_digest(as_of=now, positions=positions, price_data=_base_prices())
    overweight = [a for a in digest.alerts if a.category == "OVERWEIGHT"]
    assert len(overweight) == 1
    assert "BBCA" in overweight[0].symbol

def test_digest_loss_alert_critical():
    now = _make_dt(10)
    positions = _base_positions()
    positions[1]["unrealized_pnl_pct"] = -0.30  # -30% → CRITICAL
    digest = build_digest(as_of=now, positions=positions, price_data=_base_prices())
    loss_alerts = [a for a in digest.alerts if a.category == "LOSS"]
    assert any(a.severity == "CRITICAL" for a in loss_alerts)

def test_digest_no_price_alert():
    now = _make_dt(10)
    prices = _base_prices()
    prices["inst-001"]["today"] = None  # tidak ada harga
    digest = build_digest(as_of=now, positions=_base_positions(), price_data=prices)
    no_price = [a for a in digest.alerts if a.category == "NO_PRICE"]
    assert len(no_price) == 1

def test_digest_alerts_sorted_by_severity():
    now = _make_dt(10)
    positions = _base_positions()
    positions[0]["weight"] = 0.15         # WARNING: overweight
    positions[1]["unrealized_pnl_pct"] = -0.30  # CRITICAL: loss
    digest = build_digest(as_of=now, positions=positions, price_data=_base_prices())
    if len(digest.alerts) >= 2:
        severity_rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        ranks = [severity_rank.get(a.severity, 3) for a in digest.alerts]
        assert ranks == sorted(ranks)

def test_digest_positions_sorted_by_return():
    now = _make_dt(10)
    digest = build_digest(as_of=now, positions=_base_positions(), price_data=_base_prices())
    returns = [c.return_1d for c in digest.position_changes if c.return_1d is not None]
    if len(returns) >= 2:
        assert returns[0] >= returns[1]  # descending

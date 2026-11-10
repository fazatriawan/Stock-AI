"""Unit tests untuk Dividend Sustainability Engine (R11)."""
from datetime import date

from app.analytics.dividend import (
    DividendTrend,
    SustainabilityRating,
    analyze_dividend_sustainability,
    _cagr,
    _classify_trend,
    DividendPoint,
)


TODAY = date(2026, 11, 4)

def _base(**overrides):
    params = dict(
        instrument_id="inst-001",
        as_of=TODAY,
        dps_by_year={2024: 100.0, 2025: 110.0, 2026: 120.0},
        eps_by_year={2024: 300.0, 2025: 330.0, 2026: 360.0},
        fcf_by_year={2024: 1_000_000_000, 2025: 1_100_000_000, 2026: 1_200_000_000},
        shares_by_year={2024: 10_000_000, 2025: 10_000_000, 2026: 10_000_000},
        dividend_yield=0.028,
        inflation_rate=0.027,
    )
    params.update(overrides)
    return params


# ---------------------------------------------------------------------------
# CAGR helper
# ---------------------------------------------------------------------------

def test_cagr_positive():
    result = _cagr(100, 121, 2)
    assert abs(result - 0.10) < 0.001

def test_cagr_zero_start():
    assert _cagr(0, 100, 3) is None

def test_cagr_zero_years():
    assert _cagr(100, 110, 0) is None


# ---------------------------------------------------------------------------
# Trend classifier
# ---------------------------------------------------------------------------

def test_trend_growing():
    history = [
        DividendPoint(year=2024, dps=100, eps=300, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
        DividendPoint(year=2025, dps=110, eps=320, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
        DividendPoint(year=2026, dps=120, eps=340, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
    ]
    assert _classify_trend(history) == DividendTrend.GROWING

def test_trend_stable():
    history = [
        DividendPoint(year=2024, dps=100, eps=300, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
        DividendPoint(year=2025, dps=101, eps=320, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
        DividendPoint(year=2026, dps=100, eps=340, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
    ]
    assert _classify_trend(history) == DividendTrend.STABLE

def test_trend_cut():
    # Turun > 20% dalam 1 tahun
    history = [
        DividendPoint(year=2024, dps=100, eps=300, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
        DividendPoint(year=2025, dps=100, eps=300, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
        DividendPoint(year=2026, dps=70, eps=100, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
    ]
    assert _classify_trend(history) == DividendTrend.CUT

def test_trend_declining():
    history = [
        DividendPoint(year=2024, dps=100, eps=300, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
        DividendPoint(year=2025, dps=90, eps=280, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
        DividendPoint(year=2026, dps=85, eps=260, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
    ]
    assert _classify_trend(history) == DividendTrend.DECLINING

def test_trend_no_data():
    assert _classify_trend([]) == DividendTrend.NO_DATA

def test_trend_initiated_1year():
    history = [
        DividendPoint(year=2026, dps=100, eps=300, fcf_per_share=None, payout_ratio=None, fcf_payout_ratio=None),
    ]
    assert _classify_trend(history) == DividendTrend.INITIATED


# ---------------------------------------------------------------------------
# Full engine
# ---------------------------------------------------------------------------

def test_strong_case():
    result = analyze_dividend_sustainability(**_base())
    assert result.rating == SustainabilityRating.STRONG
    assert result.trend == DividendTrend.GROWING
    assert result.payout_ratio is not None
    assert abs(result.payout_ratio - 120/360) < 0.001
    assert result.real_yield is not None
    assert abs(result.real_yield - 0.001) < 0.001  # 2.8% - 2.7% = 0.1%
    assert result.dgr_3y is not None
    assert result.dgr_3y > 0

def test_no_dps_data():
    result = analyze_dividend_sustainability(**_base(dps_by_year={}))
    assert result.rating == SustainabilityRating.INSUFFICIENT_DATA

def test_payout_over_100_unsustainable():
    # DPS lebih besar dari EPS
    result = analyze_dividend_sustainability(**_base(
        dps_by_year={2024: 500, 2025: 500, 2026: 500},
        eps_by_year={2024: 300, 2025: 300, 2026: 300},
    ))
    assert result.rating == SustainabilityRating.UNSUSTAINABLE
    assert result.payout_ratio is not None
    assert result.payout_ratio > 1.0

def test_cut_unsustainable():
    result = analyze_dividend_sustainability(**_base(
        dps_by_year={2024: 100, 2025: 100, 2026: 70},
    ))
    assert result.rating == SustainabilityRating.UNSUSTAINABLE
    assert result.trend == DividendTrend.CUT

def test_high_payout_weak():
    # Payout 85% → WEAK; FCF tidak ada agar tidak trigger FCF check
    result = analyze_dividend_sustainability(**_base(
        dps_by_year={2024: 250, 2025: 255, 2026: 255},
        eps_by_year={2024: 300, 2025: 300, 2026: 300},
        fcf_by_year={},   # tanpa FCF — hanya EPS payout check
        shares_by_year={},
    ))
    assert result.rating == SustainabilityRating.WEAK

def test_negative_real_yield_note():
    result = analyze_dividend_sustainability(**_base(
        dividend_yield=0.02,
        inflation_rate=0.05,
    ))
    assert result.real_yield is not None
    assert result.real_yield < 0
    assert any("Real yield negatif" in n for n in result.notes)

def test_no_inflation_data_gap():
    result = analyze_dividend_sustainability(**_base(inflation_rate=None))
    assert result.real_yield is None
    assert any("inflasi" in g for g in result.data_gaps)

def test_fcf_payout_ratio_calculated():
    # FCF per share = 1_200_000_000 / 10_000_000 = 120, DPS = 120
    # fcf_payout = 120/120 = 1.0 → UNSUSTAINABLE
    result = analyze_dividend_sustainability(**_base(
        dps_by_year={2024: 100, 2025: 110, 2026: 120},
        fcf_by_year={2024: 1_000_000_000, 2025: 1_100_000_000, 2026: 1_200_000_000},
        shares_by_year={2024: 10_000_000, 2025: 10_000_000, 2026: 10_000_000},
    ))
    # FCF per share 2026 = 120, DPS = 120 → fcf_payout = 1.0
    assert result.history[-1].fcf_payout_ratio is not None
    assert abs(result.history[-1].fcf_payout_ratio - 1.0) < 0.001

def test_history_sorted_ascending():
    result = analyze_dividend_sustainability(**_base())
    years = [h.year for h in result.history]
    assert years == sorted(years)

def test_dgr_3y_computed():
    # DPS: 100 → 120 dalam 2 tahun → CAGR ≈ 9.5%
    result = analyze_dividend_sustainability(**_base())
    assert result.dgr_3y is not None
    assert abs(result.dgr_3y - ((120/100)**0.5 - 1)) < 0.001

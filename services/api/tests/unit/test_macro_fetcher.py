"""Unit tests untuk R17 Global Macro — yield curve analyzer & impact scorer."""
import pytest
from app.ingestion.macro_fetcher import (
    analyze_yield_curve,
    score_macro_impact,
    YieldCurveSignal,
)


# ---------------------------------------------------------------------------
# Yield curve analyzer
# ---------------------------------------------------------------------------

def test_yield_curve_normal():
    yc = analyze_yield_curve(treasury_10y=4.5, treasury_2y=3.0)
    assert yc.signal == YieldCurveSignal.NORMAL
    assert yc.spread_pct == pytest.approx(1.5, rel=0.01)
    assert "NORMAL" in yc.notes


def test_yield_curve_flat():
    yc = analyze_yield_curve(treasury_10y=4.1, treasury_2y=3.8)
    assert yc.signal == YieldCurveSignal.FLAT
    assert yc.spread_pct == pytest.approx(0.3, rel=0.01)
    assert "DATAR" in yc.notes or "FLAT" in yc.notes.upper()


def test_yield_curve_inverted():
    yc = analyze_yield_curve(treasury_10y=3.5, treasury_2y=4.8)
    assert yc.signal == YieldCurveSignal.INVERTED
    assert yc.spread_pct is not None
    assert yc.spread_pct < 0
    assert "resesi" in yc.notes.lower() or "TERBALIK" in yc.notes


def test_yield_curve_no_data():
    yc = analyze_yield_curve(treasury_10y=None, treasury_2y=None)
    assert yc.signal == YieldCurveSignal.NORMAL
    assert yc.spread_pct is None
    assert "tidak tersedia" in yc.notes.lower()


def test_yield_curve_partial_data():
    yc = analyze_yield_curve(treasury_10y=4.5, treasury_2y=None)
    assert yc.spread_pct is None


# ---------------------------------------------------------------------------
# Macro impact scorer
# ---------------------------------------------------------------------------

def test_macro_impact_severe_fed_inverted():
    yc = analyze_yield_curve(3.5, 5.0)  # inverted
    impact = score_macro_impact(
        fed_rate=5.5,
        cpi_us=None,
        yield_curve=yc,
        bi_rate=None,
        usd_idr=None,
    )
    assert impact.score < -0.5
    assert impact.level == "SEVERE"
    assert len(impact.drivers) > 0
    assert len(impact.recommendations) > 0


def test_macro_impact_positive_low_rates():
    yc = analyze_yield_curve(3.0, 1.5)  # normal, rendah
    impact = score_macro_impact(
        fed_rate=1.5,
        cpi_us=None,
        yield_curve=yc,
        bi_rate=4.0,
        usd_idr=14_500,
    )
    assert impact.score > 0
    assert impact.level == "POSITIVE"


def test_macro_impact_neutral_no_data():
    impact = score_macro_impact(
        fed_rate=None,
        cpi_us=None,
        yield_curve=None,
        bi_rate=None,
        usd_idr=None,
    )
    assert impact.level in ("NEUTRAL", "POSITIVE")
    assert len(impact.drivers) > 0


def test_macro_impact_weak_rupiah():
    yc = analyze_yield_curve(4.5, 4.0)
    impact = score_macro_impact(
        fed_rate=None,
        cpi_us=None,
        yield_curve=yc,
        bi_rate=None,
        usd_idr=17_000,  # sangat lemah
    )
    assert impact.score < 0
    assert any("rupiah" in d.lower() or "USD/IDR" in d for d in impact.drivers)


def test_macro_impact_high_bi_rate():
    yc = analyze_yield_curve(4.5, 4.0)
    impact = score_macro_impact(
        fed_rate=None,
        cpi_us=None,
        yield_curve=yc,
        bi_rate=6.5,
        usd_idr=None,
    )
    assert impact.score < 0
    assert any("BI Rate" in d for d in impact.drivers)


def test_macro_score_clamped():
    yc = analyze_yield_curve(2.0, 5.0)  # strongly inverted
    impact = score_macro_impact(
        fed_rate=6.0,
        cpi_us=None,
        yield_curve=yc,
        bi_rate=7.0,
        usd_idr=18_000,
    )
    assert -1.0 <= impact.score <= 1.0


def test_macro_score_always_has_drivers():
    impact = score_macro_impact(None, None, None, None, None)
    assert len(impact.drivers) >= 1

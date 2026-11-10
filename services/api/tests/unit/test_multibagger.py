"""Unit tests untuk R15 Multibagger Screener Engine."""
from app.analytics.multibagger import (
    MultibaggerInput,
    MultibaggerTier,
    score_multibagger,
)


def _inp(**kwargs) -> MultibaggerInput:
    """Helper — base input dengan semua field None, override lewat kwargs."""
    defaults = dict(
        instrument_id="test-id",
        symbol="TEST",
        exchange="IDX",
        sector="Consumer",
        pe_ratio=None,
        pb_ratio=None,
        roe=None,
        net_margin=None,
        gross_margin=None,
        revenue_growth_1y=None,
        revenue_growth_3y=None,
        eps_growth_1y=None,
        eps_growth_3y=None,
        debt_to_equity=None,
        current_ratio=None,
        fcf_yield=None,
        fcf_margin=None,
        price_vs_52w_high=None,
        relative_strength_1y=None,
        peer_pe_median=None,
        peer_roe_median=None,
    )
    defaults.update(kwargs)
    return MultibaggerInput(**defaults)


# ---------------------------------------------------------------------------
# INSUFFICIENT — data kurang
# ---------------------------------------------------------------------------

def test_insufficient_no_fields():
    result = score_multibagger(_inp())
    assert result.tier == MultibaggerTier.INSUFFICIENT
    assert result.total_score == 0.0
    assert result.data_completeness == 0.0


def test_insufficient_only_4_fields():
    result = score_multibagger(_inp(pe_ratio=15, roe=20, net_margin=15, pb_ratio=2))
    assert result.tier == MultibaggerTier.INSUFFICIENT


# ---------------------------------------------------------------------------
# STRONG tier
# ---------------------------------------------------------------------------

def test_strong_tier_all_excellent():
    result = score_multibagger(_inp(
        pe_ratio=12,
        pb_ratio=1.2,
        roe=30,
        net_margin=25,
        gross_margin=55,
        revenue_growth_1y=30,
        revenue_growth_3y=22,
        eps_growth_1y=25,
        debt_to_equity=0.2,
        current_ratio=2.5,
        fcf_yield=6,
    ))
    assert result.tier == MultibaggerTier.STRONG
    assert result.total_score >= 70
    assert len(result.components) == 4


def test_strong_tier_has_strengths():
    result = score_multibagger(_inp(
        pe_ratio=10,
        roe=28,
        net_margin=22,
        gross_margin=50,
        revenue_growth_1y=35,
        debt_to_equity=0.1,
        fcf_yield=7,
        pb_ratio=1.0,
        eps_growth_1y=30,
        current_ratio=3.0,
    ))
    assert len(result.strengths) > 0
    assert any("ROE" in s for s in result.strengths)


# ---------------------------------------------------------------------------
# MODERATE tier
# ---------------------------------------------------------------------------

def test_moderate_tier():
    result = score_multibagger(_inp(
        pe_ratio=18,
        roe=20,
        net_margin=14,
        revenue_growth_1y=18,
        debt_to_equity=0.4,
        fcf_yield=4,
        pb_ratio=1.8,
        eps_growth_1y=15,
        gross_margin=38,
        current_ratio=2.0,
    ))
    assert result.tier in (MultibaggerTier.MODERATE, MultibaggerTier.STRONG)
    assert result.total_score >= 50


# ---------------------------------------------------------------------------
# NOT_QUALIFIED
# ---------------------------------------------------------------------------

def test_not_qualified_expensive_low_roe():
    result = score_multibagger(_inp(
        pe_ratio=80,
        pb_ratio=8.0,
        roe=5,
        net_margin=2,
        gross_margin=10,
        revenue_growth_1y=-5,
        debt_to_equity=2.5,
        fcf_yield=-2,
        eps_growth_1y=-10,
        current_ratio=0.8,
    ))
    assert result.tier == MultibaggerTier.NOT_QUALIFIED
    assert result.total_score < 30


def test_not_qualified_has_concerns():
    result = score_multibagger(_inp(
        pe_ratio=90,
        pb_ratio=10.0,
        roe=3,
        net_margin=1,
        gross_margin=5,
        revenue_growth_1y=-20,
        debt_to_equity=3.0,
        fcf_yield=-5,
        eps_growth_1y=-15,
        current_ratio=0.5,
    ))
    assert len(result.concerns) > 0


# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------

def test_score_bounded_0_100():
    result = score_multibagger(_inp(
        pe_ratio=5,
        pb_ratio=0.5,
        roe=50,
        net_margin=40,
        gross_margin=70,
        revenue_growth_1y=100,
        revenue_growth_3y=80,
        eps_growth_1y=90,
        debt_to_equity=0.0,
        current_ratio=10.0,
        fcf_yield=20,
    ))
    assert 0 <= result.total_score <= 100


# ---------------------------------------------------------------------------
# Bank sektor — DER tidak dihukum
# ---------------------------------------------------------------------------

def test_bank_sector_der_not_penalized():
    bank = score_multibagger(_inp(
        sector="Financials",
        pe_ratio=12,
        pb_ratio=1.5,
        roe=18,
        net_margin=20,
        gross_margin=None,
        revenue_growth_1y=10,
        debt_to_equity=8.0,   # tinggi tapi wajar untuk bank
        current_ratio=None,
        fcf_yield=3,
        eps_growth_1y=12,
    ))
    non_bank = score_multibagger(_inp(
        sector="Consumer",
        pe_ratio=12,
        pb_ratio=1.5,
        roe=18,
        net_margin=20,
        gross_margin=None,
        revenue_growth_1y=10,
        debt_to_equity=8.0,   # tinggi dan dihukum untuk non-bank
        current_ratio=None,
        fcf_yield=3,
        eps_growth_1y=12,
    ))
    # Skor bank harus lebih tinggi atau sama karena DER tidak dihukum
    assert bank.total_score >= non_bank.total_score


# ---------------------------------------------------------------------------
# Peer PE discount meningkatkan skor
# ---------------------------------------------------------------------------

def test_peer_pe_discount_raises_score():
    no_peer = score_multibagger(_inp(
        pe_ratio=15,
        pb_ratio=1.5,
        roe=18,
        net_margin=14,
        gross_margin=35,
        revenue_growth_1y=12,
        debt_to_equity=0.4,
        eps_growth_1y=10,
        current_ratio=2.0,
        fcf_yield=4,
        peer_pe_median=None,
    ))
    with_peer = score_multibagger(_inp(
        pe_ratio=15,
        pb_ratio=1.5,
        roe=18,
        net_margin=14,
        gross_margin=35,
        revenue_growth_1y=12,
        debt_to_equity=0.4,
        eps_growth_1y=10,
        current_ratio=2.0,
        fcf_yield=4,
        peer_pe_median=25,  # 40% diskon dari peer
    ))
    assert with_peer.total_score >= no_peer.total_score


# ---------------------------------------------------------------------------
# Data completeness
# ---------------------------------------------------------------------------

def test_data_completeness_ratio():
    # 5 dari 10 field tersedia
    result = score_multibagger(_inp(
        pe_ratio=15,
        roe=18,
        net_margin=12,
        gross_margin=30,
        revenue_growth_1y=10,
    ))
    # completeness = 5/10 = 0.5
    assert result.data_completeness == 0.5


# ---------------------------------------------------------------------------
# Components tersedia
# ---------------------------------------------------------------------------

def test_four_components_returned():
    result = score_multibagger(_inp(
        pe_ratio=20,
        roe=15,
        net_margin=10,
        gross_margin=30,
        revenue_growth_1y=10,
        debt_to_equity=0.5,
        fcf_yield=3,
        pb_ratio=2.0,
        eps_growth_1y=8,
        current_ratio=1.8,
    ))
    assert len(result.components) == 4
    names = {c.name for c in result.components}
    assert names == {"growth", "profitability", "balance_sheet", "valuation"}


def test_multibagger_four_pipelines_and_reverse_scenarios():
    result = score_multibagger(_inp(
        pe_ratio=10.0,
        pb_ratio=1.2,
        roe=22.0,
        net_margin=18.0,
        gross_margin=45.0,
        revenue_growth_1y=28.0,
        revenue_growth_3y=15.0,
        eps_growth_1y=32.0,
        eps_growth_3y=14.0,
        debt_to_equity=0.25,
        current_ratio=2.2,
        fcf_yield=5.5,
        peer_pe_median=18.0,
    ))
    assert "QUALITY_COMPOUNDER" in result.pipelines_matched
    assert "EARNINGS_INFLECTION" in result.pipelines_matched
    assert "TURNAROUND" in result.pipelines_matched
    assert "UNDERAPPRECIATED_CATALYST" in result.pipelines_matched
    assert len(result.reverse_scenarios) == 4
    multiples = [s.target_multiple for s in result.reverse_scenarios]
    assert multiples == [2, 3, 5, 10]
    assert result.reverse_scenarios[0].required_eps_cagr_constant_pe_pct > 0

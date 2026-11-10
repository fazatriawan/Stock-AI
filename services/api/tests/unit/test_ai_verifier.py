"""Unit tests untuk Pass 3 Deterministic Claim Verifier (ANL-06 / PRD §19 Gate 5)."""
from datetime import datetime, timezone

from app.ai.adapter import verify_ai_claims
from app.ai.schemas import AIEnrichment, EvidenceBundle


def _make_bundle() -> EvidenceBundle:
    return EvidenceBundle(
        instrument_id="inst-bbca",
        canonical_symbol="IDX:BBCA",
        as_of=datetime(2026, 11, 10, tzinfo=timezone.utc),
        action="BUY",
        composite_score=74.5,
        hard_gate_status="PASS",
        hard_gate_reason=None,
        rsi_14=54.2,
        macd=12.5,
        sma_trend="BULLISH",
        return_1d=0.012,
        return_20d=0.045,
        volume_ratio=1.3,
        pe_ratio=18.5,
        pb_ratio=3.2,
        roe=0.21,
        sector="Financials",
        is_bank=True,
        factor_scores={"fundamental": 78.0, "valuation": 65.0, "technical": 80.0},
        bull_thesis_raw=["ROE tinggi 21.0% di atas rata-rata bank"],
        bear_case_raw=["Valuasi PB 3.2x relatif premium"],
        data_gaps=[],
        provider="yfinance",
        price_stale=False,
        integrity_status="CLEAN",
        integrity_conflicts_count=0,
        integrity_blocked_metrics=[],
        peer_pe_median=15.0,
        peer_pb_median=2.1,
        peer_roe_median=0.16,
        peer_count=4,
    )


def test_verifier_passes_grounded_claims() -> None:
    bundle = _make_bundle()
    enrichment = AIEnrichment(
        enriched_bull_points=[
            "ROE sebesar 21.0% lebih unggul dibanding median peer 16.0%.",
            "Momentum RSI 14 di level 54.2 mendukung tren kenaikan 20 hari sebesar 4.5%.",
        ],
        enriched_bear_points=[
            "Rasio P/B 3.2x berada di atas median peer 2.1x.",
        ],
        identified_risks=[
            "Risiko kenaikan biaya dana perbankan pada tahun 2026.",
        ],
        macro_context="Kebijakan suku bunga mempengaruhi NIM sektor perbankan.",
    )
    verified = verify_ai_claims(bundle, enrichment)
    assert verified.verification_status == "VERIFIED"
    assert verified.unverified_claims == []


def test_verifier_flags_hallucinated_numbers() -> None:
    bundle = _make_bundle()
    enrichment = AIEnrichment(
        enriched_bull_points=[
            "Target harga Rp45.500 dengan estimasi pertumbuhan laba 88.7% tahun depan.",
        ],
        enriched_bear_points=[],
        identified_risks=[],
    )
    verified = verify_ai_claims(bundle, enrichment)
    assert verified.verification_status == "NEEDS_REVIEW"
    assert len(verified.unverified_claims) >= 1
    assert any("CLAIM_VERIFIER" in note for note in verified.data_quality_notes)


def test_verifier_flags_forbidden_phrases() -> None:
    bundle = _make_bundle()
    enrichment = AIEnrichment(
        enriched_bull_points=[
            "Saham ini pasti multibagger dan bebas risiko untuk jangka panjang.",
        ],
        enriched_bear_points=[],
        identified_risks=[],
    )
    verified = verify_ai_claims(bundle, enrichment)
    assert verified.verification_status == "NEEDS_REVIEW"
    assert any("pasti multibagger" in c for c in verified.unverified_claims)
    assert any("bebas risiko" in c for c in verified.unverified_claims)


def test_verifier_skipped_when_enrichment_skipped() -> None:
    bundle = _make_bundle()
    enrichment = AIEnrichment(skipped=True, skip_reason="No API key")
    verified = verify_ai_claims(bundle, enrichment)
    assert verified.verification_status == "SKIPPED"

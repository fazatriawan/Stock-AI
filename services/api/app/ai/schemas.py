"""Schema untuk AI evidence bundle dan output enrichment."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class EvidenceBundle:
    """Input ke AI adapter — kumpulan fakta terverifikasi dari engine deterministik."""

    instrument_id: str
    canonical_symbol: str
    as_of: datetime

    # Dari engine deterministik — TIDAK boleh diubah AI
    action: str          # BUY/HOLD/SELL/WAIT/INSUFFICIENT_DATA
    composite_score: float
    hard_gate_status: str
    hard_gate_reason: Optional[str]

    # Snapshot teknikal (sudah dihitung, bukan raw)
    rsi_14: Optional[float]
    macd: Optional[float]
    sma_trend: str       # "BULLISH" / "BEARISH" / "NEUTRAL" / "UNKNOWN"
    return_1d: Optional[float]
    return_20d: Optional[float]
    volume_ratio: Optional[float]

    # Snapshot fundamental
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    roe: Optional[float]
    sector: Optional[str]
    is_bank: bool

    # Context
    factor_scores: dict          # {fundamental, valuation, technical, ...}
    bull_thesis_raw: list[str]   # dari engine deterministik
    bear_case_raw: list[str]     # dari engine deterministik
    data_gaps: list[str]

    # Metadata
    provider: str
    price_stale: bool


@dataclass
class AIEnrichment:
    """Output dari AI adapter — pengayaan kontekstual, bukan override rekomendasi."""

    # Enriched thesis (AI boleh memperkaya, bukan mengubah action)
    enriched_bull_points: list[str] = field(default_factory=list)
    enriched_bear_points: list[str] = field(default_factory=list)

    # Risiko tambahan yang diidentifikasi AI
    identified_risks: list[str] = field(default_factory=list)

    # Konteks makro singkat
    macro_context: Optional[str] = None

    # Flag kualitas data dari AI
    data_quality_notes: list[str] = field(default_factory=list)

    # Metadata AI call
    model_used: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: int = 0
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class AIBudgetState:
    """Pelacak penggunaan AI untuk circuit breaker."""
    calls_this_hour: int = 0
    tokens_this_hour: int = 0
    consecutive_errors: int = 0
    last_reset_at: Optional[datetime] = None

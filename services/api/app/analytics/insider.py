"""
R14 — Insider Transaction Engine.
Scoring berdasarkan transaksi orang dalam dari keterbukaan informasi publik IDX/SEC.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional


class InsiderSentiment(str, Enum):
    STRONG_BUY  = "STRONG_BUY"   # cluster buy ≥3 orang atau net buy >1% saham beredar
    BUY         = "BUY"           # net buy positif, 1-2 orang
    NEUTRAL     = "NEUTRAL"       # seimbang atau tidak ada transaksi baru
    SELL        = "SELL"          # net sell oleh 1-2 orang
    STRONG_SELL = "STRONG_SELL"   # cluster sell ≥3 orang atau net sell >1% saham beredar
    NO_DATA     = "NO_DATA"


ROLE_WEIGHT = {
    "DIRECTOR": 1.5,
    "COMMISSIONER": 1.2,
    "MAJOR_SHAREHOLDER": 1.0,
    "OTHER": 0.5,
}

CLUSTER_WINDOW_DAYS = 30
STRONG_CLUSTER_MIN  = 3        # jumlah insider berbeda dalam window
STRONG_VOLUME_PCT   = 0.01     # 1% dari shares_outstanding


@dataclass
class InsiderTxSummary:
    insider_name: str
    insider_role: str
    transaction_type: str
    transaction_date: date
    shares: int
    price_per_share: Optional[float]
    total_value: Optional[float]
    currency: str
    shares_owned_after: Optional[int]
    ownership_pct_after: Optional[float]
    disclosure_date: Optional[date]
    source_url: Optional[str] = None


@dataclass
class InsiderSignal:
    sentiment: InsiderSentiment
    score: float                      # -1.0 (strong sell) → +1.0 (strong buy)
    net_buy_shares: int
    net_sell_shares: int
    unique_buyers: int
    unique_sellers: int
    cluster_detected: bool
    cluster_type: Optional[str]       # "BUY_CLUSTER" / "SELL_CLUSTER"
    lookback_days: int
    transactions_analyzed: int
    latest_date: Optional[date]
    summary_text: str
    transactions: list[InsiderTxSummary] = field(default_factory=list)


def analyze_insider_signal(
    transactions: list[InsiderTxSummary],
    as_of: date,
    lookback_days: int = 180,
    shares_outstanding: Optional[int] = None,
) -> InsiderSignal:
    """
    Hitung sinyal insider dari daftar transaksi historis.
    Hanya transaksi BUY dan SELL yang di-score (GRANT/EXERCISE diabaikan untuk net).
    """
    cutoff = as_of - timedelta(days=lookback_days)
    recent = [t for t in transactions if t.transaction_date >= cutoff]

    if not recent:
        return InsiderSignal(
            sentiment=InsiderSentiment.NO_DATA,
            score=0.0,
            net_buy_shares=0,
            net_sell_shares=0,
            unique_buyers=0,
            unique_sellers=0,
            cluster_detected=False,
            cluster_type=None,
            lookback_days=lookback_days,
            transactions_analyzed=0,
            latest_date=None,
            summary_text=f"Tidak ada transaksi insider dalam {lookback_days} hari terakhir.",
            transactions=[],
        )

    buyers:  set[str] = set()
    sellers: set[str] = set()
    net_buy  = 0
    net_sell = 0
    weighted_score = 0.0

    for tx in recent:
        w = ROLE_WEIGHT.get(tx.insider_role, 0.5)
        if tx.transaction_type == "BUY":
            buyers.add(tx.insider_name)
            net_buy += tx.shares
            weighted_score += w * tx.shares
        elif tx.transaction_type == "SELL":
            sellers.add(tx.insider_name)
            net_sell += tx.shares
            weighted_score -= w * tx.shares

    # Cluster detection dalam CLUSTER_WINDOW_DAYS
    cluster_cutoff = as_of - timedelta(days=CLUSTER_WINDOW_DAYS)
    cluster_window = [t for t in recent if t.transaction_date >= cluster_cutoff]
    cluster_buyers  = {t.insider_name for t in cluster_window if t.transaction_type == "BUY"}
    cluster_sellers = {t.insider_name for t in cluster_window if t.transaction_type == "SELL"}

    buy_cluster  = len(cluster_buyers)  >= STRONG_CLUSTER_MIN
    sell_cluster = len(cluster_sellers) >= STRONG_CLUSTER_MIN

    # Volume cluster vs shares outstanding
    if shares_outstanding and shares_outstanding > 0:
        buy_pct  = net_buy  / shares_outstanding
        sell_pct = net_sell / shares_outstanding
        strong_volume_buy  = buy_pct  >= STRONG_VOLUME_PCT
        strong_volume_sell = sell_pct >= STRONG_VOLUME_PCT
    else:
        strong_volume_buy = strong_volume_sell = False

    # Normalize score ke [-1, 1]
    total_volume = net_buy + net_sell
    if total_volume > 0:
        raw_score = (net_buy - net_sell) / total_volume
    else:
        raw_score = 0.0

    # Tentukan sentiment
    is_strong_buy  = buy_cluster  or strong_volume_buy
    is_strong_sell = sell_cluster or strong_volume_sell

    if raw_score > 0:
        sentiment = InsiderSentiment.STRONG_BUY if is_strong_buy else InsiderSentiment.BUY
    elif raw_score < 0:
        sentiment = InsiderSentiment.STRONG_SELL if is_strong_sell else InsiderSentiment.SELL
    else:
        sentiment = InsiderSentiment.NEUTRAL

    cluster_type = None
    if buy_cluster:
        cluster_type = "BUY_CLUSTER"
    elif sell_cluster:
        cluster_type = "SELL_CLUSTER"

    latest = max(t.transaction_date for t in recent)

    # Summary text
    parts = []
    if net_buy > 0:
        parts.append(f"{len(buyers)} insider membeli {net_buy:,} saham")
    if net_sell > 0:
        parts.append(f"{len(sellers)} insider menjual {net_sell:,} saham")
    if cluster_type == "BUY_CLUSTER":
        parts.append(f"cluster beli terdeteksi ({len(cluster_buyers)} orang dalam {CLUSTER_WINDOW_DAYS}h)")
    elif cluster_type == "SELL_CLUSTER":
        parts.append(f"cluster jual terdeteksi ({len(cluster_sellers)} orang dalam {CLUSTER_WINDOW_DAYS}h)")
    summary_text = "; ".join(parts) if parts else "Tidak ada sinyal signifikan."

    return InsiderSignal(
        sentiment=sentiment,
        score=round(raw_score, 4),
        net_buy_shares=net_buy,
        net_sell_shares=net_sell,
        unique_buyers=len(buyers),
        unique_sellers=len(sellers),
        cluster_detected=bool(cluster_type),
        cluster_type=cluster_type,
        lookback_days=lookback_days,
        transactions_analyzed=len(recent),
        latest_date=latest,
        summary_text=summary_text,
        transactions=recent,
    )

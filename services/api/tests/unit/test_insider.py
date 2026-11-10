"""Unit tests untuk R14 Insider Transaction Engine."""
from datetime import date, timedelta
from app.analytics.insider import (
    InsiderSentiment,
    InsiderTxSummary,
    analyze_insider_signal,
)

TODAY = date(2026, 11, 4)


def _tx(name, role, tx_type, days_ago, shares, price=None):
    return InsiderTxSummary(
        insider_name=name,
        insider_role=role,
        transaction_type=tx_type,
        transaction_date=TODAY - timedelta(days=days_ago),
        shares=shares,
        price_per_share=price,
        total_value=shares * price if price else None,
        currency="IDR",
        shares_owned_after=None,
        ownership_pct_after=None,
        disclosure_date=None,
    )


# ---------------------------------------------------------------------------
# NO_DATA
# ---------------------------------------------------------------------------

def test_no_transactions_returns_no_data():
    sig = analyze_insider_signal([], as_of=TODAY)
    assert sig.sentiment == InsiderSentiment.NO_DATA
    assert sig.score == 0.0
    assert sig.transactions_analyzed == 0


def test_transactions_outside_lookback_ignored():
    txs = [_tx("Budi", "DIRECTOR", "BUY", 200, 100_000)]
    sig = analyze_insider_signal(txs, as_of=TODAY, lookback_days=180)
    assert sig.sentiment == InsiderSentiment.NO_DATA


# ---------------------------------------------------------------------------
# BUY signals
# ---------------------------------------------------------------------------

def test_single_director_buy():
    txs = [_tx("Budi", "DIRECTOR", "BUY", 10, 500_000, 9000)]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert sig.sentiment == InsiderSentiment.BUY
    assert sig.score > 0
    assert sig.unique_buyers == 1
    assert sig.net_buy_shares == 500_000


def test_cluster_buy_three_directors():
    txs = [
        _tx("A", "DIRECTOR", "BUY", 5, 100_000),
        _tx("B", "DIRECTOR", "BUY", 7, 150_000),
        _tx("C", "COMMISSIONER", "BUY", 10, 200_000),
    ]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert sig.sentiment == InsiderSentiment.STRONG_BUY
    assert sig.cluster_detected is True
    assert sig.cluster_type == "BUY_CLUSTER"


def test_strong_buy_by_volume(monkeypatch):
    # Net buy > 1% dari 10 juta shares outstanding
    txs = [_tx("Budi", "DIRECTOR", "BUY", 5, 150_000)]
    sig = analyze_insider_signal(txs, as_of=TODAY, shares_outstanding=10_000_000)
    assert sig.sentiment == InsiderSentiment.STRONG_BUY


# ---------------------------------------------------------------------------
# SELL signals
# ---------------------------------------------------------------------------

def test_single_director_sell():
    txs = [_tx("Siti", "DIRECTOR", "SELL", 15, 300_000, 9500)]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert sig.sentiment == InsiderSentiment.SELL
    assert sig.score < 0
    assert sig.unique_sellers == 1


def test_cluster_sell_three_insiders():
    txs = [
        _tx("A", "DIRECTOR", "SELL", 3, 100_000),
        _tx("B", "COMMISSIONER", "SELL", 5, 200_000),
        _tx("C", "DIRECTOR", "SELL", 8, 150_000),
    ]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert sig.sentiment == InsiderSentiment.STRONG_SELL
    assert sig.cluster_type == "SELL_CLUSTER"


# ---------------------------------------------------------------------------
# NEUTRAL
# ---------------------------------------------------------------------------

def test_equal_buy_sell_neutral():
    txs = [
        _tx("A", "DIRECTOR", "BUY", 10, 100_000),
        _tx("B", "DIRECTOR", "SELL", 10, 100_000),
    ]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert sig.sentiment == InsiderSentiment.NEUTRAL
    assert sig.score == 0.0


# ---------------------------------------------------------------------------
# GRANT / EXERCISE diabaikan untuk net score
# ---------------------------------------------------------------------------

def test_grant_exercise_not_counted_in_net():
    txs = [
        _tx("A", "DIRECTOR", "GRANT", 5, 1_000_000),
        _tx("B", "DIRECTOR", "EXERCISE", 5, 500_000),
    ]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert sig.net_buy_shares == 0
    assert sig.net_sell_shares == 0
    assert sig.sentiment == InsiderSentiment.NEUTRAL


# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------

def test_score_bounded():
    txs = [_tx(f"X{i}", "DIRECTOR", "BUY", i + 1, 100_000) for i in range(5)]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert -1.0 <= sig.score <= 1.0


# ---------------------------------------------------------------------------
# Summary text
# ---------------------------------------------------------------------------

def test_summary_text_contains_buyer_count():
    txs = [
        _tx("A", "DIRECTOR", "BUY", 5, 100_000),
        _tx("B", "COMMISSIONER", "BUY", 7, 50_000),
    ]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert "2 insider membeli" in sig.summary_text


def test_cluster_summary_text():
    txs = [
        _tx("A", "DIRECTOR", "BUY", 2, 100_000),
        _tx("B", "DIRECTOR", "BUY", 5, 100_000),
        _tx("C", "COMMISSIONER", "BUY", 10, 100_000),
    ]
    sig = analyze_insider_signal(txs, as_of=TODAY)
    assert "cluster" in sig.summary_text

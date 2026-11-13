"""
FREE-12: Empty-ingest classifier — deteksi mengapa provider kembali 0 bar.

Ketika refresh_stale_instruments memanggil ingest_ohlcv dan mendapat 0 bar,
kita perlu tahu apakah:
  - Ticker tidak ditemukan di provider → UNAVAILABLE (hentikan retry)
  - Provider sedang rate-limited → QUOTA_EXHAUSTED (coba lagi nanti)
  - Error jaringan sementara → tetap STALE (retry malam berikutnya)

Heuristik berbasis pesan error dan nama symbol — tidak ada API call tambahan.
Semua keputusan bersifat konservatif: jika tidak yakin → tetap STALE.

TIDAK melakukan: auto-trade, login broker, panggilan API berbayar.
"""
from __future__ import annotations

import re
from typing import Optional

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# Pola pesan error yfinance yang menandakan ticker benar-benar tidak ada
_UNAVAILABLE_PATTERNS = [
    r"no data found",
    r"no timezone found",
    r"symbol may be delisted",
    r"delisted",
    r"no price data",
    r"possibly delisted",
    r"not found",
    r"invalid ticker",
    r"no historical data",
]

# Pola pesan error yang menandakan rate-limit / quota
_QUOTA_PATTERNS = [
    r"too many requests",
    r"rate limit",
    r"429",
    r"quota exceeded",
    r"throttl",
]


def classify_empty_ingest(
    symbol: str,
    error: Optional[Exception] = None,
) -> str:
    """
    Klasifikasikan mengapa ingest mengembalikan 0 bar.

    Returns:
        "UNAVAILABLE"      — ticker tidak ada / delisted → hentikan retry
        "QUOTA_EXHAUSTED"  — provider rate-limited → coba lagi nanti
        "STALE"            — error sementara / tidak diketahui → tetap retry

    Args:
        symbol: canonical_symbol instrumen (mis. "IDX:BBCA", "US:AAPL")
        error: exception yang tertangkap saat ingest (None = tidak ada error,
               provider hanya kembali kosong)
    """
    error_msg = str(error).lower() if error else ""

    # Cek quota exhausted dulu (lebih spesifik)
    for pat in _QUOTA_PATTERNS:
        if re.search(pat, error_msg):
            log.info(
                "empty_ingest.quota_exhausted",
                symbol=symbol,
                pattern=pat,
            )
            return "QUOTA_EXHAUSTED"

    # Cek unavailable
    for pat in _UNAVAILABLE_PATTERNS:
        if re.search(pat, error_msg):
            log.info(
                "empty_ingest.unavailable",
                symbol=symbol,
                pattern=pat,
            )
            return "UNAVAILABLE"

    # Jika tidak ada error TAPI 0 bar → ticker kemungkinan tidak tercakup provider
    # (misalnya symbol IDX yang tidak ada di Yahoo Finance)
    if error is None:
        log.info("empty_ingest.no_data_no_error", symbol=symbol)
        return "UNAVAILABLE"

    # Error jaringan atau lainnya → tetap STALE untuk retry
    log.info("empty_ingest.transient_error", symbol=symbol, error=error_msg[:120])
    return "STALE"


async def mark_empty_bars(
    db: AsyncSession,
    instrument_id: str,
    new_status: str,
) -> int:
    """
    Update semua bar STALE milik instrument_id ke new_status.

    new_status harus salah satu dari: "UNAVAILABLE", "QUOTA_EXHAUSTED".
    Bar dengan status lain tidak tersentuh.

    Returns: jumlah bar yang diupdate.
    """
    from app.db.models import PriceBar

    if new_status not in ("UNAVAILABLE", "QUOTA_EXHAUSTED"):
        raise ValueError(f"new_status tidak valid: {new_status!r}")

    stmt = (
        update(PriceBar)
        .where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.freshness_status == "STALE",
        )
        .values(freshness_status=new_status)
    )
    result = await db.execute(stmt)
    marked = result.rowcount
    log.info(
        "empty_ingest.bars_marked",
        instrument_id=instrument_id,
        new_status=new_status,
        count=marked,
    )
    return marked

"""
FREE-14: Provider fallback chain untuk OHLCV ingest.

Ketika primary provider (yfinance) mengembalikan 0 bar atau raise exception,
coba provider berikutnya dalam urutan prioritas dari ProviderRegistry.

Prinsip:
- Hanya provider gratis (tunduk pada budget guard di registry).
- Fallback tidak silent — setiap percobaan dan hasilnya di-log.
- Jika semua provider gagal, kembalikan None dan caller bertanggung jawab
  memutuskan status akhir (UNAVAILABLE / QUOTA_EXHAUSTED via empty_ingest).
- Tidak pernah mencoba mock provider sebagai fallback untuk data live
  (mock tidak bisa mengisi gap data nyata).

TIDAK melakukan: auto-trade, login broker, panggilan API berbayar tanpa izin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.ohlcv import OHLCVIngestionResult, ingest_ohlcv
from app.providers.base import MarketDataProvider
from app.providers.registry import get_provider_registry

log = structlog.get_logger(__name__)


@dataclass
class FallbackIngestResult:
    """Hasil ingest dengan info provider mana yang berhasil."""
    ohlcv: OHLCVIngestionResult
    provider_used: str
    providers_tried: list[str] = field(default_factory=list)
    fallback_used: bool = False   # True jika bukan provider pertama yang berhasil


async def ingest_with_fallback(
    db: AsyncSession,
    instrument,  # app.db.models.Instrument
    market: str,
    start: date,
    end: date,
    force: bool = False,
    skip_mock: bool = True,
) -> Optional[FallbackIngestResult]:
    """
    Coba ingest OHLCV menggunakan semua provider free untuk market secara berurutan.

    Args:
        db: AsyncSession
        instrument: Instrument object
        market: "IDX" atau "US"
        start / end: rentang tanggal
        force: lewatkan cache / duplicate check
        skip_mock: jangan gunakan MockProvider sebagai fallback (default True)

    Returns:
        FallbackIngestResult jika ada provider yang berhasil mengembalikan >= 1 bar,
        None jika semua provider gagal atau kembalikan 0 bar.
    """
    registry = get_provider_registry()
    providers: list[MarketDataProvider] = registry.get_ordered(market)

    if not providers:
        log.warning("fallback.no_providers", market=market, symbol=instrument.canonical_symbol)
        return None

    tried: list[str] = []

    for idx, provider in enumerate(providers):
        provider_name = getattr(provider, "name", type(provider).__name__)

        # Skip mock provider kecuali diminta
        if skip_mock and "mock" in provider_name.lower():
            log.debug("fallback.skip_mock", provider=provider_name)
            continue

        tried.append(provider_name)

        try:
            result = await ingest_ohlcv(db, instrument, provider, start, end, force=force)

            if result.inserted > 0 or result.skipped > 0:
                log.info(
                    "fallback.provider_ok",
                    symbol=instrument.canonical_symbol,
                    provider=provider_name,
                    inserted=result.inserted,
                    skipped=result.skipped,
                    attempt=idx + 1,
                )
                return FallbackIngestResult(
                    ohlcv=result,
                    provider_used=provider_name,
                    providers_tried=tried,
                    fallback_used=(idx > 0),
                )

            log.info(
                "fallback.provider_empty",
                symbol=instrument.canonical_symbol,
                provider=provider_name,
                attempt=idx + 1,
            )

        except Exception as exc:
            log.warning(
                "fallback.provider_error",
                symbol=instrument.canonical_symbol,
                provider=provider_name,
                error=str(exc),
                attempt=idx + 1,
            )

    log.warning(
        "fallback.all_failed",
        symbol=instrument.canonical_symbol,
        market=market,
        providers_tried=tried,
    )
    return None

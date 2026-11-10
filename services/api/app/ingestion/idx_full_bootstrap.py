"""
IDX Full Bootstrap — unduh ~200+ ticker IDX ke database.

Strategi:
1. Coba Sectors API /v1/companies/?exchange=IDX (jika sectors_enabled + key tersedia)
2. Fallback ke daftar hardcoded LQ45 + IDX80 + papan utama ~200 ticker
3. Download histori OHLCV via yfinance (suffix .JK otomatis)
4. Upsert instrument + price_bars ke database

TIDAK melakukan: auto-trade, login broker, scraping private.
Semua data dari public API (Yahoo Finance / Sectors.app public endpoint).
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.domain.instruments import upsert_instrument
from app.ingestion.ohlcv import ingest_ohlcv
from app.providers.base import InstrumentInfo
from app.providers.registry import get_provider_registry

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Daftar hardcoded IDX tickers — LQ45 + IDX80 + sektoral pilihan
# Digunakan sebagai fallback jika Sectors API tidak tersedia
# ---------------------------------------------------------------------------
IDX_HARDCODED_TICKERS: list[str] = [
    # LQ45 (likuiditas tinggi)
    "BBCA", "BBRI", "BMRI", "TLKM", "ASII", "BYAN", "GOTO", "BREN",
    "AMMN", "MDKA", "EXCL", "ICBP", "INDF", "KLBF", "CPIN", "UNVR",
    "SIDO", "MAPI", "ACES", "ERAA", "SMGR", "INTP", "PTBA", "ADRO",
    "BUMI", "BRPT", "TPIA", "ESSA", "HRUM", "ITMG", "MEDC", "PGAS",
    "ANTM", "INCO", "TINS", "PSAB", "BJTM", "BBNI", "BJBR", "MEGA",
    "PNLF", "TRIM", "LIFE", "MYOR", "TSPC", "KAEF",

    # IDX80 tambahan
    "FILM", "SCMA", "MNCN", "EMTK", "VIVA", "RALS", "LPPF", "MAPA",
    "HERO", "AMRT", "DMAS", "CTRA", "BSDE", "PWON", "SMRA", "MTLA",
    "JSMR", "WIKA", "WSKT", "ADHI", "PTPP", "WTON", "ACST", "DGNS",
    "HEAL", "MIKA", "SILO", "MDLN", "KIJA", "LPKR", "BEST", "GPRA",

    # Perbankan & Keuangan
    "BNII", "BNGA", "NISP", "BABP", "BMAS", "NOBU", "BINA", "AGRO",
    "BRIS", "BTPS", "BCAP", "PANS", "RELI", "MFIN",

    # Konsumer & Retail
    "GGRM", "HMSP", "WIIM", "IIKP", "PYFA", "KDSI", "CLEO", "FOOD",
    "TGKA", "RANC", "STTP", "AISA", "ALTO", "BTEK", "IGAR", "SKLT",

    # Energi & Tambang
    "ELSA", "RUIS", "AKRA", "ISAT", "FREN", "CBMF", "SMBR", "MITI",
    "GEMS", "DSSA", "BSSR", "MBAP", "FIRE", "ATPK", "GTBO",

    # Properti & Konstruksi
    "APLN", "COWL", "DILD", "EMDE", "FMII", "GAMA", "GWSA", "JRPT",
    "MKPI", "MDLN", "NIRO", "PAMG", "PLIN", "RODA", "TARA",

    # Teknologi & Telekomunikasi
    "BUKA", "BBSS", "NETV", "EDGE", "AXIO", "DCII", "TBIG", "TOWR",

    # Healthcare
    "DGNS", "HEAL", "MIKA", "SILO", "SOHO", "PEHA", "INAF", "MERK",
]

# Hapus duplikat
IDX_HARDCODED_TICKERS = list(dict.fromkeys(IDX_HARDCODED_TICKERS))


async def _fetch_sectors_ticker_list() -> list[dict]:
    """
    Ambil daftar saham dari Sectors API /v1/companies/?exchange=IDX.
    Returns list of dicts dengan keys: ticker, company_name, sector, sub_sector.
    Returns [] jika gagal atau tidak dikonfigurasi.
    """
    settings = get_settings()
    if not settings.sectors_enabled or not settings.sectors_api_key:
        return []

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                "https://api.sectors.app/v1/companies/",
                params={"exchange": "IDX"},
                headers={"Authorization": f"apikey {settings.sectors_api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                log.info("sectors.companies_fetched", count=len(data))
                return data if isinstance(data, list) else []
            else:
                log.warning("sectors.companies_fetch_failed", status=resp.status_code)
                return []
    except Exception as exc:
        log.warning("sectors.companies_fetch_error", error=str(exc))
        return []


def _sectors_to_instrument_info(item: dict) -> Optional[InstrumentInfo]:
    """Konversi satu row Sectors API ke InstrumentInfo."""
    ticker = item.get("ticker") or item.get("symbol") or ""
    if not ticker:
        return None
    ticker = ticker.upper().replace(".JK", "")
    return InstrumentInfo(
        canonical_symbol=f"IDX:{ticker}",
        local_symbol=ticker,
        exchange="IDX",
        country="ID",
        currency="IDR",
        timezone="Asia/Jakarta",
        company_name=item.get("company_name") or item.get("name") or ticker,
        sector=item.get("sector") or None,
        industry=item.get("sub_sector") or item.get("industry") or None,
        asset_type="EQUITY",
        provider="sectors",
    )


def _hardcoded_to_instrument_info(ticker: str) -> InstrumentInfo:
    """Buat InstrumentInfo minimal dari ticker hardcoded."""
    return InstrumentInfo(
        canonical_symbol=f"IDX:{ticker}",
        local_symbol=ticker,
        exchange="IDX",
        country="ID",
        currency="IDR",
        timezone="Asia/Jakarta",
        company_name=ticker,
        asset_type="EQUITY",
        provider="yfinance",
    )


async def run_idx_full_bootstrap(
    db: AsyncSession,
    days_history: Optional[int] = None,
    max_tickers: int = 300,
    dry_run: bool = False,
) -> dict:
    """
    Bootstrap ~200+ ticker IDX ke database.

    Args:
        db: AsyncSession aktif
        days_history: Berapa hari histori OHLCV (default: dari config)
        max_tickers: Batas atas jumlah ticker yang diproses
        dry_run: Hanya hitung, tidak ingest ke DB

    Returns dict ringkasan: total_tickers, inserted, skipped, errors
    """
    settings = get_settings()
    if days_history is None:
        days_history = settings.idx_bootstrap_days

    end_date = date.today()
    start_date = end_date - timedelta(days=days_history)

    log.info(
        "idx_bootstrap.start",
        days_history=days_history,
        start_date=str(start_date),
        end_date=str(end_date),
        dry_run=dry_run,
    )

    # 1. Coba Sectors API untuk daftar lengkap
    sectors_list = await _fetch_sectors_ticker_list()
    instruments_to_process: list[InstrumentInfo] = []

    if sectors_list:
        for item in sectors_list[:max_tickers]:
            info = _sectors_to_instrument_info(item)
            if info:
                instruments_to_process.append(info)
        log.info("idx_bootstrap.using_sectors_list", count=len(instruments_to_process))
    else:
        # Fallback ke hardcoded
        for ticker in IDX_HARDCODED_TICKERS[:max_tickers]:
            instruments_to_process.append(_hardcoded_to_instrument_info(ticker))
        log.info("idx_bootstrap.using_hardcoded_list", count=len(instruments_to_process))

    if dry_run:
        return {"total_tickers": len(instruments_to_process), "dry_run": True}

    # 2. Seed data sources
    from sqlalchemy import text
    default_sources = [
        ("src_yfinance", "https://finance.yahoo.com", "Yahoo Finance", "yfinance provider"),
        ("src_sectors", "https://sectors.app", "Sectors.app", "Sectors Financial API"),
        ("src_manual", None, "Manual Entry", "data diinput manual"),
        ("src_mock", None, "Mock Provider", "synthetic test data"),
        ("src_fred", "https://fred.stlouisfed.org", "Federal Reserve (FRED)", "FRED macro data"),
    ]
    for src_id, url, publisher, title in default_sources:
        await db.execute(text("""
            INSERT INTO sources (id, url, publisher, title, license_class, primary_or_secondary)
            VALUES (:id, :url, :publisher, :title, 'THIRD_PARTY', 'SECONDARY')
            ON CONFLICT (id) DO NOTHING
        """), {"id": src_id, "url": url, "publisher": publisher, "title": title})

    # 3. Upsert instruments ke DB
    registry = get_provider_registry()
    provider = registry.get_primary("IDX")

    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    for info in instruments_to_process:
        try:
            instrument = await upsert_instrument(db, info)
            await db.flush()

            # 4. Ingest OHLCV dari yfinance
            ohlcv_result = await ingest_ohlcv(
                db=db,
                instrument=instrument,
                provider=provider,
                start=start_date,
                end=end_date,
            )
            total_inserted += ohlcv_result.inserted
            total_skipped += ohlcv_result.skipped
            total_errors += len(ohlcv_result.validation_errors)

            log.debug(
                "idx_bootstrap.ticker_done",
                symbol=info.canonical_symbol,
                bars_inserted=ohlcv_result.inserted,
            )

        except Exception as exc:
            total_errors += 1
            log.warning(
                "idx_bootstrap.ticker_error",
                symbol=getattr(info, "canonical_symbol", "?"),
                error=str(exc),
            )

    await db.commit()

    summary = {
        "total_tickers": len(instruments_to_process),
        "bars_inserted": total_inserted,
        "bars_skipped": total_skipped,
        "errors": total_errors,
        "start_date": str(start_date),
        "end_date": str(end_date),
    }
    log.info("idx_bootstrap.complete", **summary)
    return summary


async def run_bootstrap_standalone() -> None:
    """Entry point standalone — jalankan via `python -m app.ingestion.idx_full_bootstrap`."""
    async with AsyncSessionLocal() as db:
        summary = await run_idx_full_bootstrap(db)
        print(f"Bootstrap selesai: {summary}")


if __name__ == "__main__":
    asyncio.run(run_bootstrap_standalone())

"""
US Stocks Bootstrap — seed ~90 ticker US + ETF populer ke database.

Strategi:
1. Daftar hardcoded S&P 500 pilihan + ETF likuid (90 ticker)
2. Download histori OHLCV via yfinance (tanpa suffix untuk US)
3. Upsert instrument + price_bars ke database

TIDAK melakukan: auto-trade, login broker, scraping private.
Semua data dari Yahoo Finance (gratis, tanpa API key).
"""
from __future__ import annotations

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

# (name, exchange)
US_HARDCODED_TICKERS: dict[str, tuple[str, str]] = {
    # Mega-cap tech
    "AAPL":  ("Apple Inc.", "NASDAQ"),
    "MSFT":  ("Microsoft Corp.", "NASDAQ"),
    "NVDA":  ("NVIDIA Corp.", "NASDAQ"),
    "GOOGL": ("Alphabet Inc. Class A", "NASDAQ"),
    "AMZN":  ("Amazon.com Inc.", "NASDAQ"),
    "META":  ("Meta Platforms Inc.", "NASDAQ"),
    "TSLA":  ("Tesla Inc.", "NASDAQ"),
    "AVGO":  ("Broadcom Inc.", "NASDAQ"),
    # Financials
    "JPM":   ("JPMorgan Chase & Co.", "NYSE"),
    "BAC":   ("Bank of America Corp.", "NYSE"),
    "WFC":   ("Wells Fargo & Co.", "NYSE"),
    "GS":    ("Goldman Sachs Group", "NYSE"),
    "MS":    ("Morgan Stanley", "NYSE"),
    "V":     ("Visa Inc.", "NYSE"),
    "MA":    ("Mastercard Inc.", "NYSE"),
    "BRK-B": ("Berkshire Hathaway B", "NYSE"),
    # Healthcare
    "JNJ":   ("Johnson & Johnson", "NYSE"),
    "UNH":   ("UnitedHealth Group", "NYSE"),
    "LLY":   ("Eli Lilly & Co.", "NYSE"),
    "ABBV":  ("AbbVie Inc.", "NYSE"),
    "MRK":   ("Merck & Co.", "NYSE"),
    "PFE":   ("Pfizer Inc.", "NYSE"),
    "TMO":   ("Thermo Fisher Scientific", "NYSE"),
    "ABT":   ("Abbott Laboratories", "NYSE"),
    # Consumer discretionary
    "WMT":   ("Walmart Inc.", "NYSE"),
    "COST":  ("Costco Wholesale Corp.", "NASDAQ"),
    "MCD":   ("McDonald's Corp.", "NYSE"),
    "NKE":   ("Nike Inc.", "NYSE"),
    "SBUX":  ("Starbucks Corp.", "NASDAQ"),
    "TGT":   ("Target Corp.", "NYSE"),
    "HD":    ("Home Depot Inc.", "NYSE"),
    # Consumer staples
    "PG":    ("Procter & Gamble Co.", "NYSE"),
    "KO":    ("Coca-Cola Co.", "NYSE"),
    "PEP":   ("PepsiCo Inc.", "NASDAQ"),
    "PM":    ("Philip Morris International", "NYSE"),
    # Industrials
    "HON":   ("Honeywell International", "NASDAQ"),
    "CAT":   ("Caterpillar Inc.", "NYSE"),
    "BA":    ("Boeing Co.", "NYSE"),
    "RTX":   ("RTX Corp.", "NYSE"),
    "LMT":   ("Lockheed Martin Corp.", "NYSE"),
    "UPS":   ("United Parcel Service", "NYSE"),
    "FDX":   ("FedEx Corp.", "NYSE"),
    "GE":    ("GE Aerospace", "NYSE"),
    # Energy
    "XOM":   ("Exxon Mobil Corp.", "NYSE"),
    "CVX":   ("Chevron Corp.", "NYSE"),
    "COP":   ("ConocoPhillips", "NYSE"),
    "OXY":   ("Occidental Petroleum", "NYSE"),
    # Semiconductors
    "AMD":   ("Advanced Micro Devices", "NASDAQ"),
    "INTC":  ("Intel Corp.", "NASDAQ"),
    "QCOM":  ("Qualcomm Inc.", "NASDAQ"),
    "TXN":   ("Texas Instruments", "NASDAQ"),
    "MU":    ("Micron Technology", "NASDAQ"),
    "AMAT":  ("Applied Materials", "NASDAQ"),
    # Cloud / Software / AI
    "CRM":   ("Salesforce Inc.", "NYSE"),
    "ORCL":  ("Oracle Corp.", "NYSE"),
    "ADBE":  ("Adobe Inc.", "NASDAQ"),
    "NOW":   ("ServiceNow Inc.", "NYSE"),
    "SNOW":  ("Snowflake Inc.", "NYSE"),
    "PLTR":  ("Palantir Technologies", "NYSE"),
    "NET":   ("Cloudflare Inc.", "NYSE"),
    "DDOG":  ("Datadog Inc.", "NASDAQ"),
    # E-Commerce / Internet
    "SHOP":  ("Shopify Inc.", "NYSE"),
    "EBAY":  ("eBay Inc.", "NASDAQ"),
    # Media & Entertainment
    "NFLX":  ("Netflix Inc.", "NASDAQ"),
    "DIS":   ("Walt Disney Co.", "NYSE"),
    "CMCSA": ("Comcast Corp.", "NASDAQ"),
    # Payments & Fintech
    "PYPL":  ("PayPal Holdings", "NASDAQ"),
    "SQ":    ("Block Inc.", "NYSE"),
    "COIN":  ("Coinbase Global", "NASDAQ"),
    # Mobility
    "UBER":  ("Uber Technologies", "NYSE"),
    "ABNB":  ("Airbnb Inc.", "NASDAQ"),
    # Telecom
    "T":     ("AT&T Inc.", "NYSE"),
    "VZ":    ("Verizon Communications", "NYSE"),
    "TMUS":  ("T-Mobile US", "NASDAQ"),
    # Utilities
    "NEE":   ("NextEra Energy", "NYSE"),
    "DUK":   ("Duke Energy Corp.", "NYSE"),
    # REITs
    "AMT":   ("American Tower Corp.", "NYSE"),
    "PLD":   ("Prologis Inc.", "NYSE"),
    # ETF populer
    "SPY":   ("SPDR S&P 500 ETF Trust", "NYSE"),
    "QQQ":   ("Invesco QQQ ETF", "NASDAQ"),
    "IWM":   ("iShares Russell 2000 ETF", "NYSE"),
    "GLD":   ("SPDR Gold Shares ETF", "NYSE"),
    "TLT":   ("iShares 20+ Year Treasury Bond ETF", "NASDAQ"),
    "VTI":   ("Vanguard Total Stock Market ETF", "NYSE"),
    "VEA":   ("Vanguard FTSE Developed Markets ETF", "NYSE"),
    "EEM":   ("iShares MSCI Emerging Markets ETF", "NYSE"),
    "ARKK":  ("ARK Innovation ETF", "NYSE"),
    "SQQQ":  ("ProShares UltraPro Short QQQ", "NASDAQ"),
}


def _ticker_to_instrument_info(ticker: str, name: str, exchange: str) -> InstrumentInfo:
    """Buat InstrumentInfo untuk satu ticker US."""
    return InstrumentInfo(
        canonical_symbol=f"US:{ticker}",
        local_symbol=ticker,
        exchange=exchange,
        country="US",
        currency="USD",
        timezone="America/New_York",
        company_name=name,
        asset_type="ETF" if ticker in {"SPY", "QQQ", "IWM", "GLD", "TLT", "VTI", "VEA", "EEM", "ARKK", "SQQQ"} else "EQUITY",
        provider="yfinance",
    )


async def run_us_bootstrap(
    db: AsyncSession,
    days_history: Optional[int] = None,
    max_tickers: int = 100,
    dry_run: bool = False,
) -> dict:
    """
    Bootstrap ~90 ticker US ke database.

    Args:
        db: AsyncSession aktif
        days_history: Berapa hari histori OHLCV (default: dari config)
        max_tickers: Batas atas jumlah ticker yang diproses
        dry_run: Hitung saja, tidak ingest ke DB

    Returns dict ringkasan: total_tickers, bars_inserted, bars_skipped, errors
    """
    settings = get_settings()
    if days_history is None:
        days_history = getattr(settings, "us_bootstrap_days", 1825)

    end_date = date.today()
    start_date = end_date - timedelta(days=days_history)

    tickers_to_process = list(US_HARDCODED_TICKERS.items())[:max_tickers]
    instruments: list[InstrumentInfo] = [
        _ticker_to_instrument_info(ticker, name, exchange)
        for ticker, (name, exchange) in tickers_to_process
    ]

    log.info(
        "us_bootstrap.start",
        count=len(instruments),
        days_history=days_history,
        dry_run=dry_run,
    )

    if dry_run:
        return {"total_tickers": len(instruments), "dry_run": True}

    # Seed sources
    from sqlalchemy import text
    await db.execute(text("""
        INSERT INTO sources (id, url, publisher, title, license_class, primary_or_secondary)
        VALUES ('src_yfinance', 'https://finance.yahoo.com', 'Yahoo Finance', 'yfinance provider', 'THIRD_PARTY', 'SECONDARY')
        ON CONFLICT (id) DO NOTHING
    """))

    registry = get_provider_registry()
    provider = registry.get_primary("US")

    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    for info in instruments:
        try:
            instrument = await upsert_instrument(db, info)
            await db.flush()

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
                "us_bootstrap.ticker_done",
                symbol=info.canonical_symbol,
                bars_inserted=ohlcv_result.inserted,
            )
        except Exception as exc:
            total_errors += 1
            log.warning(
                "us_bootstrap.ticker_error",
                symbol=getattr(info, "canonical_symbol", "?"),
                error=str(exc),
            )

    await db.commit()

    summary = {
        "total_tickers": len(instruments),
        "bars_inserted": total_inserted,
        "bars_skipped": total_skipped,
        "errors": total_errors,
        "start_date": str(start_date),
        "end_date": str(end_date),
    }
    log.info("us_bootstrap.complete", **summary)
    return summary


async def run_bootstrap_standalone() -> None:
    """Entry point standalone — jalankan via `python -m app.ingestion.us_bootstrap`."""
    async with AsyncSessionLocal() as db:
        summary = await run_us_bootstrap(db)
        print(summary)


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_bootstrap_standalone())

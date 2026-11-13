"""
Intraday 5-menit price polling.

Dijadwalkan setiap 5 menit saat jam bursa berlangsung.
Mengambil harga terkini via yfinance interval=5m, upsert ke price_bars.

Keterbatasan:
- yfinance intraday gratis tersedia ~60 hari ke belakang
- IDX jam bursa 09:00–15:50 WIB (Senin–Jumat, bukan hari libur)
- NYSE jam bursa 09:30–16:00 EST (Senin–Jumat, bukan hari libur)

TIDAK melakukan: auto-trade, login broker, scraping private.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Market hours check
# ---------------------------------------------------------------------------

def is_idx_market_open(now: Optional[datetime] = None) -> bool:
    """
    Cek apakah IDX sedang buka.
    Jam bursa IDX: Senin–Jumat 09:00–16:00 WIB (UTC+7).
    Libur nasional tidak dideteksi — cukup untuk polling sederhana.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    local = now.astimezone(ZoneInfo("Asia/Jakarta"))
    weekday = local.weekday()  # 0=Mon, 6=Sun
    if weekday >= 5:  # Sabtu atau Minggu
        return False

    hour, minute = local.hour, local.minute
    # Sesi pagi: 09:00–11:30, Sesi siang: 13:30–15:49
    in_morning = (9, 0) <= (hour, minute) <= (11, 30)
    in_afternoon = (13, 30) <= (hour, minute) <= (15, 49)
    return in_morning or in_afternoon


def is_us_market_open(now: Optional[datetime] = None) -> bool:
    """
    Cek apakah NYSE/NASDAQ sedang buka.
    Jam bursa: Senin–Jumat 09:30–16:00 EST.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    local = now.astimezone(ZoneInfo("America/New_York"))
    weekday = local.weekday()
    if weekday >= 5:
        return False

    hour, minute = local.hour, local.minute
    return (9, 30) <= (hour, minute) <= (15, 59)


# ---------------------------------------------------------------------------
# Fetch latest price via yfinance
# ---------------------------------------------------------------------------

def _fetch_latest_prices_sync(symbols_jk: list[str]) -> dict[str, float]:
    """
    Fetch harga penutupan terkini via yfinance.
    symbols_jk: list ticker dengan suffix .JK untuk IDX (mis. ["BBCA.JK", "TLKM.JK"])
    atau tanpa suffix untuk US.
    Returns dict: canonical_symbol → harga float
    """
    if not symbols_jk:
        return {}

    try:
        import yfinance as yf
        tickers = yf.Tickers(" ".join(symbols_jk))
        prices: dict[str, float] = {}
        for sym in symbols_jk:
            ticker_obj = tickers.tickers.get(sym)
            if ticker_obj is None:
                continue
            try:
                info = ticker_obj.fast_info
                price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
                if price and price > 0:
                    prices[sym] = float(price)
            except Exception:
                log.warning("intraday.price_parse_failed", symbol=sym, exc_info=True)
        return prices
    except Exception as exc:
        log.warning("intraday.fetch_failed", error=str(exc))
        return {}


async def fetch_latest_prices(canonical_symbols: list[str]) -> dict[str, float]:
    """
    Async wrapper untuk _fetch_latest_prices_sync.
    canonical_symbols: list "IDX:BBCA", "US:AAPL", dll.
    Returns dict: canonical_symbol → price float
    """
    idx_tickers: list[str] = []
    us_tickers: list[str] = []

    for sym in canonical_symbols:
        parts = sym.split(":", 1)
        if len(parts) == 2:
            market, ticker = parts
            if market == "IDX":
                idx_tickers.append(f"{ticker}.JK")
            else:
                us_tickers.append(ticker)

    all_symbols = idx_tickers + us_tickers

    if not all_symbols:
        return {}

    # Jalankan di thread executor agar tidak blokir event loop
    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(None, _fetch_latest_prices_sync, all_symbols)

    # Map kembali ke canonical_symbol
    result: dict[str, float] = {}
    for sym in canonical_symbols:
        parts = sym.split(":", 1)
        if len(parts) != 2:
            continue
        market, ticker = parts
        yf_key = f"{ticker}.JK" if market == "IDX" else ticker
        if yf_key in raw:
            result[sym] = raw[yf_key]

    return result


# ---------------------------------------------------------------------------
# Upsert ke price_bars
# ---------------------------------------------------------------------------

async def update_latest_prices(db: "AsyncSession") -> dict:  # noqa: F821
    """
    Ambil semua instrumen aktif, fetch harga terkini, upsert ke price_bars.
    Dipanggil oleh scheduler setiap 5 menit saat jam bursa.

    Returns ringkasan: {updated, skipped, errors}
    """
    from datetime import date as date_type
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.db.models import Instrument, PriceBar

    now = datetime.now(tz=timezone.utc)
    idx_open = is_idx_market_open(now)
    us_open = is_us_market_open(now)

    if not idx_open and not us_open:
        log.debug("intraday.skip", reason="all_markets_closed")
        return {"updated": 0, "skipped": 0, "errors": 0, "reason": "markets_closed"}

    # Ambil instrumen aktif sesuai market yang buka
    markets_open: list[str] = []
    if idx_open:
        markets_open.append("IDX")
    if us_open:
        markets_open.extend(["NASDAQ", "NYSE", "US"])

    result = await db.execute(
        select(Instrument).where(
            Instrument.status == "ACTIVE",
            Instrument.exchange.in_(markets_open),
        )
    )
    instruments = result.scalars().all()

    if not instruments:
        return {"updated": 0, "skipped": 0, "errors": 0}

    canonical_symbols = [instr.canonical_symbol for instr in instruments]
    prices = await fetch_latest_prices(canonical_symbols)

    today = date_type.today()
    updated = 0
    errors = 0

    for instr in instruments:
        price = prices.get(instr.canonical_symbol)
        if price is None or price <= 0:
            continue

        try:
            stmt = pg_insert(PriceBar).values(
                instrument_id=instr.id,
                session_date=today,
                close=Decimal(str(price)),
                adj_close=Decimal(str(price)),
                provider="yfinance_intraday",
                is_adjusted=False,
                adjustment_version="v1",
                ingested_at=now,
            ).on_conflict_do_update(
                index_elements=["instrument_id", "session_date", "provider"],
                set_={
                    "close": Decimal(str(price)),
                    "adj_close": Decimal(str(price)),
                    "ingested_at": now,
                },
            )
            await db.execute(stmt)
            updated += 1
        except Exception as exc:
            errors += 1
            log.warning("intraday.upsert_error", symbol=instr.canonical_symbol, error=str(exc))

    if updated > 0:
        await db.commit()

    log.debug("intraday.update_done", updated=updated, total=len(instruments), errors=errors)
    return {"updated": updated, "skipped": len(instruments) - updated - errors, "errors": errors}

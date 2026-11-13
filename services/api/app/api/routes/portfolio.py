"""
Portfolio routes — Phase 1 Foundation.
Semua transaksi hanya manual oleh user — tidak ada auto-trading.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import asyncio
from datetime import timedelta

from app.api.schemas import (
    EditPositionRequest,
    EditPositionResponse,
    PortfolioSeedResponse,
    PortfolioSummaryResponse,
    PositionResponse,
    QuickPositionRequest,
    QuickPositionResponse,
    TradeCreateRequest,
    TradeResponse,
)
from app.db.models import Instrument, PriceBar, Trade
from app.db.session import get_db
from app.portfolio.calculator import compute_positions, enrich_positions_with_prices
from app.portfolio.seeder import get_or_create_default_portfolio, seed_initial_portfolio
from app.providers.registry import get_provider_registry
from app.ingestion.ohlcv import ingest_ohlcv

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/portfolio", tags=["portfolio"])
LOT_SIZE = 100  # 1 lot = 100 saham (IDX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_latest_prices(
    instrument_ids: list[str],
    db: AsyncSession,
) -> dict[str, tuple[float, date]]:
    """Ambil harga terakhir untuk sekumpulan instrument_id dari price_bars."""
    if not instrument_ids:
        return {}

    prices: dict[str, tuple[float, date]] = {}

    for iid in instrument_ids:
        result = await db.execute(
            select(PriceBar)
            .where(PriceBar.instrument_id == iid)
            .order_by(PriceBar.session_date.desc())
            .limit(1)
        )
        bar = result.scalar_one_or_none()
        if bar is not None:
            prices[iid] = (float(bar.close), bar.session_date)

    return prices


async def _get_instruments(
    instrument_ids: list[str],
    db: AsyncSession,
) -> dict[str, Instrument]:
    result = await db.execute(
        select(Instrument).where(Instrument.id.in_(instrument_ids))
    )
    return {inst.id: inst for inst in result.scalars().all()}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary(db: AsyncSession = Depends(get_db)) -> PortfolioSummaryResponse:
    """
    Ambil ringkasan portofolio dengan posisi aktif, harga pasar, dan P/L tidak terealisasi.
    """
    portfolio = await get_or_create_default_portfolio(db)

    # Load semua trade untuk portfolio ini
    trades_result = await db.execute(
        select(Trade)
        .where(Trade.portfolio_id == portfolio.id)
        .order_by(Trade.trade_date)
    )
    trades = list(trades_result.scalars().all())

    if not trades:
        return PortfolioSummaryResponse(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            base_currency=portfolio.base_currency,
            as_of=datetime.now(timezone.utc),
            total_invested=0.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            positions=[],
            sector_weights={},
            concentration_warnings=[],
            trade_count=0,
        )

    # Hitung posisi dari trade history (WAC)
    raw_positions = compute_positions(trades)

    if not raw_positions:
        return PortfolioSummaryResponse(
            portfolio_id=portfolio.id,
            portfolio_name=portfolio.name,
            base_currency=portfolio.base_currency,
            as_of=datetime.now(timezone.utc),
            total_invested=0.0,
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            positions=[],
            sector_weights={},
            concentration_warnings=[],
            trade_count=len(trades),
        )

    # Ambil instrument metadata
    instrument_ids = list(raw_positions.keys())
    instruments_map = await _get_instruments(instrument_ids, db)
    prices_map = await _get_latest_prices(instrument_ids, db)

    # Enrich posisi dengan metadata instrument
    for iid, pos in raw_positions.items():
        inst = instruments_map.get(iid)
        if inst:
            pos.canonical_symbol = inst.canonical_symbol
            pos.company_name = inst.company_name
            pos.exchange = inst.exchange
            pos.currency = inst.currency
            pos.sector = inst.sector

    # Enrich dengan harga pasar dan hitung P/L
    raw_positions = enrich_positions_with_prices(raw_positions, prices_map)

    # Hitung total portfolio
    total_market_value = sum(
        p.market_value for p in raw_positions.values() if p.market_value is not None
    )
    total_invested = sum(p.total_cost for p in raw_positions.values())
    unrealized_pnl = total_market_value - total_invested
    unrealized_pnl_pct = (unrealized_pnl / total_invested) if total_invested > 0 else 0.0

    # Sector weights
    sector_weights: dict[str, float] = {}
    for pos in raw_positions.values():
        if pos.sector and total_market_value > 0:
            mv = pos.market_value or (pos.total_cost)
            sector_weights[pos.sector] = sector_weights.get(pos.sector, 0.0) + mv / total_market_value

    # Concentration warnings
    warnings = []
    for sector, w in sector_weights.items():
        if w > 0.50:
            warnings.append(f"Konsentrasi tinggi di sektor {sector}: {w:.0%} dari portofolio")
    for pos in raw_positions.values():
        if pos.weight > 0.25:
            warnings.append(f"{pos.canonical_symbol or pos.instrument_id}: {pos.weight:.0%} melebihi batas 25% per saham")

    # Convert ke response model
    positions_resp = [
        PositionResponse(
            instrument_id=pos.instrument_id,
            canonical_symbol=pos.canonical_symbol,
            company_name=pos.company_name,
            exchange=pos.exchange,
            currency=pos.currency,
            sector=pos.sector,
            shares=pos.shares,
            lots=pos.lots,
            avg_cost=pos.avg_cost,
            total_cost=round(pos.total_cost, 2),
            current_price=pos.current_price,
            current_price_date=pos.current_price_date,
            market_value=pos.market_value,
            unrealized_pnl=pos.unrealized_pnl,
            unrealized_pnl_pct=pos.unrealized_pnl_pct,
            weight=pos.weight,
            trade_count=pos.trade_count,
            first_buy_date=pos.first_buy_date,
            last_trade_date=pos.last_trade_date,
        )
        for pos in sorted(raw_positions.values(), key=lambda p: -(p.market_value or p.total_cost))
    ]

    return PortfolioSummaryResponse(
        portfolio_id=portfolio.id,
        portfolio_name=portfolio.name,
        base_currency=portfolio.base_currency,
        as_of=datetime.now(timezone.utc),
        total_invested=round(total_invested, 2),
        market_value=round(total_market_value, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        unrealized_pnl_pct=round(unrealized_pnl_pct, 4),
        positions=positions_resp,
        sector_weights={k: round(v, 4) for k, v in sector_weights.items()},
        concentration_warnings=warnings,
        trade_count=len(trades),
    )


@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(db: AsyncSession = Depends(get_db)) -> list[TradeResponse]:
    """Daftar semua trade di portofolio default."""
    portfolio = await get_or_create_default_portfolio(db)

    result = await db.execute(
        select(Trade, Instrument)
        .join(Instrument, Trade.instrument_id == Instrument.id)
        .where(Trade.portfolio_id == portfolio.id)
        .order_by(Trade.trade_date.desc(), Trade.id.desc())
    )
    rows = result.all()

    return [
        TradeResponse(
            id=t.id,
            portfolio_id=t.portfolio_id,
            instrument_id=t.instrument_id,
            canonical_symbol=inst.canonical_symbol,
            company_name=inst.company_name,
            trade_date=t.trade_date,
            side=t.side,
            shares=float(t.shares),
            lots=round(float(t.shares) / 100, 2),
            price=float(t.price),
            fee=float(t.fee or 0),
            tax=float(t.tax or 0),
            currency=t.currency,
            source_broker=t.source_broker,
            notes=t.notes,
            created_at=t.created_at,
        )
        for t, inst in rows
    ]


@router.post("/trades", response_model=TradeResponse, status_code=201)
async def add_trade(
    body: TradeCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> TradeResponse:
    """
    Tambah transaksi manual.
    Semua keputusan transaksi sepenuhnya menjadi tanggung jawab pengguna.
    """
    portfolio = await get_or_create_default_portfolio(db)

    # Resolve instrument
    result = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == body.canonical_symbol)
    )
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrumen {body.canonical_symbol!r} tidak ditemukan")

    if body.side not in ("BUY", "SELL"):
        raise HTTPException(status_code=422, detail="side harus BUY atau SELL")

    if body.shares <= 0 or body.price <= 0:
        raise HTTPException(status_code=422, detail="shares dan price harus positif")

    # Generate fingerprint unik untuk dedup (maks 64 char sesuai kolom DB)
    fingerprint = f"MANUAL-{uuid.uuid4().hex[:16]}"

    trade = Trade(
        id=str(uuid.uuid4()),
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        trade_date=body.trade_date,
        side=body.side,
        shares=body.shares,
        price=body.price,
        fee=body.fee or 0.0,
        tax=body.tax or 0.0,
        currency=body.currency or instrument.currency,
        source_broker=body.source_broker,
        import_fingerprint=fingerprint,
        notes=body.notes,
    )
    db.add(trade)
    await db.flush()

    log.info(
        "portfolio.trade.added",
        symbol=body.canonical_symbol,
        side=body.side,
        shares=body.shares,
        price=body.price,
    )

    return TradeResponse(
        id=trade.id,
        portfolio_id=trade.portfolio_id,
        instrument_id=trade.instrument_id,
        canonical_symbol=instrument.canonical_symbol,
        company_name=instrument.company_name,
        trade_date=trade.trade_date,
        side=trade.side,
        shares=float(trade.shares),
        lots=round(float(trade.shares) / 100, 2),
        price=float(trade.price),
        fee=float(trade.fee or 0),
        tax=float(trade.tax or 0),
        currency=trade.currency,
        source_broker=trade.source_broker,
        notes=trade.notes,
        created_at=trade.created_at,
    )


@router.delete("/trades/{trade_id}", status_code=204, response_class=Response)
async def delete_trade(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Hapus transaksi. Hanya trade MANUAL yang boleh dihapus (bukan SEED)."""
    portfolio = await get_or_create_default_portfolio(db)

    result = await db.execute(
        select(Trade).where(
            Trade.id == trade_id,
            Trade.portfolio_id == portfolio.id,
        )
    )
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")

    # Proteksi: jangan hapus seed data (bisa merusak posisi awal)
    if trade.import_fingerprint and trade.import_fingerprint.startswith("SEED-"):
        raise HTTPException(
            status_code=403,
            detail="Trade seed tidak dapat dihapus. Tambahkan trade koreksi jika perlu.",
        )

    await db.delete(trade)
    log.info("portfolio.trade.deleted", trade_id=trade_id)
    return Response(status_code=204)


@router.delete("/positions/{symbol}", status_code=200, response_model=None)
async def delete_position(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Hapus semua trades untuk satu simbol saham dari portofolio.
    Gunakan untuk menghapus posisi yang salah input.
    Trade SEED tidak dapat dihapus.
    """
    canonical = symbol.strip().upper()
    if ":" not in canonical:
        canonical = f"IDX:{canonical}"

    portfolio = await get_or_create_default_portfolio(db)

    # Cari instrument
    instr_res = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == canonical)
    )
    instrument = instr_res.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrumen {canonical!r} tidak ditemukan")

    # Ambil semua trades
    trades_res = await db.execute(
        select(Trade).where(
            Trade.portfolio_id == portfolio.id,
            Trade.instrument_id == instrument.id,
        )
    )
    trades = trades_res.scalars().all()
    if not trades:
        raise HTTPException(status_code=404, detail=f"Tidak ada posisi {canonical} di portofolio")

    deleted = 0
    for t in trades:
        await db.delete(t)
        deleted += 1

    await db.commit()
    log.info("portfolio.position.deleted", symbol=canonical, deleted=deleted)

    return {
        "symbol": canonical,
        "deleted_trades": deleted,
        "message": f"{deleted} trade dihapus untuk {canonical}",
    }


@router.patch("/positions/{symbol}", response_model=EditPositionResponse)
async def edit_position(
    symbol: str,
    body: EditPositionRequest,
    db: AsyncSession = Depends(get_db),
) -> EditPositionResponse:
    """
    Edit posisi — hapus semua trade lama lalu buat satu trade baru
    dengan lot dan harga rata-rata yang diperbarui.
    Ini adalah koreksi data, bukan transaksi baru.
    """
    canonical = symbol.strip().upper()
    if ":" not in canonical:
        canonical = f"IDX:{canonical}"

    portfolio = await get_or_create_default_portfolio(db)

    # Cari instrumen
    instr_res = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == canonical)
    )
    instrument = instr_res.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrumen {canonical!r} tidak ditemukan")

    # Hapus semua trade lama
    trades_res = await db.execute(
        select(Trade).where(
            Trade.portfolio_id == portfolio.id,
            Trade.instrument_id == instrument.id,
        )
    )
    for t in trades_res.scalars().all():
        await db.delete(t)

    # Buat satu trade baru sebagai pengganti
    trade_date = body.trade_date or date.today()
    shares = float(body.lots * LOT_SIZE)
    new_trade = Trade(
        id=str(uuid.uuid4()),
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        trade_date=trade_date,
        side="BUY",
        shares=shares,
        price=body.avg_price,
        fee=0.0,
        tax=0.0,
        currency=instrument.currency,
        source_broker="MANUAL",
        import_fingerprint=None,
        notes=body.notes or f"Dikoreksi: {body.lots} lot @ {body.avg_price:,.2f}",
    )
    db.add(new_trade)
    await db.commit()

    log.info("portfolio.position.edited", symbol=canonical, lots=body.lots, price=body.avg_price)

    return EditPositionResponse(
        canonical_symbol=canonical,
        company_name=instrument.company_name,
        lots=body.lots,
        shares=int(shares),
        avg_price=body.avg_price,
        total_cost=shares * body.avg_price,
        trade_date=trade_date,
    )


@router.post("/seed", response_model=PortfolioSeedResponse)
async def seed_portfolio(db: AsyncSession = Depends(get_db)) -> PortfolioSeedResponse:
    """
    Isi portofolio awal dari data CR §10.
    Idempotent — aman dijalankan berkali-kali.
    Instrumen harus sudah ada (jalankan /admin/bootstrap lebih dulu).
    """
    result = await seed_initial_portfolio(db)
    return PortfolioSeedResponse(
        message="Seed selesai",
        portfolio_id=result["portfolio_id"],
        created=result["created"],
        skipped=result["skipped"],
        errors=result["errors"],
    )


# ---------------------------------------------------------------------------
# Quick Position Entry — tambah posisi via lot (auto-create instrument)
# ---------------------------------------------------------------------------

@router.post("/positions/quick", response_model=QuickPositionResponse, status_code=201)
async def quick_add_position(
    body: QuickPositionRequest,
    db: AsyncSession = Depends(get_db),
) -> QuickPositionResponse:
    """
    Tambah posisi baru dengan cepat: cukup isi kode saham, lot, dan harga rata-rata.

    - 1 lot = 100 saham (IDX)
    - Jika instrumen belum ada di DB, akan dibuat otomatis dengan data minimal
    - Harga terkini akan di-refresh via yfinance di background
    - Keputusan input sepenuhnya tanggung jawab pengguna
    """
    # Normalise symbol: "BBCA" → "IDX:BBCA"
    raw = body.symbol.strip().upper()
    if ":" not in raw:
        canonical = f"IDX:{raw}"
        local_sym = raw
        exchange = "IDX"
        currency = "IDR"
        country = "ID"
        timezone = "Asia/Jakarta"
    else:
        canonical = raw
        parts = raw.split(":", 1)
        exchange = parts[0]
        local_sym = parts[1]
        currency = "IDR" if exchange in ("IDX", "BEI") else "USD"
        country = "ID" if exchange in ("IDX", "BEI") else "US"
        timezone = "Asia/Jakarta" if exchange in ("IDX", "BEI") else "America/New_York"

    # Cari atau buat instrument
    instr_res = await db.execute(
        select(Instrument).where(Instrument.canonical_symbol == canonical)
    )
    instrument = instr_res.scalar_one_or_none()

    if instrument is None:
        instrument = Instrument(
            id=str(uuid.uuid4()),
            canonical_symbol=canonical,
            local_symbol=local_sym,
            exchange=exchange,
            country=country,
            currency=currency,
            timezone=timezone,
            asset_type="EQUITY",
            status="ACTIVE",
            company_name=local_sym,
        )
        db.add(instrument)
        await db.flush()
        log.info("portfolio.quick_add.instrument_created", symbol=canonical)

    portfolio = await get_or_create_default_portfolio(db)

    shares = body.lots * 100
    trade_date = body.trade_date or date.today()
    fingerprint = f"QUICK-{portfolio.id}-{instrument.id}-{trade_date}-BUY-{shares}-{uuid.uuid4().hex[:8]}"

    trade = Trade(
        id=str(uuid.uuid4()),
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        trade_date=trade_date,
        side="BUY",
        shares=float(shares),
        price=body.avg_price,
        fee=body.fee,
        tax=0.0,
        currency=currency,
        source_broker="MANUAL",
        import_fingerprint=fingerprint,
        notes=body.notes,
    )
    db.add(trade)
    await db.commit()

    log.info(
        "portfolio.quick_add.done",
        symbol=canonical,
        lots=body.lots,
        shares=shares,
        avg_price=body.avg_price,
    )

    # Trigger price refresh via yfinance di background (best-effort)
    price_refresh_ok = False
    try:
        from app.ingestion.ohlcv import ingest_ohlcv
        from app.providers.registry import get_provider_registry
        from datetime import timedelta

        async def _refresh() -> None:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as bg_db:
                registry = get_provider_registry()
                market = "IDX" if exchange in ("IDX", "BEI") else "US"
                provider = registry.get_primary(market)
                end_d = date.today()
                start_d = end_d - timedelta(days=365)
                await ingest_ohlcv(bg_db, instrument, provider, start_d, end_d)
                await bg_db.commit()

        asyncio.create_task(_refresh())
        price_refresh_ok = True
    except Exception:
        log.warning("portfolio.price_refresh_task_failed", exc_info=True)

    return QuickPositionResponse(
        trade_id=trade.id,
        canonical_symbol=instrument.canonical_symbol,
        company_name=instrument.company_name,
        lots=body.lots,
        shares=shares,
        avg_price=body.avg_price,
        total_cost=float(shares) * body.avg_price + body.fee,
        trade_date=trade_date,
        price_refresh_triggered=price_refresh_ok,
    )


# ---------------------------------------------------------------------------
# Refresh semua harga portfolio
# ---------------------------------------------------------------------------

@router.post("/prices/refresh")
async def refresh_portfolio_prices(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Trigger refresh harga untuk semua instrumen yang ada di portofolio.
    Background task — langsung return, proses berjalan async.
    """
    portfolio = await get_or_create_default_portfolio(db)
    trades = await db.execute(
        select(Trade).where(Trade.portfolio_id == portfolio.id)
    )
    all_trades = trades.scalars().all()

    # Kumpulkan instrument_id unik
    instrument_ids = list({t.instrument_id for t in all_trades})
    if not instrument_ids:
        return {"triggered": 0, "symbols": []}

    # Ambil instrumen
    result = await db.execute(
        select(Instrument).where(Instrument.id.in_(instrument_ids))
    )
    instruments = result.scalars().all()
    registry = get_provider_registry()

    end = date.today()
    start = end - timedelta(days=7)  # refresh 7 hari terakhir saja (cepat)

    triggered_symbols: list[str] = []

    async def _refresh_one(instr: Instrument) -> None:
        try:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as bg_db:
                market = "IDX" if instr.exchange in ("IDX", "BEI") else "US"
                provider = registry.get_primary(market)
                await ingest_ohlcv(bg_db, instr, provider, start, end)
                await bg_db.commit()
        except Exception as exc:
            log.warning("portfolio.prices.refresh.error", symbol=instr.canonical_symbol, error=str(exc))

    for instr in instruments:
        asyncio.create_task(_refresh_one(instr))
        triggered_symbols.append(instr.canonical_symbol)

    return {
        "triggered": len(instruments),
        "symbols": [i.canonical_symbol for i in instruments],
        "message": f"Refresh harga dimulai untuk {len(instruments)} saham di background",
    }

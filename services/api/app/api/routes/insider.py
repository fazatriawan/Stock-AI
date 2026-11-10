"""
R14 — Insider Transaction API routes.

Endpoints:
  GET  /insider/{symbol}/signal      — sinyal insider (scoring engine)
  GET  /insider/{symbol}/transactions — daftar transaksi historis
  POST /insider/{symbol}/transactions — tambah transaksi manual (dari IDX disclosure)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    InsiderImportResponse,
    InsiderSignalResponse,
    InsiderTransactionRequest,
    InsiderTransactionResponse,
)
from app.analytics.insider_loader import load_insider_signal, upsert_insider_transaction
from app.db.models import InsiderTransaction
from app.db.session import get_db
from app.domain.instruments import resolve_instrument

router = APIRouter(prefix="/insider", tags=["insider"])


@router.get("/{symbol}/signal", response_model=InsiderSignalResponse)
async def get_insider_signal(
    symbol: str,
    lookback_days: int = 180,
    db: AsyncSession = Depends(get_db),
) -> InsiderSignalResponse:
    instrument = await resolve_instrument(db, symbol)
    if not instrument:
        raise HTTPException(status_code=404, detail=f"Instrumen tidak ditemukan: {symbol}")

    today = datetime.now(tz=timezone.utc).date()
    signal = await load_insider_signal(db, instrument, as_of=today, lookback_days=lookback_days)

    return InsiderSignalResponse(
        symbol=symbol,
        as_of=today,
        sentiment=signal.sentiment.value,
        score=signal.score,
        net_buy_shares=signal.net_buy_shares,
        net_sell_shares=signal.net_sell_shares,
        unique_buyers=signal.unique_buyers,
        unique_sellers=signal.unique_sellers,
        cluster_detected=signal.cluster_detected,
        cluster_type=signal.cluster_type,
        lookback_days=signal.lookback_days,
        transactions_analyzed=signal.transactions_analyzed,
        latest_date=signal.latest_date,
        summary_text=signal.summary_text,
        transactions=[
            InsiderTransactionResponse(
                insider_name=t.insider_name,
                insider_role=t.insider_role,
                transaction_type=t.transaction_type,
                transaction_date=t.transaction_date,
                shares=t.shares,
                price_per_share=t.price_per_share,
                total_value=t.total_value,
                currency=t.currency,
                shares_owned_after=t.shares_owned_after,
                ownership_pct_after=t.ownership_pct_after,
                disclosure_date=t.disclosure_date,
                source_url=t.source_url,
            )
            for t in signal.transactions
        ],
    )


@router.get("/{symbol}/transactions", response_model=list[InsiderTransactionResponse])
async def list_insider_transactions(
    symbol: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[InsiderTransactionResponse]:
    instrument = await resolve_instrument(db, symbol)
    if not instrument:
        raise HTTPException(status_code=404, detail=f"Instrumen tidak ditemukan: {symbol}")

    result = await db.execute(
        select(InsiderTransaction)
        .where(InsiderTransaction.instrument_id == instrument.id)
        .order_by(InsiderTransaction.transaction_date.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())

    return [
        InsiderTransactionResponse(
            id=r.id,
            insider_name=r.insider_name,
            insider_role=r.insider_role,
            transaction_type=r.transaction_type,
            transaction_date=r.transaction_date,
            shares=r.shares,
            price_per_share=float(r.price_per_share) if r.price_per_share else None,
            total_value=float(r.total_value) if r.total_value else None,
            currency=r.currency,
            shares_owned_after=r.shares_owned_after,
            ownership_pct_after=float(r.ownership_pct_after) if r.ownership_pct_after else None,
            disclosure_date=r.disclosure_date,
            source_url=r.source_url,
        )
        for r in rows
    ]


@router.post("/{symbol}/transactions", response_model=InsiderImportResponse)
async def add_insider_transactions(
    symbol: str,
    transactions: list[InsiderTransactionRequest],
    db: AsyncSession = Depends(get_db),
) -> InsiderImportResponse:
    """
    Tambah transaksi insider secara manual dari keterbukaan informasi publik IDX.
    Duplikat (berdasarkan nama + tanggal + jumlah saham) akan di-skip otomatis.
    """
    instrument = await resolve_instrument(db, symbol)
    if not instrument:
        raise HTTPException(status_code=404, detail=f"Instrumen tidak ditemukan: {symbol}")

    _validate_roles   = {"DIRECTOR", "COMMISSIONER", "MAJOR_SHAREHOLDER", "OTHER"}
    _validate_types   = {"BUY", "SELL", "GRANT", "EXERCISE"}

    inserted = skipped = 0
    for tx in transactions:
        if tx.insider_role not in _validate_roles:
            raise HTTPException(
                status_code=422,
                detail=f"insider_role tidak valid: {tx.insider_role}. Pilihan: {_validate_roles}",
            )
        if tx.transaction_type not in _validate_types:
            raise HTTPException(
                status_code=422,
                detail=f"transaction_type tidak valid: {tx.transaction_type}. Pilihan: {_validate_types}",
            )

        was_inserted = await upsert_insider_transaction(db, instrument, tx.model_dump())
        if was_inserted:
            inserted += 1
        else:
            skipped += 1

    await db.commit()
    return InsiderImportResponse(symbol=symbol, inserted=inserted, skipped=skipped)


from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import InstrumentResponse, InstrumentSearchResponse
from app.core.exceptions import DataNotFoundError
from app.db.session import get_db
from app.domain.instruments import resolve_instrument, search_instruments

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("/search", response_model=InstrumentSearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=50, description="Ticker atau nama perusahaan"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> InstrumentSearchResponse:
    """Cari instrument dari canonical_symbol, local_symbol, atau company_name."""
    instruments = await search_instruments(db, q, limit=limit)
    return InstrumentSearchResponse(
        results=[InstrumentResponse.model_validate(i) for i in instruments],
        query=q,
        count=len(instruments),
    )


@router.get("/{symbol}", response_model=InstrumentResponse)
async def get_instrument(
    symbol: str,
    db: AsyncSession = Depends(get_db),
) -> InstrumentResponse:
    """Resolve instrument dari berbagai format: IDX:BMRI, BMRI, BMRI.JK."""
    instrument = await resolve_instrument(db, symbol)
    if not instrument:
        raise DataNotFoundError(f"Instrument tidak ditemukan: {symbol}")
    return InstrumentResponse.model_validate(instrument)

from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.schemas import MarketStatusResponse
from app.domain.calendar import MarketCalendar, EXCHANGE_CONFIG

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/status", response_model=list[MarketStatusResponse])
async def get_market_status() -> list[MarketStatusResponse]:
    """Status semua exchange yang didukung."""
    results = []
    now = datetime.now(tz=timezone.utc)
    for exchange in EXCHANGE_CONFIG:
        cal = MarketCalendar(exchange)
        today = now.date()
        results.append(MarketStatusResponse(
            exchange=exchange,
            timezone=EXCHANGE_CONFIG[exchange]["timezone"],
            is_trading_day=cal.is_trading_day(today),
            is_eod_data_ready=cal.is_eod_data_ready(today, now),
            session_date=today,
            as_of=now,
        ))
    return results

"""Unit tests untuk MarketCalendar — timezone-aware."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.calendar import MarketCalendar


class TestMarketCalendar:
    def test_weekday_is_trading_day(self) -> None:
        cal = MarketCalendar("IDX")
        assert cal.is_trading_day(date(2026, 11, 3))  # Senin

    def test_weekend_not_trading_day(self) -> None:
        cal = MarketCalendar("IDX")
        # Nov 7 2026 = Sabtu, Nov 8 2026 = Minggu
        assert not cal.is_trading_day(date(2026, 11, 7))
        assert not cal.is_trading_day(date(2026, 11, 8))

    def test_previous_trading_day(self) -> None:
        cal = MarketCalendar("IDX")
        # Nov 9 2026 = Senin → previous = Jumat Nov 7? No, Jumat = Nov 6
        prev = cal.previous_trading_day(date(2026, 11, 9))  # Senin → Jumat
        assert prev == date(2026, 11, 6)

    def test_next_trading_day(self) -> None:
        cal = MarketCalendar("IDX")
        nxt = cal.next_trading_day(date(2026, 11, 6))  # Jumat → Senin
        assert nxt == date(2026, 11, 9)

    def test_eod_ready_after_close(self) -> None:
        cal = MarketCalendar("IDX")
        tz = ZoneInfo("Asia/Jakarta")
        session = date(2026, 11, 3)  # Selasa
        # 17:30 WIB = 1h 15m setelah close 16:15
        after_close = datetime(2026, 11, 3, 17, 30, tzinfo=tz)
        assert cal.is_eod_data_ready(session, after_close)

    def test_eod_not_ready_before_close(self) -> None:
        cal = MarketCalendar("IDX")
        tz = ZoneInfo("Asia/Jakarta")
        session = date(2026, 11, 3)
        before_close = datetime(2026, 11, 3, 15, 0, tzinfo=tz)
        assert not cal.is_eod_data_ready(session, before_close)

    def test_trading_days_between(self) -> None:
        cal = MarketCalendar("IDX")
        # Nov 7 = Sabtu, Nov 8 = Minggu, Nov 9 = Senin
        days = cal.trading_days_between(date(2026, 11, 7), date(2026, 11, 13))
        assert date(2026, 11, 7) not in days  # Sabtu
        assert date(2026, 11, 8) not in days  # Minggu
        assert date(2026, 11, 9) in days      # Senin
        assert len(days) == 5  # Sen-Jum

    def test_unknown_exchange_raises(self) -> None:
        with pytest.raises(ValueError):
            MarketCalendar("INVALID")

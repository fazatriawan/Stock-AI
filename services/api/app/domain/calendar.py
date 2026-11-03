"""
Market calendar — timezone-aware.
Mengetahui kapan bursa buka/tutup, hari libur, dan apakah data EOD sudah siap.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

EXCHANGE_CONFIG: dict[str, dict] = {
    "IDX": {
        "timezone": "Asia/Jakarta",
        "open_time": (9, 0),
        "close_time": (16, 15),
        "currency": "IDR",
        "country": "ID",
        "eod_ready_offset_hours": 1,  # EOD data tersedia ~1 jam setelah close
    },
    "NYSE": {
        "timezone": "America/New_York",
        "open_time": (9, 30),
        "close_time": (16, 0),
        "currency": "USD",
        "country": "US",
        "eod_ready_offset_hours": 2,
    },
    "NASDAQ": {
        "timezone": "America/New_York",
        "open_time": (9, 30),
        "close_time": (16, 0),
        "currency": "USD",
        "country": "US",
        "eod_ready_offset_hours": 2,
    },
}


class MarketCalendar:
    def __init__(self, exchange: str) -> None:
        if exchange not in EXCHANGE_CONFIG:
            raise ValueError(f"Exchange tidak dikenali: {exchange}")
        self.exchange = exchange
        self.config = EXCHANGE_CONFIG[exchange]
        self.tz = ZoneInfo(self.config["timezone"])

    def is_trading_day(self, d: date) -> bool:
        """Apakah hari ini hari bursa (bukan Sabtu/Minggu). Hari libur nasional belum dihandle — todo."""
        return d.weekday() < 5  # Senin=0, Jumat=4

    def previous_trading_day(self, d: date) -> date:
        """Hari bursa sebelumnya."""
        prev = d - timedelta(days=1)
        while not self.is_trading_day(prev):
            prev -= timedelta(days=1)
        return prev

    def next_trading_day(self, d: date) -> date:
        nxt = d + timedelta(days=1)
        while not self.is_trading_day(nxt):
            nxt += timedelta(days=1)
        return nxt

    def is_eod_data_ready(self, session_date: date, now: datetime | None = None) -> bool:
        """
        Apakah data EOD untuk session_date sudah tersedia di sumber?
        EOD dianggap siap = close_time + eod_ready_offset_hours telah lewat.
        """
        if now is None:
            now = datetime.now(tz=self.tz)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=self.tz)

        close_h, close_m = self.config["close_time"]
        offset_h = self.config["eod_ready_offset_hours"]

        eod_ready_at = datetime(
            session_date.year, session_date.month, session_date.day,
            close_h, close_m, 0, tzinfo=self.tz
        ) + timedelta(hours=offset_h)

        return now >= eod_ready_at

    def trading_days_between(self, start: date, end: date) -> list[date]:
        """Daftar hari bursa antara start dan end (inclusive)."""
        days = []
        current = start
        while current <= end:
            if self.is_trading_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days

    def get_close_time(self, session_date: date) -> datetime:
        h, m = self.config["close_time"]
        return datetime(session_date.year, session_date.month, session_date.day, h, m, tzinfo=self.tz)

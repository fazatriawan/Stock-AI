"""
FREE-17: Data gap detector untuk OHLCV instruments.

"Gap" = instrumen dengan bar count jauh di bawah ekspektasi berdasarkan
rentang tanggal pertama hingga terakhir yang tersimpan. Heuristik sederhana
tanpa kalender bursa penuh: gunakan business days * 0.90 sebagai ekspektasi
(faktor 0.90 memperhitungkan libur nasional rata-rata).

Prinsip:
- Hanya menghitung bar dengan freshness_status IN ('FRESH', 'STALE').
  Bar UNAVAILABLE / QUOTA_EXHAUSTED tidak masuk hitungan — mereka memang tidak ada.
- Instrumen dengan history < min_days_history diabaikan (terlalu baru untuk dievaluasi).
- Tidak pernah mengambil data harga atau memanggil provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

_ACTIVE_STATUSES = ("FRESH", "STALE")

# Faktor koreksi libur: 252 hari trading / 260 hari kerja ≈ 0.969
# Pakai 0.90 agar lebih toleran terhadap libur lokal IDX/NYSE
_HOLIDAY_FACTOR = 0.90


@dataclass
class GapReport:
    instrument_id: str
    canonical_symbol: str
    exchange: str
    bar_count: int
    expected_bars: int   # estimasi business days * holiday_factor
    gap_pct: float       # persen bar yang hilang (0 = tidak ada gap)
    first_date: date
    last_date: date
    history_days: int    # last_date - first_date dalam hari kalender
    severity: str        # "CRITICAL" / "WARNING" / "OK"


@dataclass
class DataGapsResult:
    reports: list[GapReport]
    instruments_checked: int
    with_gaps: int   # severity != OK
    ran_at: datetime


def _business_days(start: date, end: date) -> int:
    """Estimasi jumlah hari kerja antara start dan end (inklusif)."""
    total = (end - start).days + 1
    weeks, remainder = divmod(total, 7)
    bdays = weeks * 5

    # Hitung sisa hari
    start_dow = start.weekday()  # 0=Senin
    for i in range(remainder):
        if (start_dow + i) % 7 < 5:
            bdays += 1

    return max(bdays, 0)


def _classify(gap_pct: float) -> str:
    if gap_pct >= 25:
        return "CRITICAL"
    if gap_pct >= 10:
        return "WARNING"
    return "OK"


async def detect_data_gaps(
    db: AsyncSession,
    threshold_pct: float = 10.0,
    min_days_history: int = 30,
    limit: int = 100,
) -> DataGapsResult:
    """
    Deteksi instrumen dengan gap data OHLCV signifikan.

    Args:
        db: AsyncSession
        threshold_pct: hanya laporkan instrumen dengan gap_pct >= nilai ini (default 10%)
        min_days_history: abaikan instrumen dengan history < N hari (terlalu baru)
        limit: maks instrumen yang dilaporkan (sorted by gap_pct desc)

    Returns:
        DataGapsResult
    """
    from app.db.models import Instrument, PriceBar

    # Agregasi per instrument: count, min_date, max_date — hanya status aktif
    agg_rows = await db.execute(
        select(
            PriceBar.instrument_id,
            func.count(PriceBar.id).label("bar_count"),
            func.min(PriceBar.session_date).label("first_date"),
            func.max(PriceBar.session_date).label("last_date"),
        )
        .where(PriceBar.freshness_status.in_(_ACTIVE_STATUSES))
        .group_by(PriceBar.instrument_id)
    )
    agg = {r.instrument_id: r for r in agg_rows}

    if not agg:
        return DataGapsResult(
            reports=[],
            instruments_checked=0,
            with_gaps=0,
            ran_at=datetime.now(tz=timezone.utc),
        )

    # Ambil instrument metadata sekaligus
    instr_rows = await db.execute(
        select(Instrument.id, Instrument.canonical_symbol, Instrument.exchange)
        .where(Instrument.id.in_(list(agg.keys())))
    )
    instr_map = {r.id: r for r in instr_rows}

    reports: list[GapReport] = []

    for instrument_id, row in agg.items():
        instr = instr_map.get(instrument_id)
        if instr is None:
            continue

        first: date = row.first_date
        last: date = row.last_date
        history_days = (last - first).days

        if history_days < min_days_history:
            continue

        expected = int(_business_days(first, last) * _HOLIDAY_FACTOR)
        bar_count = row.bar_count

        if expected <= 0:
            continue

        missing = max(0, expected - bar_count)
        gap_pct = round(missing / expected * 100, 1)

        severity = _classify(gap_pct)

        if gap_pct < threshold_pct and severity == "OK":
            continue

        reports.append(GapReport(
            instrument_id=instrument_id,
            canonical_symbol=instr.canonical_symbol,
            exchange=instr.exchange,
            bar_count=bar_count,
            expected_bars=expected,
            gap_pct=gap_pct,
            first_date=first,
            last_date=last,
            history_days=history_days,
            severity=severity,
        ))

    # Sort by gap_pct descending, take top `limit`
    reports.sort(key=lambda r: r.gap_pct, reverse=True)
    reports = reports[:limit]

    instruments_checked = len(agg)
    with_gaps = sum(1 for r in reports if r.severity != "OK")

    log.info(
        "gap_detector.complete",
        instruments_checked=instruments_checked,
        with_gaps=with_gaps,
        threshold_pct=threshold_pct,
    )

    return DataGapsResult(
        reports=reports,
        instruments_checked=instruments_checked,
        with_gaps=with_gaps,
        ran_at=datetime.now(tz=timezone.utc),
    )

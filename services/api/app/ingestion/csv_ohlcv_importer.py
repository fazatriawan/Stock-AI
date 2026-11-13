"""
OHLCV CSV Importer — FREE-02.

Mengimpor data harga historis dari file CSV publik ke tabel price_bars.
Terpisah dari portfolio trade importer.

Prinsip:
- Idempotent: duplikat (instrument_id, session_date, provider) di-skip, bukan error.
- Null != 0: kolom kosong tidak diisi dengan nilai default.
- Simpan Source row dengan checksum file — tidak re-import file yang sama.
- freshness_status = FRESH untuk baris yang berhasil diimpor.
- Tidak mengisi tanggal kosong dari data hari sebelumnya.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# Nama kolom yang diterima (case-insensitive)
_DATE_COLS = {"date", "tanggal", "session_date", "trading_date"}
_OPEN_COLS = {"open", "open_price", "harga_buka"}
_HIGH_COLS = {"high", "high_price", "harga_tertinggi"}
_LOW_COLS = {"low", "low_price", "harga_terendah"}
_CLOSE_COLS = {"close", "close_price", "harga_tutup", "last", "last_price"}
_VOLUME_COLS = {"volume", "vol"}
_ADJ_CLOSE_COLS = {"adj_close", "adjusted_close", "adj close"}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d")


@dataclass
class OHLCVRow:
    session_date: date
    close: Decimal
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    adj_close: Optional[Decimal] = None
    volume: Optional[int] = None


@dataclass
class OHLCVImportResult:
    inserted: int = 0
    skipped_duplicate: int = 0
    skipped_existing_source: bool = False
    parse_errors: list[str] = field(default_factory=list)
    source_id: Optional[str] = None


def _parse_date(val: str) -> Optional[date]:
    val = val.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(val: str) -> Optional[Decimal]:
    val = val.strip().replace(",", "")
    if not val or val in ("-", "N/A", "n/a", ""):
        return None
    try:
        return Decimal(val)
    except InvalidOperation:
        return None


def _parse_volume(val: str) -> Optional[int]:
    val = val.strip().replace(",", "")
    if not val or val in ("-", "N/A", "n/a", ""):
        return None
    try:
        return int(float(val))
    except (ValueError, OverflowError):
        return None


def _find_col(headers: list[str], candidates: set[str]) -> Optional[str]:
    """Cari nama kolom dari header CSV (case-insensitive)."""
    lower = {h.lower(): h for h in headers}
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def _file_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_ohlcv_csv(content: bytes) -> tuple[list[OHLCVRow], list[str]]:
    """
    Parse bytes CSV menjadi list OHLCVRow.
    Returns (rows, errors).
    """
    import csv

    rows: list[OHLCVRow] = []
    errors: list[str] = []

    # Coba beberapa encoding — utf-8-sig sebelum utf-8 agar BOM di-strip
    text: Optional[str] = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except (UnicodeDecodeError, ValueError):
            continue

    if text is None:
        return [], ["Gagal membaca file — coba simpan ulang sebagai UTF-8"]

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], ["File CSV tidak memiliki header"]

    headers = list(reader.fieldnames)
    date_col = _find_col(headers, _DATE_COLS)
    close_col = _find_col(headers, _CLOSE_COLS)

    if date_col is None:
        return [], [f"Kolom tanggal tidak ditemukan. Header: {headers}"]
    if close_col is None:
        return [], [f"Kolom close/harga tidak ditemukan. Header: {headers}"]

    open_col = _find_col(headers, _OPEN_COLS)
    high_col = _find_col(headers, _HIGH_COLS)
    low_col = _find_col(headers, _LOW_COLS)
    vol_col = _find_col(headers, _VOLUME_COLS)
    adj_col = _find_col(headers, _ADJ_CLOSE_COLS)

    for i, row in enumerate(reader, start=2):  # baris 1 = header
        raw_date = row.get(date_col, "").strip()
        raw_close = row.get(close_col, "").strip()

        if not raw_date and not raw_close:
            continue  # baris kosong

        session_date = _parse_date(raw_date)
        if session_date is None:
            errors.append(f"Baris {i}: tanggal tidak valid '{raw_date}'")
            continue

        close = _parse_decimal(raw_close)
        if close is None or close <= 0:
            errors.append(f"Baris {i}: close tidak valid '{raw_close}'")
            continue

        ohlcv = OHLCVRow(session_date=session_date, close=close)

        if open_col:
            v = _parse_decimal(row.get(open_col, ""))
            if v is not None and v > 0:
                ohlcv.open = v

        if high_col:
            v = _parse_decimal(row.get(high_col, ""))
            if v is not None and v > 0:
                ohlcv.high = v

        if low_col:
            v = _parse_decimal(row.get(low_col, ""))
            if v is not None and v > 0:
                ohlcv.low = v

        if adj_col:
            v = _parse_decimal(row.get(adj_col, ""))
            if v is not None and v > 0:
                ohlcv.adj_close = v

        if vol_col:
            vol = _parse_volume(row.get(vol_col, ""))
            if vol is not None and vol >= 0:
                ohlcv.volume = vol

        # Validasi high >= low jika keduanya ada
        if ohlcv.high is not None and ohlcv.low is not None and ohlcv.high < ohlcv.low:
            errors.append(f"Baris {i}: high ({ohlcv.high}) < low ({ohlcv.low}), baris dilewati")
            continue

        rows.append(ohlcv)

    return rows, errors


async def import_ohlcv_csv(
    db,  # AsyncSession
    instrument_id: str,
    provider: str,
    content: bytes,
    license_class: str = "PERSONAL_RESEARCH",
    source_url: Optional[str] = None,
) -> OHLCVImportResult:
    """
    Import OHLCV dari bytes CSV ke price_bars.

    - Idempotent: file yang sudah diimpor (checksum sama) tidak diproses ulang.
    - Duplikat per (instrument_id, session_date, provider) di-skip.
    - freshness_status = FRESH untuk baris baru.
    """
    from sqlalchemy import select
    from app.db.base import new_uuid
    from app.db.models import PriceBar, Source

    result = OHLCVImportResult()
    checksum = _file_checksum(content)

    # Cek apakah file sudah pernah diimpor
    existing_source = await db.scalar(
        select(Source.id).where(Source.checksum == checksum)
    )
    if existing_source:
        log.info("csv_ohlcv.skip_existing_source", checksum=checksum[:12], source_id=existing_source)
        result.skipped_existing_source = True
        result.source_id = existing_source
        return result

    # Parse CSV
    rows, parse_errors = parse_ohlcv_csv(content)
    result.parse_errors = parse_errors

    if not rows:
        log.warning("csv_ohlcv.no_rows_parsed", instrument_id=instrument_id, errors=len(parse_errors))
        return result

    # Buat Source row
    source = Source(
        id=new_uuid(),
        url=source_url,
        publisher="csv_import",
        title=f"OHLCV CSV import — {instrument_id} via {provider}",
        fetched_at=datetime.now(tz=timezone.utc),
        license_class=license_class,
        checksum=checksum,
        primary_or_secondary="SECONDARY",
        verification_status="UNVERIFIED",
    )
    db.add(source)

    # Ambil session_dates yang sudah ada untuk provider ini
    existing_dates_result = await db.execute(
        select(PriceBar.session_date).where(
            PriceBar.instrument_id == instrument_id,
            PriceBar.provider == provider,
        )
    )
    existing_dates = {r[0] for r in existing_dates_result.fetchall()}

    for row in rows:
        if row.session_date in existing_dates:
            result.skipped_duplicate += 1
            continue

        bar = PriceBar(
            instrument_id=instrument_id,
            session_date=row.session_date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            adj_close=row.adj_close,
            volume=row.volume,
            provider=provider,
            is_adjusted=False,
            adjustment_version="v1",
            freshness_status="FRESH",
            source_id=source.id,
        )
        db.add(bar)
        result.inserted += 1
        existing_dates.add(row.session_date)

    await db.flush()
    result.source_id = source.id

    log.info(
        "csv_ohlcv.import_complete",
        instrument_id=instrument_id,
        provider=provider,
        inserted=result.inserted,
        skipped=result.skipped_duplicate,
        errors=len(result.parse_errors),
    )
    return result

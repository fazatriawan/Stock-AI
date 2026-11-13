"""
Unit tests FREE-02 — OHLCV CSV Importer.

Fokus pada parse_ohlcv_csv (pure function, tanpa DB).
import_ohlcv_csv diuji dengan mock AsyncSession ringan.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.csv_ohlcv_importer import (
    OHLCVImportResult,
    OHLCVRow,
    _file_checksum,
    _find_col,
    _parse_date,
    _parse_decimal,
    _parse_volume,
    parse_ohlcv_csv,
)


# ---------------------------------------------------------------------------
# Helper: buat CSV bytes
# ---------------------------------------------------------------------------

def _csv(rows: list[str], header: str = "date,open,high,low,close,volume") -> bytes:
    return "\n".join([header] + rows).encode()


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_iso(self):
        assert _parse_date("2024-01-15") == date(2024, 1, 15)

    def test_slash_dmy(self):
        assert _parse_date("15/01/2024") == date(2024, 1, 15)

    def test_slash_mdy(self):
        assert _parse_date("01/15/2024") == date(2024, 1, 15)

    def test_compact(self):
        assert _parse_date("20240115") == date(2024, 1, 15)

    def test_invalid(self):
        assert _parse_date("not-a-date") is None

    def test_empty(self):
        assert _parse_date("") is None


# ---------------------------------------------------------------------------
# _parse_decimal
# ---------------------------------------------------------------------------

class TestParseDecimal:
    def test_normal(self):
        assert _parse_decimal("1234.56") == Decimal("1234.56")

    def test_comma_thousand(self):
        assert _parse_decimal("1,234.56") == Decimal("1234.56")

    def test_empty(self):
        assert _parse_decimal("") is None

    def test_dash(self):
        assert _parse_decimal("-") is None

    def test_na(self):
        assert _parse_decimal("N/A") is None

    def test_invalid(self):
        assert _parse_decimal("abc") is None


# ---------------------------------------------------------------------------
# _parse_volume
# ---------------------------------------------------------------------------

class TestParseVolume:
    def test_integer(self):
        assert _parse_volume("1000000") == 1_000_000

    def test_float_string(self):
        # beberapa provider export volume sebagai "1234567.0"
        assert _parse_volume("1234567.0") == 1_234_567

    def test_comma(self):
        assert _parse_volume("1,234,567") == 1_234_567

    def test_empty(self):
        assert _parse_volume("") is None

    def test_zero(self):
        assert _parse_volume("0") == 0


# ---------------------------------------------------------------------------
# _find_col
# ---------------------------------------------------------------------------

class TestFindCol:
    def test_exact_match(self):
        assert _find_col(["Date", "Close"], {"date"}) == "Date"

    def test_case_insensitive(self):
        assert _find_col(["DATE", "CLOSE"], {"date"}) == "DATE"

    def test_not_found(self):
        assert _find_col(["foo", "bar"], {"date"}) is None

    def test_alias(self):
        assert _find_col(["Last"], {"close", "close_price", "last", "last_price"}) == "Last"


# ---------------------------------------------------------------------------
# parse_ohlcv_csv — happy path
# ---------------------------------------------------------------------------

class TestParseOHLCVCSV:
    def test_basic_full_row(self):
        csv_bytes = _csv(["2024-01-15,100.0,105.0,99.0,102.5,500000"])
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert errors == []
        assert len(rows) == 1
        r = rows[0]
        assert r.session_date == date(2024, 1, 15)
        assert r.close == Decimal("102.5")
        assert r.open == Decimal("100.0")
        assert r.high == Decimal("105.0")
        assert r.low == Decimal("99.0")
        assert r.volume == 500_000

    def test_multiple_rows(self):
        csv_bytes = _csv([
            "2024-01-15,100,105,99,102,500000",
            "2024-01-16,102,108,101,107,600000",
        ])
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert len(rows) == 2
        assert errors == []

    def test_close_only_columns(self):
        csv_bytes = "date,close\n2024-01-15,102.5\n".encode()
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert len(rows) == 1
        assert rows[0].open is None
        assert rows[0].volume is None

    def test_alias_header_names(self):
        # Stooq-style header
        csv_bytes = "Date,Open,High,Low,Close,Volume\n2024-01-15,100,105,99,102,500000\n".encode()
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert len(rows) == 1
        assert errors == []

    def test_adj_close_column(self):
        csv_bytes = "date,open,high,low,close,adj_close,volume\n2024-01-15,100,105,99,102,101.5,500000\n".encode()
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert rows[0].adj_close == Decimal("101.5")

    def test_empty_lines_skipped(self):
        csv_bytes = "date,close\n2024-01-15,102\n\n2024-01-16,103\n".encode()
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert len(rows) == 2

    def test_utf8_bom(self):
        # .encode("utf-8-sig") menambahkan BOM secara otomatis
        csv_bytes = "date,close\n2024-01-15,102\n".encode("utf-8-sig")
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert len(rows) == 1

    def test_latin1_encoding(self):
        csv_bytes = "date,close\n2024-01-15,102\n".encode("latin-1")
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# parse_ohlcv_csv — error cases
# ---------------------------------------------------------------------------

class TestParseOHLCVErrors:
    def test_missing_date_column(self):
        csv_bytes = "foo,close\n2024-01-15,102\n".encode()
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert rows == []
        assert any("tanggal" in e for e in errors)

    def test_missing_close_column(self):
        csv_bytes = "date,open\n2024-01-15,100\n".encode()
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert rows == []
        assert any("close" in e for e in errors)

    def test_invalid_date_row(self):
        csv_bytes = _csv(["NOT_A_DATE,100,105,99,102,500"])
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert rows == []
        assert len(errors) == 1
        assert "Baris 2" in errors[0]

    def test_zero_close_rejected(self):
        csv_bytes = _csv(["2024-01-15,100,105,99,0,500"])
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert rows == []
        assert any("close" in e for e in errors)

    def test_negative_close_rejected(self):
        csv_bytes = _csv(["2024-01-15,100,105,99,-5,500"])
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert rows == []

    def test_high_less_than_low_rejected(self):
        csv_bytes = _csv(["2024-01-15,100,90,99,95,500"])  # high=90 < low=99
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert rows == []
        assert any("high" in e and "low" in e for e in errors)

    def test_mixed_valid_and_invalid(self):
        csv_bytes = _csv([
            "2024-01-15,100,105,99,102,500",
            "BAD_DATE,100,105,99,102,500",
            "2024-01-17,101,106,100,103,600",
        ])
        rows, errors = parse_ohlcv_csv(csv_bytes)
        assert len(rows) == 2
        assert len(errors) == 1

    def test_no_header(self):
        # DictReader tanpa header tidak bisa detect kolom
        csv_bytes = b""
        rows, errors = parse_ohlcv_csv(csv_bytes)
        # Empty file → no fieldnames or no rows — either way rows is empty
        assert rows == [] or errors != []


# ---------------------------------------------------------------------------
# _file_checksum
# ---------------------------------------------------------------------------

class TestFileChecksum:
    def test_deterministic(self):
        b = b"hello world"
        assert _file_checksum(b) == _file_checksum(b)

    def test_different_content(self):
        assert _file_checksum(b"aaa") != _file_checksum(b"bbb")

    def test_sha256_length(self):
        assert len(_file_checksum(b"test")) == 64


# ---------------------------------------------------------------------------
# import_ohlcv_csv — unit with mock DB
# ---------------------------------------------------------------------------

class TestImportOHLCVCSV:
    """
    Uji logika idempoten tanpa DB asli.
    DB di-mock dengan AsyncMock.
    """

    def _make_db(self, scalar_return=None, fetchall_return=None):
        """Buat mock DB: add/flush sync, scalar/execute/flush async."""
        db = MagicMock()
        db.scalar = AsyncMock(return_value=scalar_return)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = fetchall_return or []
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_skip_existing_source(self):
        """File yang sudah pernah diimpor (checksum sama) harus di-skip."""
        from app.ingestion.csv_ohlcv_importer import import_ohlcv_csv

        db = self._make_db(scalar_return="existing-source-id")
        csv_bytes = _csv(["2024-01-15,100,105,99,102,500"])
        result = await import_ohlcv_csv(db, "BBCA", "yfinance", csv_bytes)

        assert result.skipped_existing_source is True
        assert result.source_id == "existing-source-id"
        assert result.inserted == 0

    @pytest.mark.asyncio
    async def test_insert_new_rows(self):
        """Baris baru harus di-insert, Source row dibuat."""
        from app.ingestion.csv_ohlcv_importer import import_ohlcv_csv

        db = self._make_db(scalar_return=None, fetchall_return=[])
        csv_bytes = _csv([
            "2024-01-15,100,105,99,102,500",
            "2024-01-16,102,108,101,107,600",
        ])
        result = await import_ohlcv_csv(db, "BBCA", "yfinance", csv_bytes)

        assert result.inserted == 2
        assert result.skipped_duplicate == 0
        assert result.parse_errors == []
        assert result.source_id is not None

    @pytest.mark.asyncio
    async def test_skip_duplicate_dates(self):
        """Tanggal yang sudah ada di DB harus di-skip."""
        from app.ingestion.csv_ohlcv_importer import import_ohlcv_csv

        db = self._make_db(scalar_return=None, fetchall_return=[(date(2024, 1, 15),)])
        csv_bytes = _csv([
            "2024-01-15,100,105,99,102,500",  # duplikat
            "2024-01-16,102,108,101,107,600",  # baru
        ])
        result = await import_ohlcv_csv(db, "BBCA", "yfinance", csv_bytes)

        assert result.inserted == 1
        assert result.skipped_duplicate == 1

    @pytest.mark.asyncio
    async def test_parse_errors_returned(self):
        """Error baris tetap dikembalikan meski sebagian berhasil."""
        from app.ingestion.csv_ohlcv_importer import import_ohlcv_csv

        db = self._make_db(scalar_return=None, fetchall_return=[])
        csv_bytes = _csv([
            "2024-01-15,100,105,99,102,500",
            "BAD_DATE,100,105,99,102,500",
        ])
        result = await import_ohlcv_csv(db, "BBCA", "yfinance", csv_bytes)

        assert result.inserted == 1
        assert len(result.parse_errors) == 1

    @pytest.mark.asyncio
    async def test_empty_csv_no_rows(self):
        """CSV tanpa baris valid tidak crash."""
        from app.ingestion.csv_ohlcv_importer import import_ohlcv_csv

        db = self._make_db(scalar_return=None)
        csv_bytes = "date,close\n".encode()
        result = await import_ohlcv_csv(db, "BBCA", "yfinance", csv_bytes)

        assert result.inserted == 0
        assert result.skipped_existing_source is False

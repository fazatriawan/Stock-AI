"""
Unit test untuk portfolio importers (Phase 2).
Menguji: fingerprint generator, CSV parser, format detection, symbol normalisation.
"""
from __future__ import annotations

from datetime import date


from app.portfolio.importers.base import BrokerFormat, ValidationStatus
from app.portfolio.importers.fingerprint import generate_fingerprint
from app.portfolio.importers.csv_importer import (
    _detect_format,
    _normalise_symbol,
    _parse_date,
    _parse_number,
    _parse_side,
    parse_csv,
)

import pandas as pd


# ---------------------------------------------------------------------------
# Fingerprint tests
# ---------------------------------------------------------------------------

class TestGenerateFingerprint:
    def test_returns_32_chars(self):
        fp = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0)
        assert len(fp) == 32

    def test_deterministic(self):
        fp1 = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0)
        fp2 = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0)
        assert fp1 == fp2

    def test_case_insensitive_symbol(self):
        fp1 = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0)
        fp2 = generate_fingerprint("idx:bmri", date(2024, 1, 2), "buy", 1100, 4900.0)
        assert fp1 == fp2

    def test_different_date_different_fp(self):
        fp1 = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0)
        fp2 = generate_fingerprint("IDX:BMRI", date(2024, 1, 3), "BUY", 1100, 4900.0)
        assert fp1 != fp2

    def test_different_price_different_fp(self):
        fp1 = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0)
        fp2 = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4901.0)
        assert fp1 != fp2

    def test_different_side_different_fp(self):
        fp_buy = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0)
        fp_sell = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "SELL", 1100, 4900.0)
        assert fp_buy != fp_sell

    def test_different_broker_different_fp(self):
        fp1 = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0, "STOCKBIT")
        fp2 = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0, "BNI_SEKURITAS")
        assert fp1 != fp2

    def test_default_broker(self):
        fp = generate_fingerprint("IDX:BMRI", date(2024, 1, 2), "BUY", 1100, 4900.0)
        assert len(fp) == 32


# ---------------------------------------------------------------------------
# Symbol normalisation tests
# ---------------------------------------------------------------------------

class TestNormaliseSymbol:
    def test_plain_code(self):
        assert _normalise_symbol("BMRI") == "IDX:BMRI"

    def test_with_jk_suffix(self):
        assert _normalise_symbol("BMRI.JK") == "IDX:BMRI"

    def test_with_jkt_suffix(self):
        assert _normalise_symbol("BBRI.JKT") == "IDX:BBRI"

    def test_already_has_prefix(self):
        assert _normalise_symbol("IDX:BBCA") == "IDX:BBCA"

    def test_lowercase_input(self):
        assert _normalise_symbol("bmri") == "IDX:BMRI"

    def test_strips_whitespace(self):
        assert _normalise_symbol("  BBNI  ") == "IDX:BBNI"


# ---------------------------------------------------------------------------
# Date parsing tests
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_iso_format(self):
        assert _parse_date("2024-01-15") == date(2024, 1, 15)

    def test_slash_ddmmyyyy(self):
        assert _parse_date("15/01/2024") == date(2024, 1, 15)

    def test_dash_ddmmyyyy(self):
        assert _parse_date("15-01-2024") == date(2024, 1, 15)

    def test_abbrev_month(self):
        assert _parse_date("15 Jan 2024") == date(2024, 1, 15)

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_nan(self):
        assert _parse_date("nan") is None

    def test_invalid(self):
        assert _parse_date("tanggal invalid") is None


# ---------------------------------------------------------------------------
# Number parsing tests
# ---------------------------------------------------------------------------

class TestParseNumber:
    def test_plain_integer(self):
        assert _parse_number("1000") == 1000.0

    def test_with_rp_prefix(self):
        assert _parse_number("Rp 5000") == 5000.0

    def test_none_input(self):
        assert _parse_number(None) is None

    def test_empty(self):
        assert _parse_number("") is None

    def test_float(self):
        assert _parse_number("4900.5") == 4900.5


# ---------------------------------------------------------------------------
# Side parsing tests
# ---------------------------------------------------------------------------

class TestParseSide:
    def test_buy_english(self):
        assert _parse_side("BUY") == "BUY"

    def test_buy_indonesian(self):
        assert _parse_side("BELI") == "BUY"

    def test_sell_english(self):
        assert _parse_side("SELL") == "SELL"

    def test_sell_indonesian(self):
        assert _parse_side("JUAL") == "SELL"

    def test_b_shorthand(self):
        assert _parse_side("B") == "BUY"

    def test_s_shorthand(self):
        assert _parse_side("S") == "SELL"

    def test_invalid(self):
        assert _parse_side("XYZ") is None

    def test_case_insensitive(self):
        assert _parse_side("buy") == "BUY"
        assert _parse_side("jual") == "SELL"


# ---------------------------------------------------------------------------
# Format detection tests
# ---------------------------------------------------------------------------

class TestDetectFormat:
    def test_stockbit_format(self):
        df = pd.DataFrame(columns=["Tanggal", "Kode Saham", "Jenis", "Lot", "Harga", "Fee"])
        result = _detect_format(df)
        assert result == BrokerFormat.STOCKBIT

    def test_bni_format(self):
        df = pd.DataFrame(columns=["Date", "Stock Code", "Side", "Volume (Lot)", "Execution Price"])
        result = _detect_format(df)
        assert result == BrokerFormat.BNI_SEKURITAS

    def test_generic_format(self):
        df = pd.DataFrame(columns=["date", "symbol", "side", "qty", "price"])
        result = _detect_format(df)
        assert result == BrokerFormat.GENERIC_CSV


# ---------------------------------------------------------------------------
# Full CSV parse tests
# ---------------------------------------------------------------------------

class TestParseCSV:
    def _make_stockbit_csv(self, rows: list[dict]) -> bytes:
        """Buat konten CSV Stockbit format."""
        lines = ["Tanggal,Kode Saham,Jenis,Lot,Harga,Fee"]
        for r in rows:
            lines.append(f"{r['date']},{r['symbol']},{r['side']},{r['lot']},{r['price']},{r.get('fee', 0)}")
        return "\n".join(lines).encode("utf-8")

    def test_single_buy(self):
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000},
        ])
        result = parse_csv(content, "STOCKBIT")
        assert result.broker_format == BrokerFormat.STOCKBIT
        assert result.total_rows == 1
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.canonical_symbol == "IDX:BMRI"
        assert t.side == "BUY"
        assert t.lots == 10
        assert t.shares == 1000  # 10 lot × 100
        assert t.price == 5000.0
        assert t.status == ValidationStatus.OK

    def test_buy_and_sell(self):
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000},
            {"date": "2024-01-16", "symbol": "BMRI", "side": "Jual", "lot": 5, "price": 5200},
        ])
        result = parse_csv(content)
        assert result.total_rows == 2
        assert result.valid_count == 2
        assert result.trades[0].side == "BUY"
        assert result.trades[1].side == "SELL"

    def test_multiple_symbols(self):
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000},
            {"date": "2024-01-15", "symbol": "BBRI", "side": "Beli", "lot": 5, "price": 4200},
        ])
        result = parse_csv(content)
        symbols = {t.canonical_symbol for t in result.trades}
        assert "IDX:BMRI" in symbols
        assert "IDX:BBRI" in symbols

    def test_invalid_side_marks_error(self):
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI", "side": "HOLD", "lot": 10, "price": 5000},
        ])
        result = parse_csv(content)
        assert result.error_count == 1
        assert result.trades[0].status == ValidationStatus.ERROR

    def test_invalid_date_marks_error(self):
        content = self._make_stockbit_csv([
            {"date": "tanggal-error", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000},
        ])
        result = parse_csv(content)
        assert result.trades[0].status == ValidationStatus.ERROR

    def test_fingerprint_generated_for_valid_trade(self):
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000},
        ])
        result = parse_csv(content)
        assert len(result.trades[0].fingerprint) == 32

    def test_fingerprint_not_generated_for_error_trade(self):
        content = self._make_stockbit_csv([
            {"date": "invalid", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000},
        ])
        result = parse_csv(content)
        assert result.trades[0].fingerprint == ""

    def test_empty_csv(self):
        content = b"Tanggal,Kode Saham,Jenis,Lot,Harga\n"
        result = parse_csv(content)
        assert result.total_rows == 0

    def test_empty_bytes(self):
        result = parse_csv(b"")
        assert result.total_rows == 0
        assert len(result.parse_errors) > 0

    def test_jk_symbol_normalised(self):
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI.JK", "side": "Beli", "lot": 10, "price": 5000},
        ])
        result = parse_csv(content)
        assert result.trades[0].canonical_symbol == "IDX:BMRI"

    def test_fee_parsed(self):
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000, "fee": 15000},
        ])
        result = parse_csv(content)
        assert result.trades[0].fee == 15000.0

    def test_row_number_starts_at_2(self):
        """Baris pertama data = baris 2 (baris 1 adalah header)."""
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000},
        ])
        result = parse_csv(content)
        assert result.trades[0].row_number == 2

    def test_valid_count_and_error_count(self):
        content = self._make_stockbit_csv([
            {"date": "2024-01-15", "symbol": "BMRI", "side": "Beli", "lot": 10, "price": 5000},
            {"date": "bad-date", "symbol": "BBRI", "side": "Jual", "lot": 5, "price": 4200},
        ])
        result = parse_csv(content)
        assert result.valid_count == 1
        assert result.error_count == 1

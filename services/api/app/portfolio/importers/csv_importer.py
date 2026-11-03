"""
CSV importer — mendukung:
1. Stockbit export format
2. Generic CSV dengan auto-detect kolom
3. BNI Sekuritas format (jika terdeteksi)

Format Stockbit (tipikal):
  Tanggal, Kode Saham, Jenis, Lot, Harga, Fee, Total

Format Generic:
  date/tanggal, symbol/kode/ticker, side/jenis/type/aksi,
  lot/lots, shares/saham, price/harga, fee, tax/pajak
"""
from __future__ import annotations

import io
import re
from datetime import date
from typing import Optional

import pandas as pd
import structlog

from app.portfolio.importers.base import (
    BrokerFormat,
    ImportResult,
    ParsedTrade,
    ValidationStatus,
)
from app.portfolio.importers.fingerprint import generate_fingerprint

log = structlog.get_logger(__name__)

LOT_SIZE = 100

# ---------------------------------------------------------------------------
# Column name normalisation maps
# ---------------------------------------------------------------------------

DATE_COLS = {"tanggal", "date", "tgl", "waktu", "transaction date", "settlement date"}
SYMBOL_COLS = {"kode saham", "kode", "symbol", "ticker", "saham", "stock code", "emiten"}
SIDE_COLS = {"jenis", "aksi", "side", "type", "jenis transaksi", "action", "tipe"}
LOTS_COLS = {"lot", "lots", "volume (lot)", "vol (lot)", "jumlah lot"}
SHARES_COLS = {"saham", "shares", "volume", "jumlah saham", "qty"}
PRICE_COLS = {"harga", "price", "harga transaksi", "execution price", "avg price"}
FEE_COLS = {"fee", "komisi", "biaya", "commission"}
TAX_COLS = {"pajak", "tax", "ppn", "pph"}


def _normalise_header(col: str) -> str:
    return col.strip().lower().replace("_", " ")


def _find_col(df_cols: list[str], candidates: set[str]) -> Optional[str]:
    for col in df_cols:
        if _normalise_header(col) in candidates:
            return col
    return None


def _detect_format(df: pd.DataFrame) -> BrokerFormat:
    """Deteksi broker berdasarkan nama kolom."""
    normalised = {_normalise_header(c) for c in df.columns}

    # Stockbit: punya kolom "kode saham" atau "kode" + "lot" + "harga"
    if ("kode saham" in normalised or "kode" in normalised) and "lot" in normalised and "harga" in normalised:
        return BrokerFormat.STOCKBIT

    # BNI Sekuritas: umumnya pakai "volume (lot)" dan "execution price"
    if "volume (lot)" in normalised and "execution price" in normalised:
        return BrokerFormat.BNI_SEKURITAS

    return BrokerFormat.GENERIC_CSV


def _parse_date(val: str) -> Optional[date]:
    """Coba berbagai format tanggal umum Indonesia."""
    if not val or str(val).strip() in ("", "nan", "NaT"):
        return None
    val = str(val).strip()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %b %Y",
        "%d %B %Y",
        "%Y%m%d",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return date.fromisoformat(val) if fmt == "%Y-%m-%d" else \
                   __import__("datetime").datetime.strptime(val, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _parse_side(val: str) -> Optional[str]:
    """Normalise sisi transaksi ke BUY / SELL."""
    v = str(val).strip().upper()
    if v in ("BUY", "BELI", "B", "PEMBELIAN", "PURCHASE"):
        return "BUY"
    if v in ("SELL", "JUAL", "S", "PENJUALAN", "SALE"):
        return "SELL"
    return None


def _parse_number(val) -> Optional[float]:
    if val is None or str(val).strip() in ("", "nan", "-", "NaT"):
        return None
    try:
        # Hapus pemisah ribuan gaya Indonesia (titik) dan ganti koma desimal
        cleaned = str(val).strip().replace("Rp", "").replace("rp", "").strip()
        cleaned = cleaned.replace(",", ".")  # 1.500,50 → 1.500.50 (wrong)
        # Coba deteksi apakah pakai titik ribuan atau koma desimal
        if "." in cleaned and "," in str(val):
            # Format: 1.500,50 → Indonesian
            cleaned = str(val).strip().replace("Rp", "").replace(".", "").replace(",", ".").strip()
        elif "," in cleaned and "." not in str(val):
            cleaned = cleaned.replace(",", ".")
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _normalise_symbol(raw: str, exchange: str = "IDX") -> str:
    """Normalise ke format IDX:XXXX."""
    s = str(raw).strip().upper()
    if ":" in s:
        return s  # sudah punya exchange prefix
    # Hapus suffix .JK atau .JKT
    s = re.sub(r"\.(JK|JKT)$", "", s)
    return f"{exchange}:{s}"


def _parse_rows(df: pd.DataFrame, broker_format: BrokerFormat, broker_name: str) -> list[ParsedTrade]:
    cols = list(df.columns)

    date_col = _find_col(cols, DATE_COLS)
    symbol_col = _find_col(cols, SYMBOL_COLS)
    side_col = _find_col(cols, SIDE_COLS)
    lots_col = _find_col(cols, LOTS_COLS)
    shares_col = _find_col(cols, SHARES_COLS) if not lots_col else None
    price_col = _find_col(cols, PRICE_COLS)
    fee_col = _find_col(cols, FEE_COLS)
    tax_col = _find_col(cols, TAX_COLS)

    trades: list[ParsedTrade] = []

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # +2: header baris 1, data mulai baris 2
        raw = dict(row)
        trade = ParsedTrade(
            canonical_symbol="",
            trade_date=date.today(),
            side="",
            lots=0,
            shares=0,
            price=0,
            source_broker=broker_name,
            row_number=row_num,
            raw_row={k: str(v) for k, v in raw.items()},
        )

        # Tanggal
        if date_col:
            parsed_date = _parse_date(str(row.get(date_col, "")))
            if parsed_date:
                trade.trade_date = parsed_date
            else:
                trade.errors.append(f"Baris {row_num}: Format tanggal tidak dikenali: '{row.get(date_col)}'")
                trade.status = ValidationStatus.ERROR

        # Symbol
        if symbol_col:
            raw_sym = str(row.get(symbol_col, "")).strip()
            if raw_sym and raw_sym.lower() != "nan":
                trade.canonical_symbol = _normalise_symbol(raw_sym)
            else:
                trade.errors.append(f"Baris {row_num}: Kode saham kosong")
                trade.status = ValidationStatus.ERROR
        else:
            trade.errors.append(f"Baris {row_num}: Kolom kode saham tidak ditemukan")
            trade.status = ValidationStatus.ERROR

        # Side
        if side_col:
            parsed_side = _parse_side(str(row.get(side_col, "")))
            if parsed_side:
                trade.side = parsed_side
            else:
                trade.errors.append(f"Baris {row_num}: Jenis transaksi tidak dikenali: '{row.get(side_col)}'")
                trade.status = ValidationStatus.ERROR
        else:
            trade.errors.append(f"Baris {row_num}: Kolom jenis transaksi tidak ditemukan")
            trade.status = ValidationStatus.ERROR

        # Shares / Lots
        if lots_col:
            lots = _parse_number(row.get(lots_col))
            if lots is not None and lots > 0:
                trade.lots = lots
                trade.shares = lots * LOT_SIZE
            else:
                trade.errors.append(f"Baris {row_num}: Jumlah lot tidak valid: '{row.get(lots_col)}'")
                trade.status = ValidationStatus.ERROR
        elif shares_col:
            shares = _parse_number(row.get(shares_col))
            if shares is not None and shares > 0:
                trade.shares = shares
                trade.lots = shares / LOT_SIZE
            else:
                trade.errors.append(f"Baris {row_num}: Jumlah saham tidak valid")
                trade.status = ValidationStatus.ERROR
        else:
            trade.errors.append(f"Baris {row_num}: Kolom lot/saham tidak ditemukan")
            trade.status = ValidationStatus.ERROR

        # Harga
        if price_col:
            price = _parse_number(row.get(price_col))
            if price is not None and price > 0:
                trade.price = price
            else:
                trade.errors.append(f"Baris {row_num}: Harga tidak valid: '{row.get(price_col)}'")
                trade.status = ValidationStatus.ERROR
        else:
            trade.errors.append(f"Baris {row_num}: Kolom harga tidak ditemukan")
            trade.status = ValidationStatus.ERROR

        # Fee (opsional)
        if fee_col:
            fee = _parse_number(row.get(fee_col))
            trade.fee = fee or 0.0

        # Tax (opsional)
        if tax_col:
            tax = _parse_number(row.get(tax_col))
            trade.tax = tax or 0.0

        # Fingerprint (hanya jika data valid)
        if trade.status != ValidationStatus.ERROR and trade.canonical_symbol and trade.side:
            trade.fingerprint = generate_fingerprint(
                trade.canonical_symbol,
                trade.trade_date,
                trade.side,
                trade.shares,
                trade.price,
                broker_name,
            )

        trades.append(trade)

    return trades


def parse_csv(content: bytes, broker_hint: Optional[str] = None) -> ImportResult:
    """
    Parse file CSV dari broker.

    Args:
        content: bytes konten file CSV
        broker_hint: nama broker dari user (opsional, untuk logging)
    Returns:
        ImportResult dengan list ParsedTrade
    """
    parse_errors: list[str] = []

    # Coba beberapa encoding umum
    df: Optional[pd.DataFrame] = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(io.BytesIO(content), encoding=encoding, dtype=str)
            break
        except Exception:
            continue

    if df is None:
        return ImportResult(
            broker_format=BrokerFormat.UNKNOWN,
            trades=[],
            total_rows=0,
            parse_errors=["Gagal membaca file CSV — coba simpan ulang sebagai UTF-8"],
        )

    # Hapus baris kosong
    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty:
        return ImportResult(
            broker_format=BrokerFormat.UNKNOWN,
            trades=[],
            total_rows=0,
            parse_errors=["File CSV kosong atau tidak ada data transaksi"],
        )

    broker_format = _detect_format(df)
    broker_name = broker_hint or broker_format.value

    log.info(
        "csv.parse",
        rows=len(df),
        format=broker_format,
        columns=list(df.columns),
    )

    trades = _parse_rows(df, broker_format, broker_name)

    return ImportResult(
        broker_format=broker_format,
        trades=trades,
        total_rows=len(df),
        parse_errors=parse_errors,
    )

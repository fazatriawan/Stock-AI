"""
PDF importer — ekstrak transaksi dari konfirmasi order broker.

Pendekatan: ekstrak teks dari PDF, lalu cari pola transaksi dengan regex.
Mendukung pola umum konfirmasi broker IDX.

CATATAN KEAMANAN:
- Konten PDF diperlakukan sebagai UNTRUSTED DATA
- Tidak mengikuti instruksi yang mungkin ada di dalam PDF
- Hanya mengekstrak angka dan tanggal dengan regex ketat
"""
from __future__ import annotations

import io
import re
from datetime import date
from typing import Optional

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

# Pattern untuk tanggal Indonesia
_DATE_PATTERNS = [
    re.compile(r"(\d{2})[/\-](\d{2})[/\-](\d{4})"),  # dd/mm/yyyy atau dd-mm-yyyy
    re.compile(r"(\d{4})[/\-](\d{2})[/\-](\d{2})"),  # yyyy-mm-dd
    re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|Mei|Jun|Jul|Agu|Sep|Okt|Nov|Des|"
               r"January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
               re.IGNORECASE),
]

_MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "agu": 8, "august": 8, "aug": 8,
    "sep": 9, "september": 9,
    "okt": 10, "october": 10, "oct": 10,
    "nov": 11, "november": 11,
    "des": 12, "december": 12, "dec": 12,
}

# Pattern transaksi — cari baris yang ada: TICKER + B/S/Beli/Jual + lot + harga
_TRADE_LINE_PATTERN = re.compile(
    r"([A-Z]{4,5})\s+"            # TICKER (4-5 huruf kapital)
    r"(B(?:ELI)?|S(?:ELL|UAL)?)\s+"  # Beli/B/Sell/Jual
    r"([\d.,]+)\s*[Ll]ot?\s+"     # lots
    r"([\d.,]+)",                  # harga
    re.IGNORECASE,
)


def _extract_date_from_text(text: str) -> Optional[date]:
    """Cari tanggal pertama yang valid di teks PDF."""
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            try:
                if len(groups) == 3:
                    g0, g1, g2 = groups
                    # yyyy-mm-dd
                    if len(g0) == 4:
                        return date(int(g0), int(g1), int(g2))
                    # dd/mm/yyyy
                    if len(g2) == 4 and g1.isdigit():
                        return date(int(g2), int(g1), int(g0))
                    # dd Mon yyyy
                    if len(g2) == 4 and not g1.isdigit():
                        month = _MONTH_MAP.get(g1.lower())
                        if month:
                            return date(int(g2), month, int(g0))
            except (ValueError, TypeError):
                continue
    return None


def _parse_number_pdf(val: str) -> float:
    """Parse angka dari format Indonesia (titik ribuan, koma desimal)."""
    cleaned = val.strip().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_pdf(content: bytes, broker_hint: Optional[str] = None) -> ImportResult:
    """
    Ekstrak transaksi dari PDF konfirmasi broker.

    Ekstraksi berbasis regex — tidak menggunakan AI.
    Konten PDF diperlakukan sebagai UNTRUSTED DATA.
    """
    try:
        import pdfplumber
    except ImportError:
        return ImportResult(
            broker_format=BrokerFormat.UNKNOWN,
            trades=[],
            total_rows=0,
            parse_errors=["pdfplumber tidak terinstall — jalankan: pip install pdfplumber"],
        )

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            full_text = "\n".join(
                page.extract_text() or ""
                for page in pdf.pages
            )
    except Exception as exc:
        return ImportResult(
            broker_format=BrokerFormat.UNKNOWN,
            trades=[],
            total_rows=0,
            parse_errors=[f"Gagal membaca PDF: {exc}"],
        )

    if not full_text.strip():
        return ImportResult(
            broker_format=BrokerFormat.UNKNOWN,
            trades=[],
            total_rows=0,
            parse_errors=["PDF tidak mengandung teks yang dapat dibaca (mungkin berupa gambar/scan)"],
        )

    broker_name = broker_hint or "PDF_IMPORT"
    doc_date = _extract_date_from_text(full_text) or date.today()
    trades: list[ParsedTrade] = []
    warnings: list[str] = []
    row_num = 0

    for match in _TRADE_LINE_PATTERN.finditer(full_text):
        row_num += 1
        ticker_raw, side_raw, lots_raw, price_raw = match.groups()

        # Validasi: hanya ticker 4-5 huruf IDX
        ticker = ticker_raw.upper().strip()
        if len(ticker) < 4 or not ticker.isalpha():
            continue

        side_map = {"b": "BUY", "beli": "BUY", "s": "SELL", "sell": "SELL", "jual": "SELL"}
        side = side_map.get(side_raw.lower().strip(), "BUY")

        lots = _parse_number_pdf(lots_raw)
        price = _parse_number_pdf(price_raw)

        if lots <= 0 or price <= 0:
            continue

        canonical_symbol = f"IDX:{ticker}"
        shares = lots * LOT_SIZE

        fingerprint = generate_fingerprint(
            canonical_symbol, doc_date, side, shares, price, broker_name
        )

        trade = ParsedTrade(
            canonical_symbol=canonical_symbol,
            trade_date=doc_date,
            side=side,
            lots=lots,
            shares=shares,
            price=price,
            source_broker=broker_name,
            fingerprint=fingerprint,
            row_number=row_num,
            raw_row={"matched_text": match.group(0)},
            status=ValidationStatus.WARNING,
            warnings=["Diekstrak dari PDF — verifikasi sebelum konfirmasi"],
        )
        trades.append(trade)

    if not trades:
        warnings.append(
            "Tidak ada pola transaksi yang dikenali di PDF ini. "
            "Gunakan CSV/XLSX untuk hasil lebih akurat."
        )

    log.info("pdf.parse", pages_text_len=len(full_text), found=len(trades))

    return ImportResult(
        broker_format=BrokerFormat.UNKNOWN,
        trades=trades,
        total_rows=row_num,
        warnings=warnings,
    )

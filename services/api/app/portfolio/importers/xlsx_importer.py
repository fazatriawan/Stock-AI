"""
XLSX importer — membaca Excel dari broker.
Menggunakan engine openpyxl via pandas, lalu delegate ke logika CSV parser.
"""
from __future__ import annotations

import io
from typing import Optional

import pandas as pd
import structlog

from app.portfolio.importers.base import BrokerFormat, ImportResult
from app.portfolio.importers.csv_importer import _detect_format, _parse_rows

log = structlog.get_logger(__name__)


def parse_xlsx(content: bytes, broker_hint: Optional[str] = None, sheet_name: int = 0) -> ImportResult:
    """
    Parse file XLSX dari broker.

    Args:
        content: bytes konten file Excel
        broker_hint: nama broker dari user (opsional)
        sheet_name: indeks sheet (default 0 = sheet pertama)
    """
    try:
        df = pd.read_excel(
            io.BytesIO(content),
            sheet_name=sheet_name,
            dtype=str,
            engine="openpyxl",
        )
    except Exception as exc:
        return ImportResult(
            broker_format=BrokerFormat.UNKNOWN,
            trades=[],
            total_rows=0,
            parse_errors=[f"Gagal membaca file Excel: {exc}"],
        )

    # Hapus baris kosong
    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty:
        return ImportResult(
            broker_format=BrokerFormat.UNKNOWN,
            trades=[],
            total_rows=0,
            parse_errors=["File Excel kosong atau tidak ada data transaksi"],
        )

    broker_format = _detect_format(df)
    broker_name = broker_hint or broker_format.value

    log.info(
        "xlsx.parse",
        rows=len(df),
        format=broker_format,
        columns=list(df.columns),
    )

    trades = _parse_rows(df, broker_format, broker_name)

    return ImportResult(
        broker_format=broker_format,
        trades=trades,
        total_rows=len(df),
    )

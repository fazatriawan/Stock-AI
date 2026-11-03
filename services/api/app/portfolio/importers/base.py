"""
Base types untuk import pipeline.
Semua parser mengembalikan list[ParsedTrade] yang siap divalidasi dan di-commit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class BrokerFormat(str, Enum):
    STOCKBIT = "STOCKBIT"
    BNI_SEKURITAS = "BNI_SEKURITAS"
    MIRAE = "MIRAE"
    IPOT = "IPOT"
    GENERIC_CSV = "GENERIC_CSV"
    UNKNOWN = "UNKNOWN"


class ValidationStatus(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class ParsedTrade:
    """Satu baris transaksi yang diparsing dari file broker."""
    # Data inti
    canonical_symbol: str        # sudah dinormalisasi ke IDX:XXXX atau US:XXXX
    trade_date: date
    side: str                    # BUY / SELL
    lots: float                  # lot (1 lot = 100 saham untuk IDX)
    shares: float                # lots * lot_size
    price: float                 # harga per saham
    fee: float = 0.0
    tax: float = 0.0
    currency: str = "IDR"
    source_broker: str = "IMPORT"

    # Metadata import
    fingerprint: str = ""        # hash deterministik untuk dedup
    row_number: int = 0          # nomor baris di file asli
    raw_row: dict = field(default_factory=dict)  # baris mentah untuk audit trail

    # Validasi
    status: ValidationStatus = ValidationStatus.OK
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Notes
    notes: Optional[str] = None


@dataclass
class ImportResult:
    """Hasil parsing satu file."""
    broker_format: BrokerFormat
    trades: list[ParsedTrade]
    total_rows: int = 0
    parse_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return sum(1 for t in self.trades if t.status != ValidationStatus.ERROR)

    @property
    def error_count(self) -> int:
        return sum(1 for t in self.trades if t.status == ValidationStatus.ERROR)

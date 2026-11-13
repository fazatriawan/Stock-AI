"""
Provider contract sesuai PRD §9.2.
Setiap provider HARUS mengimplementasikan interface ini.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol, runtime_checkable


class ProviderStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class LicenseStatus(str, Enum):
    FREE_PERSONAL = "FREE_PERSONAL"   # gratis untuk riset pribadi
    PAID = "PAID"                     # berbayar / berlangganan
    RESTRICTED = "RESTRICTED"         # ada syarat khusus (ToS, registrasi)
    UNKNOWN = "UNKNOWN"


class AccessStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"             # provider tidak dikonfigurasi / dinonaktifkan
    NOT_CONFIGURED = "NOT_CONFIGURED" # API key / paket tidak tersedia
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    LICENSE_BLOCKED = "LICENSE_BLOCKED"


@dataclass
class ProviderCapability:
    """
    Deklarasi kemampuan dan metadata akses sebuah provider.
    Digunakan oleh budget guard dan Data Health UI.
    """
    license_status: LicenseStatus
    access_status: AccessStatus
    cost: str                              # "free" / "paid" / "unknown"
    granularity: str                       # "daily" / "intraday" / "snapshot"
    freshness_policy: str                  # "EOD" / "on_demand" / "manual_import"
    supports_point_in_time: bool
    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None    # None = ongoing
    quota_per_day: Optional[int] = None
    quota_remaining: Optional[int] = None
    datasets: list[str] = field(default_factory=list)  # ["ohlcv", "fundamental", ...]
    notes: Optional[str] = None


@dataclass
class ProviderHealth:
    provider: str
    status: ProviderStatus
    last_success: Optional[datetime] = None
    last_error: Optional[str] = None
    latency_ms: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class Bar:
    """Satu candle OHLCV harian. adj_close bisa None jika provider tidak menyediakan."""
    instrument_id: str
    session_date: date
    open: Optional[Decimal]
    high: Optional[Decimal]
    low: Optional[Decimal]
    close: Decimal
    adj_close: Optional[Decimal]
    volume: Optional[int]
    provider: str
    is_adjusted: bool = False
    adjustment_version: str = "v1"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.close <= 0:
            errors.append(f"close <= 0: {self.close}")
        if self.high is not None and self.low is not None and self.high < self.low:
            errors.append(f"high < low: {self.high} < {self.low}")
        if self.open is not None and self.open <= 0:
            errors.append(f"open <= 0: {self.open}")
        if self.volume is not None and self.volume < 0:
            errors.append(f"volume < 0: {self.volume}")
        return errors


@dataclass
class Fact:
    """Satu data point fundamental/metrik."""
    instrument_id: str
    metric: str
    value: Optional[Decimal]
    value_text: Optional[str]
    period_end: date
    period_start: Optional[date]
    filing_date: Optional[date]
    available_at: Optional[date]
    unit: Optional[str]
    currency: Optional[str]
    accounting_basis: Optional[str]
    source_url: Optional[str]
    provider: str
    published_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    license_class: str = "UNKNOWN"
    validation_status: str = "UNVERIFIED"


@dataclass
class CorporateActionRecord:
    instrument_id: str
    action_type: str  # SPLIT, DIVIDEND, RIGHTS, MERGER
    effective_at: date
    announced_at: Optional[date]
    ratio: Optional[Decimal]
    cash_amount: Optional[Decimal]
    currency: Optional[str]
    status: str
    source_url: Optional[str]
    provider: str


@dataclass
class InstrumentInfo:
    canonical_symbol: str
    local_symbol: str
    exchange: str
    country: str
    currency: str
    timezone: str
    asset_type: str = "EQUITY"
    sector: Optional[str] = None
    industry: Optional[str] = None
    company_name: Optional[str] = None
    mic: Optional[str] = None
    provider: str = "unknown"


@runtime_checkable
class MarketDataProvider(Protocol):
    """Interface wajib untuk semua data provider."""

    name: str

    def get_instruments(self, market: str) -> list[InstrumentInfo]:
        """Ambil daftar instrument di market tertentu (IDX / US)."""
        ...

    def get_ohlcv(self, instrument_id: str, start: date, end: date) -> list[Bar]:
        """Ambil OHLCV harian. start dan end inclusive."""
        ...

    def get_fundamentals(self, instrument_id: str, as_of: datetime) -> list[Fact]:
        """Ambil fundamental metrics yang tersedia per as_of."""
        ...

    def get_corporate_actions(
        self, instrument_id: str, start: date
    ) -> list[CorporateActionRecord]:
        """Ambil corporate actions sejak tanggal start."""
        ...

    def health(self) -> ProviderHealth:
        """Cek status provider."""
        ...

    def capability(self) -> ProviderCapability:
        """Deklarasikan kemampuan, lisensi, dan kuota provider ini."""
        ...

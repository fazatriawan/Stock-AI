"""
OpenBB Platform provider — experimental.

OpenBB adalah open-source financial data platform (75k+ stars GitHub).
Fokus utama: US equities, 500+ rasio finansial via openbb-finance.
IDX support belum diverifikasi resmi — gunakan sebagai pelengkap yfinance.

Instalasi (opsional, tidak wajib):
  pip install openbb

Konfigurasi (opsional):
  OPENBB_ENABLED=true
  OPENBB_PAT=<your_personal_access_token>  # dari openbb.co, opsional

Jika openbb tidak terinstall, provider ini gracefully mengembalikan kosong
dan mencatat peringatan — aplikasi tetap berjalan normal.

TIDAK melakukan: auto-trade, login broker, scraping private.
Data OpenBB bersumber dari public API (Yahoo Finance, CBOE, dll).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from app.core.logging import get_logger
from app.providers.base import (
    AccessStatus, Bar, CorporateActionRecord, Fact, InstrumentInfo,
    LicenseStatus, ProviderCapability, ProviderHealth, ProviderStatus,
)

logger = get_logger(__name__)

# Metrik OpenBB → nama field kita
OPENBB_METRIC_MAP: dict[str, str] = {
    "pe_ratio": "PE_RATIO",
    "price_to_book": "P/B",
    "return_on_equity": "ROE",
    "eps": "EPS_TRAILING",
    "revenue": "REVENUE",
    "net_income": "NET_INCOME",
    "market_cap": "MARKET_CAP",
    "dividend_yield": "DIVIDEND_YIELD",
    "debt_to_equity": "DEBT_TO_EQUITY",
    "gross_margin": "GROSS_MARGIN",
    "operating_margin": "OPERATING_MARGIN",
    "beta": "BETA",
    # Extended (US-focused)
    "current_ratio": "CURRENT_RATIO",
    "quick_ratio": "QUICK_RATIO",
    "free_cash_flow": "FREE_CASH_FLOW",
    "enterprise_value": "ENTERPRISE_VALUE",
    "ebitda": "EBITDA",
    "price_to_sales": "PRICE_TO_SALES",
    "forward_pe": "PE_FORWARD",
}


def _try_import_openbb():
    """
    Import openbb secara lazy — tidak crash jika tidak terinstall.
    Returns (obb, True) jika berhasil, (None, False) jika tidak.
    """
    try:
        from openbb import obb  # type: ignore[import-not-found]
        return obb, True
    except ImportError:
        return None, False


class OpenBBProvider:
    """
    Provider eksperimental berbasis OpenBB Platform.
    Bagus untuk US equities dengan 500+ rasio finansial.
    IDX support terbatas — yfinance tetap menjadi provider utama untuk IDX.
    """

    name = "openbb"

    def __init__(self, pat: Optional[str] = None) -> None:
        self._pat = pat
        self._obb, self._available = _try_import_openbb()
        if self._available:
            if pat:
                try:
                    self._obb.account.login(pat=pat)  # type: ignore[union-attr]
                    logger.info("OpenBB login sukses")
                except Exception as exc:
                    logger.warning("OpenBB login gagal, lanjut tanpa auth", error=str(exc))
            logger.info("OpenBBProvider aktif")
        else:
            logger.warning("openbb tidak terinstall — OpenBBProvider dalam mode disabled")

    def health(self) -> ProviderHealth:
        if not self._available:
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.DOWN,
                notes="openbb tidak terinstall. Install dengan: pip install openbb",
            )
        try:
            # Cek dengan query ringan
            self._obb.equity.price.quote(symbol="AAPL", provider="yfinance")  # type: ignore[union-attr]
            return ProviderHealth(provider=self.name, status=ProviderStatus.OK)
        except Exception as exc:
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.DEGRADED,
                last_error=str(exc),
            )

    def capability(self) -> ProviderCapability:
        access = AccessStatus.ACTIVE if self._available else AccessStatus.NOT_CONFIGURED
        return ProviderCapability(
            license_status=LicenseStatus.FREE_PERSONAL,
            access_status=access,
            cost="free",
            granularity="daily",
            freshness_policy="on_demand",
            supports_point_in_time=False,
            datasets=["ohlcv", "fundamental"],
            notes="OpenBB Platform — open source, US-focused; IDX support belum terverifikasi",
        )

    def get_instruments(self, market: str) -> list[InstrumentInfo]:
        return []  # OpenBB tidak punya registry instrument lengkap

    def get_ohlcv(self, instrument_id: str, start: date, end: date) -> list[Bar]:
        if not self._available:
            return []

        symbol = self._to_openbb_symbol(instrument_id)
        if not symbol:
            return []

        try:
            df = self._obb.equity.price.historical(  # type: ignore[union-attr]
                symbol=symbol,
                start_date=str(start),
                end_date=str(end),
                provider="yfinance",
            ).to_df()

            bars: list[Bar] = []
            for idx_date, row in df.iterrows():
                try:
                    bars.append(Bar(
                        instrument_id=instrument_id,
                        session_date=idx_date.date() if hasattr(idx_date, "date") else idx_date,
                        open=Decimal(str(row.get("open", 0))) if row.get("open") else None,
                        high=Decimal(str(row.get("high", 0))) if row.get("high") else None,
                        low=Decimal(str(row.get("low", 0))) if row.get("low") else None,
                        close=Decimal(str(row["close"])),
                        adj_close=Decimal(str(row.get("adj_close", row["close"]))),
                        volume=int(row.get("volume", 0)),
                        provider=self.name,
                        is_adjusted=False,
                    ))
                except Exception:
                    logger.debug("openbb.bar_row_parse_failed", symbol=symbol, date=str(idx_date), exc_info=True)
                    continue
            return bars
        except Exception as exc:
            logger.warning("openbb.ohlcv_error", symbol=symbol, error=str(exc))
            return []

    def get_fundamentals(self, instrument_id: str, as_of: datetime | None = None) -> list[Fact]:
        if not self._available:
            return []

        symbol = self._to_openbb_symbol(instrument_id)
        if not symbol:
            return []

        facts: list[Fact] = []
        today = date.today()

        try:
            # Overview metrics
            overview = self._obb.equity.fundamental.overview(  # type: ignore[union-attr]
                symbol=symbol, provider="yfinance",
            ).to_df()

            if not overview.empty:
                row = overview.iloc[0]
                for col_name, metric_name in OPENBB_METRIC_MAP.items():
                    val = row.get(col_name)
                    if val is not None:
                        try:
                            facts.append(Fact(
                                instrument_id=instrument_id,
                                metric=metric_name,
                                value=Decimal(str(float(val))),
                                value_text=None,
                                period_end=today,
                                period_start=None,
                                filing_date=None,
                                available_at=today,
                                unit=None,
                                currency="USD",
                                accounting_basis="TTM",
                                source_url=None,
                                provider=self.name,
                            ))
                        except Exception:
                            logger.debug("openbb.metric_parse_failed", symbol=symbol, metric=metric_name, exc_info=True)
                            continue
        except Exception as exc:
            logger.warning("openbb.fundamentals_error", symbol=symbol, error=str(exc))

        return facts

    def get_corporate_actions(self, instrument_id: str, start: date) -> list[CorporateActionRecord]:
        return []  # Belum diimplementasi

    def _to_openbb_symbol(self, instrument_id: str) -> Optional[str]:
        """
        Konversi canonical_symbol ke format OpenBB.
        IDX:BBCA → BBCA.JK (via yfinance)
        US:AAPL → AAPL
        """
        if ":" not in instrument_id:
            return instrument_id
        exchange, ticker = instrument_id.split(":", 1)
        if exchange == "IDX":
            return f"{ticker}.JK"
        return ticker

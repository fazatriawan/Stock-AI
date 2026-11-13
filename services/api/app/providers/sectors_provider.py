"""
Sectors Financial API adapter — data fundamental IDX berkualitas tinggi.
https://sectors.app/api — requires SECTORS_API_KEY

Hanya untuk IDX (Indonesia Stock Exchange).
Jika API key tidak ada atau request gagal, kembalikan list kosong (tidak silent fallback ke angka palsu).

Endpoint yang dipakai:
  GET /v1/company/report/{ticker}/     — fundamental + valuasi satu emiten
  GET /v1/companies/?sub_sector=...    — daftar emiten per sub-sektor (untuk peer list)
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

from app.core.logging import get_logger
from app.providers.base import (
    AccessStatus, Bar, CorporateActionRecord, Fact, InstrumentInfo,
    LicenseStatus, ProviderCapability, ProviderHealth, ProviderStatus,
)

logger = get_logger(__name__)

BASE_URL = "https://api.sectors.app/v1"

# Mapping field response Sectors → canonical metric name + unit
# Sumber: https://sectors.app/api/documentation
FINANCIALS_MAP: dict[str, tuple[str, str]] = {
    "revenue":            ("REVENUE",           "currency"),
    "net_income":         ("NET_INCOME",         "currency"),
    "gross_profit":       ("GROSS_PROFIT",       "currency"),
    "ebitda":             ("EBITDA",             "currency"),
    "total_equity":       ("TOTAL_EQUITY",       "currency"),
    "total_assets":       ("TOTAL_ASSETS",       "currency"),
    "total_debt":         ("TOTAL_DEBT",         "currency"),
    "cash_and_equiv":     ("CASH_AND_EQUIV",     "currency"),
    "capex":              ("CAPEX",              "currency"),
    "operating_income":   ("OPERATING_INCOME",  "currency"),
}

VALUATION_MAP: dict[str, tuple[str, str]] = {
    "pe":                 ("PE_RATIO",           "ratio"),
    "pb":                 ("P/B",                "ratio"),
    "ps":                 ("P/S",                "ratio"),
    "ev_ebitda":          ("EV_EBITDA",          "ratio"),
    "market_cap":         ("MARKET_CAP",         "currency"),
    "enterprise_value":   ("ENTERPRISE_VALUE",   "currency"),
    "dividend_yield":     ("DIVIDEND_YIELD",     "ratio"),
    "eps":                ("EPS_TRAILING",        "currency"),
}

RATIOS_MAP: dict[str, tuple[str, str]] = {
    "roe":                ("ROE",                "ratio"),
    "roa":                ("ROA",                "ratio"),
    "gross_margin":       ("GROSS_MARGIN",       "ratio"),
    "operating_margin":   ("OPERATING_MARGIN",   "ratio"),
    "net_margin":         ("NET_MARGIN",         "ratio"),
    "current_ratio":      ("CURRENT_RATIO",      "ratio"),
    "debt_to_equity":     ("DEBT_TO_EQUITY",     "ratio"),
    "asset_turnover":     ("ASSET_TURNOVER",     "ratio"),
    # Bank-specific
    "nim":                ("NIM",                "ratio"),
    "npl_gross":          ("NPL_GROSS",          "ratio"),
    "car":                ("CAR",                "ratio"),
    "ldr":                ("LDR",                "ratio"),
    "casa_ratio":         ("CASA_RATIO",         "ratio"),
}


def _safe_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _ticker_from_id(instrument_id: str) -> str:
    """IDX:BBCA → BBCA"""
    return instrument_id.split(":", 1)[-1] if ":" in instrument_id else instrument_id


class SectorsProvider:
    """
    Adapter ke Sectors Financial API untuk data fundamental IDX.
    Hanya valid untuk instrumen IDX (exchange = IDX / BEI).
    """

    name = "sectors"
    _last_call_time: float = 0.0
    _min_interval: float = 1.0  # Sectors API: ~60 req/menit

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.monotonic()

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """HTTP GET dengan rate limit dan error handling."""
        self._rate_limit()
        url = f"{BASE_URL}{path}"
        try:
            resp = httpx.get(url, headers=self._headers, params=params, timeout=15.0)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Sectors API HTTP error", path=path, status=e.response.status_code)
            return None
        except httpx.RequestError as e:
            logger.error("Sectors API request error", path=path, error=str(e))
            return None

    # ------------------------------------------------------------------
    # MarketDataProvider interface
    # ------------------------------------------------------------------

    def get_instruments(self, market: str) -> list[InstrumentInfo]:
        """Ambil daftar emiten per market. Sectors API hanya mendukung IDX."""
        if market != "IDX":
            return []
        data = self._get("/companies/", {"exchange": "IDX", "fields": "ticker,company_name,sector,sub_sector"})
        if not data or not isinstance(data, list):
            return []
        result: list[InstrumentInfo] = []
        for item in data:
            ticker = item.get("ticker")
            if not ticker:
                continue
            result.append(InstrumentInfo(
                canonical_symbol=f"IDX:{ticker}",
                local_symbol=ticker,
                exchange="IDX",
                country="ID",
                currency="IDR",
                timezone="Asia/Jakarta",
                sector=item.get("sector"),
                industry=item.get("sub_sector"),
                company_name=item.get("company_name"),
                provider="sectors",
            ))
        return result

    def get_ohlcv(self, instrument_id: str, start: date, end: date) -> list[Bar]:
        """Sectors API tidak menyediakan OHLCV — gunakan yfinance untuk harga."""
        logger.debug("SectorsProvider tidak menyediakan OHLCV, skip", symbol=instrument_id)
        return []

    def get_fundamentals(self, instrument_id: str, as_of: datetime) -> list[Fact]:
        """
        Ambil fundamental dari Sectors API.
        Response: { "symbol": ..., "financials": {...}, "valuation": {...}, "ratios": {...} }
        """
        ticker = _ticker_from_id(instrument_id)
        data = self._get(f"/company/report/{ticker}/")
        if not data:
            return []

        facts: list[Fact] = []
        currency = data.get("currency", "IDR")
        # Period: Sectors API umumnya return data fiskal terakhir
        fiscal_year = data.get("fiscal_year") or (as_of.year - 1)
        period_end = date(int(fiscal_year), 12, 31)

        def _emit(src: dict, field_map: dict, section_name: str) -> None:
            for api_key, (metric, unit) in field_map.items():
                raw = src.get(api_key)
                val = _safe_decimal(raw)
                if val is None:
                    continue
                facts.append(Fact(
                    instrument_id=instrument_id,
                    metric=metric,
                    value=val,
                    value_text=None,
                    period_end=period_end,
                    period_start=date(int(fiscal_year), 1, 1),
                    filing_date=None,
                    available_at=as_of.date(),
                    unit=unit,
                    currency=currency if unit == "currency" else None,
                    accounting_basis="GAAP",
                    source_url=f"{BASE_URL}/company/report/{ticker}/",
                    provider="sectors",
                    ingested_at=datetime.now(tz=timezone.utc),
                    license_class="LICENSED",
                    validation_status="VERIFIED",
                ))

        _emit(data.get("financials", {}), FINANCIALS_MAP, "financials")
        _emit(data.get("valuation", {}), VALUATION_MAP, "valuation")
        _emit(data.get("ratios", {}), RATIOS_MAP, "ratios")

        logger.info("Sectors fundamentals fetched", ticker=ticker, facts=len(facts))
        return facts

    def get_corporate_actions(
        self, instrument_id: str, start: date
    ) -> list[CorporateActionRecord]:
        """Corporate actions dari Sectors API (endpoint terpisah, diimplementasikan ke depan)."""
        return []

    def health(self) -> ProviderHealth:
        try:
            data = self._get("/health/")
            if data is not None:
                return ProviderHealth(
                    provider="sectors",
                    status=ProviderStatus.OK,
                    last_success=datetime.now(tz=timezone.utc),
                    notes="sectors.app IDX fundamental data",
                )
        except Exception as e:
            return ProviderHealth(provider="sectors", status=ProviderStatus.DOWN, last_error=str(e))
        return ProviderHealth(provider="sectors", status=ProviderStatus.UNKNOWN)

    def capability(self) -> ProviderCapability:
        access = AccessStatus.ACTIVE if self._api_key else AccessStatus.NOT_CONFIGURED
        return ProviderCapability(
            license_status=LicenseStatus.PAID,
            access_status=access,
            cost="paid",
            granularity="snapshot",
            freshness_policy="on_demand",
            supports_point_in_time=False,
            datasets=["fundamental", "peers", "instruments"],
            quota_per_day=None,  # tergantung paket Insider (5000 kredit/bulan)
            notes="Sectors Financial API — Insider US$59/bulan; paket Free tidak termasuk akses API",
        )

    # ------------------------------------------------------------------
    # Sectors-specific — peer listing (di luar MarketDataProvider)
    # ------------------------------------------------------------------

    def get_peers(self, ticker: str, limit: int = 10) -> list[str]:
        """
        Ambil daftar ticker peer (sub-sektor yang sama).
        Mengembalikan list ticker IDX (tanpa prefix IDX:).
        """
        data = self._get(f"/company/report/{ticker}/")
        if not data:
            return []
        sub_sector = data.get("sub_sector")
        if not sub_sector:
            return []
        peers_data = self._get("/companies/", {
            "sub_sector": sub_sector,
            "fields": "ticker",
            "limit": limit + 1,  # +1 untuk exclude diri sendiri
        })
        if not peers_data or not isinstance(peers_data, list):
            return []
        return [
            item["ticker"] for item in peers_data
            if isinstance(item, dict) and item.get("ticker") and item["ticker"] != ticker
        ][:limit]

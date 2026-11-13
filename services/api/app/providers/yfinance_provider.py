"""
yfinance provider untuk personal research/prototyping.
Sesuai disclaimer yfinance: personal use only, bukan production financial data.
Rate limit: jangan lebih dari ~100 req/menit; gunakan caching.
"""
from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from app.core.logging import get_logger
from app.providers.base import (
    AccessStatus, Bar, CorporateActionRecord, Fact, InstrumentInfo,
    LicenseStatus, ProviderCapability, ProviderHealth, ProviderStatus,
)

logger = get_logger(__name__)

# Mapping exchange IDX ke suffix yfinance
IDX_SUFFIX = ".JK"
# Exchange mapping canonical → yfinance symbol
EXCHANGE_SUFFIX: dict[str, str] = {
    "IDX": ".JK",
    "NASDAQ": "",
    "NYSE": "",
}


def _canonical_to_yf(instrument_id: str) -> str:
    """Konversi IDX:BBCA → BBCA.JK, US:AAPL → AAPL."""
    if ":" not in instrument_id:
        return instrument_id
    exchange, symbol = instrument_id.split(":", 1)
    suffix = EXCHANGE_SUFFIX.get(exchange, "")
    return f"{symbol}{suffix}"


class YFinanceProvider:
    """Provider berbasis yfinance untuk personal research."""

    name = "yfinance"
    _last_call_time: float = 0
    _min_interval: float = 0.5  # detik antar request

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    def get_instruments(self, market: str) -> list[InstrumentInfo]:
        # yfinance tidak menyediakan daftar instrument per market secara langsung
        # Kembalikan empty — gunakan canonical registry atau mock untuk bootstrapping
        logger.warning("yfinance tidak mendukung get_instruments; gunakan canonical registry")
        return []

    def get_ohlcv(self, instrument_id: str, start: date, end: date) -> list[Bar]:
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance tidak terinstall")
            return []

        self._rate_limit()
        yf_symbol = _canonical_to_yf(instrument_id)

        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=True,
                back_adjust=False,
            )
        except Exception as e:
            logger.error("yfinance OHLCV error", symbol=yf_symbol, error=str(e))
            return []

        if df.empty:
            return []

        bars: list[Bar] = []
        for idx_date, row in df.iterrows():
            session_date = idx_date.date() if hasattr(idx_date, "date") else idx_date
            try:
                close_val = Decimal(str(round(float(row["Close"]), 6)))
                if close_val <= 0:
                    continue
                bar = Bar(
                    instrument_id=instrument_id,
                    session_date=session_date,
                    open=Decimal(str(round(float(row["Open"]), 6))) if row.get("Open") else None,
                    high=Decimal(str(round(float(row["High"]), 6))) if row.get("High") else None,
                    low=Decimal(str(round(float(row["Low"]), 6))) if row.get("Low") else None,
                    close=close_val,
                    adj_close=close_val,  # auto_adjust=True → Close sudah adjusted
                    volume=int(row["Volume"]) if row.get("Volume") is not None else None,
                    provider="yfinance",
                    is_adjusted=True,
                )
                errors = bar.validate()
                if errors:
                    logger.warning("Bar validation error", symbol=yf_symbol, date=str(session_date), errors=errors)
                    continue
                bars.append(bar)
            except Exception as e:
                logger.warning("Bar parse error", symbol=yf_symbol, date=str(session_date), error=str(e))
                continue

        return bars

    def get_fundamentals(self, instrument_id: str, as_of: datetime) -> list[Fact]:
        try:
            import yfinance as yf
        except ImportError:
            return []

        self._rate_limit()
        yf_symbol = _canonical_to_yf(instrument_id)

        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info
        except Exception as e:
            logger.error("yfinance info error", symbol=yf_symbol, error=str(e))
            return []

        facts: list[Fact] = []
        metric_map: dict[str, tuple[str, Optional[str]]] = {
            "trailingPE": ("PE_RATIO", "ratio"),
            "priceToBook": ("P/B", "ratio"),
            "returnOnEquity": ("ROE", "ratio"),
            "debtToEquity": ("DEBT_TO_EQUITY", "ratio"),
            "revenueGrowth": ("REVENUE_GROWTH_YOY", "ratio"),
            "grossMargins": ("GROSS_MARGIN", "ratio"),
            "operatingMargins": ("OPERATING_MARGIN", "ratio"),
            "trailingEps": ("EPS_TRAILING", "currency"),
            "forwardEps": ("EPS_FORWARD", "currency"),
            "dividendYield": ("DIVIDEND_YIELD", "ratio"),
            "beta": ("BETA", "ratio"),
            "marketCap": ("MARKET_CAP", "currency"),
            "enterpriseValue": ("ENTERPRISE_VALUE", "currency"),
            "trailingAnnualDividendRate": ("DIVIDEND_ANNUAL", "currency"),
        }

        currency = info.get("currency", "USD")
        period_end = date(as_of.year - 1, 12, 31)

        for yf_key, (metric_name, unit) in metric_map.items():
            raw = info.get(yf_key)
            if raw is None:
                continue
            try:
                val = Decimal(str(round(float(raw), 8)))
                facts.append(Fact(
                    instrument_id=instrument_id,
                    metric=metric_name,
                    value=val,
                    value_text=None,
                    period_end=period_end,
                    period_start=None,
                    filing_date=None,
                    available_at=as_of.date(),
                    unit=unit,
                    currency=currency if unit == "currency" else None,
                    accounting_basis=None,
                    source_url=None,
                    provider="yfinance",
                    ingested_at=datetime.utcnow(),
                    license_class="PERSONAL_RESEARCH",
                    validation_status="ESTIMATED",
                ))
            except Exception:
                logger.debug("yfinance.metric_parse_failed", metric=metric_name, yf_key=yf_key, exc_info=True)
                continue

        return facts

    def get_corporate_actions(
        self, instrument_id: str, start: date
    ) -> list[CorporateActionRecord]:
        try:
            import yfinance as yf
        except ImportError:
            return []

        self._rate_limit()
        yf_symbol = _canonical_to_yf(instrument_id)
        records: list[CorporateActionRecord] = []

        try:
            ticker = yf.Ticker(yf_symbol)

            # Splits
            splits = ticker.splits
            if splits is not None and not splits.empty:
                for split_date, ratio in splits.items():
                    sd = split_date.date() if hasattr(split_date, "date") else split_date
                    if sd >= start:
                        records.append(CorporateActionRecord(
                            instrument_id=instrument_id,
                            action_type="SPLIT",
                            effective_at=sd,
                            announced_at=None,
                            ratio=Decimal(str(ratio)),
                            cash_amount=None,
                            currency=None,
                            status="CONFIRMED",
                            source_url=None,
                            provider="yfinance",
                        ))

            # Dividends
            divs = ticker.dividends
            if divs is not None and not divs.empty:
                for div_date, amount in divs.items():
                    dd = div_date.date() if hasattr(div_date, "date") else div_date
                    if dd >= start:
                        records.append(CorporateActionRecord(
                            instrument_id=instrument_id,
                            action_type="DIVIDEND",
                            effective_at=dd,
                            announced_at=None,
                            ratio=None,
                            cash_amount=Decimal(str(round(float(amount), 6))),
                            currency=None,
                            status="CONFIRMED",
                            source_url=None,
                            provider="yfinance",
                        ))
        except Exception as e:
            logger.error("yfinance corporate actions error", symbol=yf_symbol, error=str(e))

        return records

    def health(self) -> ProviderHealth:
        try:
            import yfinance as yf
            ticker = yf.Ticker("AAPL")
            info = ticker.fast_info
            if info:
                return ProviderHealth(
                    provider="yfinance",
                    status=ProviderStatus.OK,
                    last_success=datetime.utcnow(),
                    notes="personal use only",
                )
        except Exception as e:
            return ProviderHealth(
                provider="yfinance",
                status=ProviderStatus.DOWN,
                last_error=str(e),
            )
        return ProviderHealth(provider="yfinance", status=ProviderStatus.UNKNOWN)

    def capability(self) -> ProviderCapability:
        try:
            import yfinance  # noqa: F401
            access = AccessStatus.ACTIVE
        except ImportError:
            access = AccessStatus.NOT_CONFIGURED
        return ProviderCapability(
            license_status=LicenseStatus.FREE_PERSONAL,
            access_status=access,
            cost="free",
            granularity="daily",
            freshness_policy="EOD",
            supports_point_in_time=False,
            datasets=["ohlcv", "fundamental", "corporate_actions", "instruments"],
            notes="Hanya untuk riset pribadi — lihat ketentuan penggunaan yfinance",
        )

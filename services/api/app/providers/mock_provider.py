"""
Mock provider untuk testing dan development offline.
Menggunakan data sintetis deterministik — BUKAN data pasar riil.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from app.providers.base import (
    Bar, CorporateActionRecord, Fact, InstrumentInfo,
    MarketDataProvider, ProviderHealth, ProviderStatus,
)

# Daftar instrument mock — IDX dan US
MOCK_INSTRUMENTS: dict[str, InstrumentInfo] = {
    # IDX
    "IDX:BBCA": InstrumentInfo("IDX:BBCA", "BBCA", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Financials", industry="Banks", company_name="Bank Central Asia Tbk"),
    "IDX:BBRI": InstrumentInfo("IDX:BBRI", "BBRI", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Financials", industry="Banks", company_name="Bank Rakyat Indonesia Tbk"),
    "IDX:BMRI": InstrumentInfo("IDX:BMRI", "BMRI", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Financials", industry="Banks", company_name="Bank Mandiri Tbk"),
    "IDX:TLKM": InstrumentInfo("IDX:TLKM", "TLKM", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Communication Services", industry="Telecom", company_name="Telkom Indonesia Tbk"),
    "IDX:ASII": InstrumentInfo("IDX:ASII", "ASII", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Industrials", industry="Conglomerate", company_name="Astra International Tbk"),
    "IDX:UNVR": InstrumentInfo("IDX:UNVR", "UNVR", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Consumer Staples", industry="FMCG", company_name="Unilever Indonesia Tbk"),
    "IDX:GOTO": InstrumentInfo("IDX:GOTO", "GOTO", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Technology", industry="Internet", company_name="GoTo Gojek Tokopedia Tbk"),
    "IDX:ADRO": InstrumentInfo("IDX:ADRO", "ADRO", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Energy", industry="Coal", company_name="Adaro Energy Indonesia Tbk"),
    "IDX:PTBA": InstrumentInfo("IDX:PTBA", "PTBA", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Energy", industry="Coal", company_name="Bukit Asam Tbk"),
    "IDX:ICBP": InstrumentInfo("IDX:ICBP", "ICBP", "IDX", "ID", "IDR", "Asia/Jakarta", sector="Consumer Staples", industry="Food", company_name="Indofood CBP Tbk"),
    # US
    "US:AAPL": InstrumentInfo("US:AAPL", "AAPL", "NASDAQ", "US", "USD", "America/New_York", sector="Technology", industry="Consumer Electronics", company_name="Apple Inc"),
    "US:MSFT": InstrumentInfo("US:MSFT", "MSFT", "NASDAQ", "US", "USD", "America/New_York", sector="Technology", industry="Software", company_name="Microsoft Corporation"),
    "US:GOOGL": InstrumentInfo("US:GOOGL", "GOOGL", "NASDAQ", "US", "USD", "America/New_York", sector="Technology", industry="Internet", company_name="Alphabet Inc"),
    "US:AMZN": InstrumentInfo("US:AMZN", "AMZN", "NASDAQ", "US", "USD", "America/New_York", sector="Consumer Discretionary", industry="E-Commerce", company_name="Amazon.com Inc"),
    "US:META": InstrumentInfo("US:META", "META", "NASDAQ", "US", "USD", "America/New_York", sector="Technology", industry="Social Media", company_name="Meta Platforms Inc"),
    "US:NVDA": InstrumentInfo("US:NVDA", "NVDA", "NASDAQ", "US", "USD", "America/New_York", sector="Technology", industry="Semiconductors", company_name="NVIDIA Corporation"),
    "US:JPM": InstrumentInfo("US:JPM", "JPM", "NYSE", "US", "USD", "America/New_York", sector="Financials", industry="Banks", company_name="JPMorgan Chase & Co"),
    "US:JNJ": InstrumentInfo("US:JNJ", "JNJ", "NYSE", "US", "USD", "America/New_York", sector="Healthcare", industry="Pharmaceuticals", company_name="Johnson & Johnson"),
    "US:XOM": InstrumentInfo("US:XOM", "XOM", "NYSE", "US", "USD", "America/New_York", sector="Energy", industry="Oil & Gas", company_name="Exxon Mobil Corporation"),
    "US:BRK.B": InstrumentInfo("US:BRK.B", "BRK.B", "NYSE", "US", "USD", "America/New_York", sector="Financials", industry="Insurance", company_name="Berkshire Hathaway Inc"),
}

# Harga awal sintetis per instrument
BASE_PRICES: dict[str, float] = {
    "IDX:BBCA": 9500, "IDX:BBRI": 4800, "IDX:BMRI": 5600, "IDX:TLKM": 3600,
    "IDX:ASII": 5200, "IDX:UNVR": 2700, "IDX:GOTO": 80, "IDX:ADRO": 2200,
    "IDX:PTBA": 2800, "IDX:ICBP": 8500,
    "US:AAPL": 175, "US:MSFT": 380, "US:GOOGL": 140, "US:AMZN": 170,
    "US:META": 490, "US:NVDA": 460, "US:JPM": 190, "US:JNJ": 155,
    "US:XOM": 110, "US:BRK.B": 350,
}


def _generate_bars(instrument_id: str, start: date, end: date) -> list[Bar]:
    """Generate OHLCV sintetis deterministik menggunakan seed dari instrument_id."""
    rng = random.Random(hash(instrument_id) % (2**32))
    base = BASE_PRICES.get(instrument_id, 1000.0)

    bars: list[Bar] = []
    current_price = base
    current = start
    while current <= end:
        # Skip weekend
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue

        # Simulasi return harian ±2%
        daily_return = rng.gauss(0.0003, 0.015)
        current_price = max(current_price * (1 + daily_return), 0.01)

        open_p = Decimal(str(round(current_price * rng.uniform(0.99, 1.005), 2)))
        close_p = Decimal(str(round(current_price, 2)))
        high_p = Decimal(str(round(max(float(open_p), float(close_p)) * rng.uniform(1.001, 1.015), 2)))
        low_p = Decimal(str(round(min(float(open_p), float(close_p)) * rng.uniform(0.985, 0.999), 2)))
        vol = int(rng.uniform(500_000, 20_000_000))

        bars.append(Bar(
            instrument_id=instrument_id,
            session_date=current,
            open=open_p,
            high=high_p,
            low=low_p,
            close=close_p,
            adj_close=close_p,
            volume=vol,
            provider="mock",
            is_adjusted=True,
        ))
        current += timedelta(days=1)

    return bars


class MockProvider:
    """Mock provider — data sintetis untuk testing. BUKAN data pasar riil."""

    name = "mock"

    def get_instruments(self, market: str) -> list[InstrumentInfo]:
        market_prefix = "IDX:" if market == "IDX" else "US:"
        return [v for k, v in MOCK_INSTRUMENTS.items() if k.startswith(market_prefix)]

    def get_ohlcv(self, instrument_id: str, start: date, end: date) -> list[Bar]:
        if instrument_id not in MOCK_INSTRUMENTS:
            return []
        return _generate_bars(instrument_id, start, end)

    def get_fundamentals(self, instrument_id: str, as_of: datetime) -> list[Fact]:
        if instrument_id not in MOCK_INSTRUMENTS:
            return []
        info = MOCK_INSTRUMENTS[instrument_id]
        rng = random.Random(hash(instrument_id) % (2**32))
        period_end = date(as_of.year if as_of.month > 3 else as_of.year - 1, 12, 31)

        metrics: list[tuple[str, Optional[Decimal], str]] = []
        if info.sector == "Financials" and info.industry == "Banks":
            metrics = [
                ("ROE", Decimal(str(round(rng.uniform(0.10, 0.22), 4))), "ratio"),
                ("NIM", Decimal(str(round(rng.uniform(0.04, 0.08), 4))), "ratio"),
                ("NPL_GROSS", Decimal(str(round(rng.uniform(0.01, 0.04), 4))), "ratio"),
                ("CAR", Decimal(str(round(rng.uniform(0.18, 0.26), 4))), "ratio"),
                ("P/B", Decimal(str(round(rng.uniform(1.2, 3.5), 2))), "ratio"),
            ]
        else:
            metrics = [
                ("REVENUE", Decimal(str(round(rng.uniform(1e12, 1e14), 0))), "IDR"),
                ("NET_INCOME", Decimal(str(round(rng.uniform(1e11, 1e13), 0))), "IDR"),
                ("EPS", Decimal(str(round(rng.uniform(50, 500), 2))), "IDR"),
                ("PE_RATIO", Decimal(str(round(rng.uniform(8, 25), 2))), "ratio"),
                ("ROE", Decimal(str(round(rng.uniform(0.08, 0.25), 4))), "ratio"),
            ]

        facts = []
        for metric_name, val, unit in metrics:
            facts.append(Fact(
                instrument_id=instrument_id,
                metric=metric_name,
                value=val,
                value_text=None,
                period_end=period_end,
                period_start=date(period_end.year, 1, 1),
                filing_date=date(period_end.year + 1, 3, 15),
                available_at=date(period_end.year + 1, 3, 15),
                unit=unit,
                currency=info.currency,
                accounting_basis="GAAP",
                source_url=None,
                provider="mock",
                license_class="SYNTHETIC_TEST",
                validation_status="SYNTHETIC",
            ))
        return facts

    def get_corporate_actions(
        self, instrument_id: str, start: date
    ) -> list[CorporateActionRecord]:
        return []

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="mock",
            status=ProviderStatus.OK,
            last_success=datetime.utcnow(),
            notes="Mock provider — synthetic data only",
        )

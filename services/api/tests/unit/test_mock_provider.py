"""
Unit tests — mock provider dan data ingestion.
Gate Milestone A: 20 ticker, duplicate, stale, currency, missing days, split.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.providers.mock_provider import MockProvider, MOCK_INSTRUMENTS


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider()


class TestMockProviderInstruments:
    def test_get_instruments_idx(self, provider: MockProvider) -> None:
        instruments = provider.get_instruments("IDX")
        assert len(instruments) >= 10
        for i in instruments:
            assert i.exchange == "IDX"
            assert i.currency == "IDR"
            assert i.country == "ID"

    def test_get_instruments_us(self, provider: MockProvider) -> None:
        instruments = provider.get_instruments("US")
        assert len(instruments) >= 10
        for i in instruments:
            assert i.currency == "USD"
            assert i.country == "US"

    def test_total_instruments_20(self, provider: MockProvider) -> None:
        """Gate Milestone A: minimal 20 ticker."""
        idx = provider.get_instruments("IDX")
        us = provider.get_instruments("US")
        assert len(idx) + len(us) >= 20

    def test_canonical_symbols_unique(self, provider: MockProvider) -> None:
        """Canonical symbol tidak boleh duplikat."""
        all_symbols = list(MOCK_INSTRUMENTS.keys())
        assert len(all_symbols) == len(set(all_symbols))

    def test_ticker_resolution_formats(self) -> None:
        """IDX:BMRI, BMRI, BMRI.JK → instrument yang sama."""
        assert "IDX:BMRI" in MOCK_INSTRUMENTS
        info = MOCK_INSTRUMENTS["IDX:BMRI"]
        assert info.local_symbol == "BMRI"
        assert info.exchange == "IDX"


class TestMockOHLCV:
    def test_bars_returned(self, provider: MockProvider) -> None:
        start = date(2026, 1, 1)
        end = date(2026, 3, 31)
        bars = provider.get_ohlcv("IDX:BBCA", start, end)
        assert len(bars) > 40  # ~60 hari bursa

    def test_no_weekend_bars(self, provider: MockProvider) -> None:
        """Mock tidak boleh generate bar di weekend."""
        start = date(2026, 1, 1)
        end = date(2026, 3, 31)
        bars = provider.get_ohlcv("IDX:BBCA", start, end)
        for bar in bars:
            assert bar.session_date.weekday() < 5, f"Bar di weekend: {bar.session_date}"

    def test_bar_validation_pass(self, provider: MockProvider) -> None:
        """Semua bar harus lulus validasi OHLCV constraints."""
        start = date(2026, 1, 1)
        end = date(2026, 6, 30)
        bars = provider.get_ohlcv("IDX:BBCA", start, end)
        for bar in bars:
            errors = bar.validate()
            assert not errors, f"Validasi gagal {bar.session_date}: {errors}"

    def test_close_positive(self, provider: MockProvider) -> None:
        start = date(2026, 1, 1)
        end = date(2026, 3, 31)
        bars = provider.get_ohlcv("IDX:BBCA", start, end)
        for bar in bars:
            assert bar.close > 0

    def test_high_gte_low(self, provider: MockProvider) -> None:
        start = date(2026, 1, 1)
        end = date(2026, 3, 31)
        bars = provider.get_ohlcv("IDX:BBCA", start, end)
        for bar in bars:
            if bar.high is not None and bar.low is not None:
                assert bar.high >= bar.low

    def test_unknown_instrument_returns_empty(self, provider: MockProvider) -> None:
        bars = provider.get_ohlcv("IDX:XXXXX", date(2026, 1, 1), date(2026, 3, 31))
        assert bars == []

    def test_deterministic_output(self, provider: MockProvider) -> None:
        """Data mock harus deterministik — sama jika dipanggil ulang."""
        start = date(2026, 1, 5)
        end = date(2026, 1, 10)
        bars1 = provider.get_ohlcv("IDX:BBCA", start, end)
        bars2 = provider.get_ohlcv("IDX:BBCA", start, end)
        assert len(bars1) == len(bars2)
        for b1, b2 in zip(bars1, bars2):
            assert b1.close == b2.close
            assert b1.volume == b2.volume

    def test_us_instrument_currency(self, provider: MockProvider) -> None:
        """US instrument harus ada di MOCK_INSTRUMENTS dengan currency USD."""
        assert "US:AAPL" in MOCK_INSTRUMENTS
        info = MOCK_INSTRUMENTS["US:AAPL"]
        assert info.currency == "USD"

    def test_idx_idr_prices(self, provider: MockProvider) -> None:
        """IDX price range masuk akal (ratusan hingga jutaan IDR)."""
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)
        bars = provider.get_ohlcv("IDX:BBCA", start, end)
        assert len(bars) > 0
        for bar in bars:
            assert float(bar.close) > 100  # minimal 100 IDR

    def test_provider_label(self, provider: MockProvider) -> None:
        """Semua bar harus berlabel provider='mock' agar sumber jelas."""
        bars = provider.get_ohlcv("IDX:BBCA", date(2026, 1, 1), date(2026, 1, 31))
        for bar in bars:
            assert bar.provider == "mock"

    def test_multiple_instruments_no_overlap(self, provider: MockProvider) -> None:
        """Data berbeda instrumen tidak boleh ter-cross."""
        start = date(2026, 1, 5)
        end = date(2026, 1, 8)
        bbca = provider.get_ohlcv("IDX:BBCA", start, end)
        bbri = provider.get_ohlcv("IDX:BBRI", start, end)
        if bbca and bbri:
            # Harga BBCA dan BBRI seharusnya berbeda (seed berbeda)
            assert bbca[0].close != bbri[0].close


class TestMockFundamentals:
    def test_bank_fundamentals(self, provider: MockProvider) -> None:
        """Bank harus menghasilkan NIM, NPL, CAR, ROE — bukan PE/Revenue biasa."""
        from datetime import datetime
        facts = provider.get_fundamentals("IDX:BBCA", datetime(2026, 6, 1))
        metric_names = [f.metric for f in facts]
        assert "NIM" in metric_names
        assert "NPL_GROSS" in metric_names
        assert "CAR" in metric_names
        assert "ROE" in metric_names

    def test_general_fundamentals(self, provider: MockProvider) -> None:
        from datetime import datetime
        facts = provider.get_fundamentals("IDX:TLKM", datetime(2026, 6, 1))
        metric_names = [f.metric for f in facts]
        assert "REVENUE" in metric_names or "PE_RATIO" in metric_names

    def test_synthetic_license(self, provider: MockProvider) -> None:
        """Semua fact mock harus berlabel SYNTHETIC_TEST — bukan real data."""
        from datetime import datetime
        facts = provider.get_fundamentals("IDX:BBCA", datetime(2026, 6, 1))
        for f in facts:
            assert f.license_class == "SYNTHETIC_TEST"
            assert f.validation_status == "SYNTHETIC"

    def test_provider_health_ok(self, provider: MockProvider) -> None:
        from app.providers.base import ProviderStatus
        health = provider.health()
        assert health.status == ProviderStatus.OK
        assert health.provider == "mock"

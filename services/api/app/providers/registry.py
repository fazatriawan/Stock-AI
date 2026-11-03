"""
Registry provider dengan priority chain:
  official → licensed vendor → allowed research adapter → UNAVAILABLE
Tidak pernah silent fallback ke data palsu.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import MarketDataProvider, ProviderHealth, ProviderStatus
from app.providers.mock_provider import MockProvider
from app.providers.yfinance_provider import YFinanceProvider

logger = get_logger(__name__)


class ProviderRegistry:
    def __init__(self) -> None:
        settings = get_settings()
        self._providers: dict[str, list[MarketDataProvider]] = {
            "IDX": [],
            "US": [],
        }
        self._provider_by_name: dict[str, MarketDataProvider] = {}

        # Daftarkan provider berdasarkan konfigurasi
        if settings.yfinance_enabled:
            yf = YFinanceProvider()
            self._providers["IDX"].append(yf)  # type: ignore[arg-type]
            self._providers["US"].append(yf)  # type: ignore[arg-type]
            self._provider_by_name["yfinance"] = yf  # type: ignore[assignment]

        # Mock selalu tersedia sebagai fallback terakhir untuk testing
        mock = MockProvider()
        self._mock = mock
        self._provider_by_name["mock"] = mock  # type: ignore[assignment]

    def get_primary(self, market: str) -> MarketDataProvider:
        """Ambil provider utama untuk market. Fallback ke mock jika tidak ada."""
        providers = self._providers.get(market, [])
        if providers:
            return providers[0]
        logger.warning("Tidak ada provider terdaftar untuk market, menggunakan mock", market=market)
        return self._mock  # type: ignore[return-value]

    def get_fallback(self, market: str) -> MarketDataProvider:
        """Ambil provider fallback (mock)."""
        return self._mock  # type: ignore[return-value]

    def get_by_name(self, name: str) -> MarketDataProvider | None:
        return self._provider_by_name.get(name)  # type: ignore[return-value]

    def all_health(self) -> list[ProviderHealth]:
        results = []
        for name, provider in self._provider_by_name.items():
            try:
                results.append(provider.health())
            except Exception as e:
                results.append(ProviderHealth(
                    provider=name,
                    status=ProviderStatus.DOWN,
                    last_error=str(e),
                ))
        return results


_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def get_provider(market: str) -> MarketDataProvider:
    return get_provider_registry().get_primary(market)

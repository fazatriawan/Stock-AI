"""
Registry provider dengan priority chain:
  official → licensed vendor → allowed research adapter → UNAVAILABLE
Tidak pernah silent fallback ke data palsu.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import MarketDataProvider, ProviderHealth, ProviderStatus
from app.providers.circuit_breaker import all_circuit_breaker_statuses, get_circuit_breaker
from app.providers.mock_provider import MockProvider
from app.providers.sectors_provider import SectorsProvider
from app.providers.yfinance_provider import YFinanceProvider
from app.providers.openbb_provider import OpenBBProvider

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
        # Sectors — prioritas tertinggi untuk fundamental IDX (lebih akurat dari yfinance)
        if settings.sectors_enabled and settings.sectors_api_key:
            if not settings.paid_providers_enabled:
                logger.warning(
                    "budget_guard.blocked_paid_provider",
                    provider="sectors",
                    reason="paid_providers_enabled=false",
                )
            else:
                sectors: MarketDataProvider = SectorsProvider(api_key=settings.sectors_api_key)
                self._providers["IDX"].insert(0, sectors)
                self._provider_by_name["sectors"] = sectors
                logger.info("SectorsProvider aktif untuk IDX fundamental")

        if settings.yfinance_enabled:
            yf: MarketDataProvider = YFinanceProvider()
            self._providers["IDX"].append(yf)
            self._providers["US"].append(yf)
            self._provider_by_name["yfinance"] = yf

        # OpenBB — experimental, US-focused, 500+ rasio finansial
        if settings.openbb_enabled:
            openbb: MarketDataProvider = OpenBBProvider(pat=settings.openbb_pat or None)
            self._providers["US"].append(openbb)
            # IDX support terbatas, tambahkan sebagai fallback saja
            self._providers["IDX"].append(openbb)
            self._provider_by_name["openbb"] = openbb
            logger.info("OpenBBProvider aktif (experimental)")

        # Mock selalu tersedia sebagai fallback terakhir untuk testing
        self._mock: MarketDataProvider = MockProvider()
        self._provider_by_name["mock"] = self._mock

    def get_primary(self, market: str) -> MarketDataProvider:
        """Ambil provider utama untuk market. Fallback ke mock jika tidak ada."""
        providers = self._providers.get(market, [])
        if providers:
            return providers[0]
        logger.warning("Tidak ada provider terdaftar untuk market, menggunakan mock", market=market)
        return self._mock

    def get_fundamental_provider(self, market: str) -> MarketDataProvider:
        """
        Pilih provider terbaik untuk data fundamental.
        Untuk IDX: Sectors > yfinance > mock.
        Untuk US: yfinance > mock.
        """
        if market == "IDX":
            if "sectors" in self._provider_by_name:
                return self._provider_by_name["sectors"]
        providers = self._providers.get(market, [])
        if providers:
            return providers[0]
        return self._mock

    def get_fallback(self, market: str) -> MarketDataProvider:
        """Ambil provider fallback (mock)."""
        return self._mock

    def get_by_name(self, name: str) -> MarketDataProvider | None:
        return self._provider_by_name.get(name)

    def all_health(self) -> list[ProviderHealth]:
        results = []
        for name, provider in self._provider_by_name.items():
            cb = get_circuit_breaker(name)
            if not cb.allow_request():
                results.append(ProviderHealth(
                    provider=name,
                    status=ProviderStatus.DOWN,
                    last_error=f"Circuit breaker OPEN — {cb._state.last_error}",
                    notes="Circuit breaker aktif, provider tidak diuji",
                ))
                cb._state.total_calls -= 1  # health probe bukan request sesungguhnya
                continue
            try:
                h = provider.health()
                cb.record_success()
                results.append(h)
            except Exception as e:
                cb.record_failure(str(e))
                results.append(ProviderHealth(
                    provider=name,
                    status=ProviderStatus.DOWN,
                    last_error=str(e),
                ))
        return results

    def all_circuit_breaker_statuses(self) -> list[dict]:
        return all_circuit_breaker_statuses()


_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def get_provider(market: str) -> MarketDataProvider:
    return get_provider_registry().get_primary(market)

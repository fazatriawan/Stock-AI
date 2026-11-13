from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    secret_key: str = "change-me"

    # Database
    database_url: str = "postgresql+asyncpg://stock_user:change_me@localhost:5432/stock_intelligence"
    database_url_sync: str = "postgresql://stock_user:change_me@localhost:5432/stock_intelligence"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic / TokenPlus
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""  # kosong = pakai endpoint Anthropic langsung; isi untuk proxy (TokenPlus, dll)
    anthropic_model: str = "claude-sonnet-5-5"
    ai_daily_token_budget: int = 500_000
    ai_cache_ttl_seconds: int = 3600

    # Budget guard (FREE-03) — default Rp0 / tidak ada langganan otomatis
    data_monthly_budget_idr: int = 0
    ai_runtime_monthly_budget_idr: int = 0
    paid_providers_enabled: bool = False
    automatic_subscription: bool = False

    # Providers
    yfinance_enabled: bool = True
    fmp_api_key: str = ""
    fmp_enabled: bool = False
    fred_api_key: str = ""
    bps_api_key: str = ""
    sectors_api_key: str = ""
    sectors_enabled: bool = False  # aktifkan kalau punya API key sectors.app

    # OpenBB — experimental, US-focused, 500+ rasio
    openbb_enabled: bool = False
    openbb_pat: str = ""  # Personal Access Token openbb.co (opsional)

    # Intraday polling (5-menit saat jam bursa)
    intraday_polling_enabled: bool = True

    # IDX Full Bootstrap
    idx_bootstrap_days: int = 1825  # 5 tahun histori OHLCV

    # US Stocks Bootstrap (FREE-10)
    us_bootstrap_days: int = 1825  # 5 tahun histori OHLCV
    us_bootstrap_enabled: bool = True

    # Timezone
    default_timezone: str = "Asia/Jakarta"
    idx_timezone: str = "Asia/Jakarta"
    nyse_timezone: str = "America/New_York"

    # Portfolio
    base_currency: str = "IDR"
    default_market: str = "IDX"

    # Security
    session_expire_seconds: int = 86400
    allowed_origins: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

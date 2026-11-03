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

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    ai_daily_token_budget: int = 500_000
    ai_cache_ttl_seconds: int = 3600

    # Providers
    yfinance_enabled: bool = True
    fmp_api_key: str = ""
    fmp_enabled: bool = False
    fred_api_key: str = ""
    bps_api_key: str = ""

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

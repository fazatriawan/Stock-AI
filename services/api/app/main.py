"""
Stock Intelligence API — FastAPI entry point.
"""
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import StockIntelligenceError, stock_error_handler
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Stock Intelligence API starting", env=settings.app_env)
    yield
    logger.info("Stock Intelligence API shutting down")


app = FastAPI(
    title="Stock Intelligence API",
    description="Personal equity research & decision support — Indonesia & US markets",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(StockIntelligenceError, stock_error_handler)  # type: ignore[arg-type]

# Routes
from app.api.routes import markets, instruments, stocks, data_health, ingestion, portfolio, import_trades, portfolio_intelligence, rebalance, journal, daily, decisions, screener, performance, macro, notebook

app.include_router(markets.router, prefix="/api/v1")
app.include_router(instruments.router, prefix="/api/v1")
app.include_router(stocks.router, prefix="/api/v1")
app.include_router(data_health.router, prefix="/api/v1")
app.include_router(ingestion.router, prefix="/api/v1")
app.include_router(portfolio.router, prefix="/api/v1")
app.include_router(import_trades.router, prefix="/api/v1")
app.include_router(portfolio_intelligence.router, prefix="/api/v1")
app.include_router(rebalance.router, prefix="/api/v1")
app.include_router(journal.router, prefix="/api/v1")
app.include_router(daily.router, prefix="/api/v1")
app.include_router(decisions.router, prefix="/api/v1")
app.include_router(screener.router, prefix="/api/v1")
app.include_router(performance.router, prefix="/api/v1")
app.include_router(macro.router, prefix="/api/v1")
app.include_router(notebook.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "Stock Intelligence API",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}

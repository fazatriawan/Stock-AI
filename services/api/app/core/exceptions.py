from fastapi import Request
from fastapi.responses import JSONResponse


class StockIntelligenceError(Exception):
    """Base error."""
    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR", retryable: bool = False):
        self.message = message
        self.error_code = error_code
        self.retryable = retryable
        super().__init__(message)


class DataNotFoundError(StockIntelligenceError):
    def __init__(self, message: str):
        super().__init__(message, "NOT_FOUND", False)


class DataStaleError(StockIntelligenceError):
    def __init__(self, message: str):
        super().__init__(message, "DATA_STALE", True)


class ProviderError(StockIntelligenceError):
    def __init__(self, message: str, provider: str = "unknown"):
        super().__init__(f"[{provider}] {message}", "PROVIDER_ERROR", True)
        self.provider = provider


class InsufficientDataError(StockIntelligenceError):
    def __init__(self, message: str):
        super().__init__(message, "INSUFFICIENT_DATA", False)


class ValidationError(StockIntelligenceError):
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR", False)


async def stock_error_handler(request: Request, exc: StockIntelligenceError) -> JSONResponse:
    status_map = {
        "NOT_FOUND": 404,
        "VALIDATION_ERROR": 422,
        "INSUFFICIENT_DATA": 200,
        "DATA_STALE": 200,
        "PROVIDER_ERROR": 503,
    }
    status_code = status_map.get(exc.error_code, 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        },
    )

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import init_db
from app.routers import auth

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    log.info("agentis_api_started", environment=settings.environment)
    yield
    log.info("agentis_api_stopped")


app = FastAPI(
    title="Agentis API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        error_body = detail
    else:
        error_body = {"code": "error", "message": str(detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_body},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": str(exc.errors())}},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred"}}
    )

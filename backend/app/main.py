import uuid as uuid_lib
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import init_db
from app.logging_config import configure_logging
from app.routers import auth, tasks
from app.routers.files import router as files_router
from app.routers.ws import router as ws_router
from app.routers.admin import router as admin_router
from app.routers.organizations import router as orgs_router
from app.routers.webhooks import router as webhooks_router
from app.routers.tools_admin import router as tools_admin_router
from app.routers.integrations import router as integrations_router
from app.routers.voice import router as voice_router
from app.routers.marketplace import router as marketplace_router
from app.routers.config_admin import router as config_admin_router
from app.routers.oidc_config import router as oidc_config_router
from app.routers.oidc_auth import router as oidc_auth_router
from app.observability.metrics import metrics_router
from app.tools.registry import tool_registry
from app.tools.init_registry import register_all_tools, seed_tool_configs
from app.services.marketplace_seed import seed_marketplace_plugins
from app.database import AsyncSessionLocal

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    register_all_tools()
    async with AsyncSessionLocal() as db:
        await seed_tool_configs(db)
        await seed_marketplace_plugins(db)

    # Warn if fernet_key is missing (integrations feature requires it)
    if not settings.fernet_key:
        log.warning("fernet_key_not_set",
                    detail="AGENTIS_FERNET_KEY is not configured — /integrations endpoints will fail")
    else:
        try:
            from cryptography.fernet import Fernet as _Fernet
            _Fernet(settings.fernet_key.encode())
        except Exception:
            log.warning("fernet_key_invalid",
                        detail="AGENTIS_FERNET_KEY is set but not a valid Fernet key")

    log.info("agentis_api_started", environment=settings.environment,
             tools=tool_registry.list_names())
    yield
    log.info("agentis_api_stopped")


app = FastAPI(
    title="Agentis API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid_lib.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        path=request.url.path,
        method=request.method,
    )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    log.info("http_request", status_code=response.status_code)
    return response


app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(files_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(orgs_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(tools_admin_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(marketplace_router, prefix="/api/v1")
app.include_router(config_admin_router, prefix="/api/v1")
app.include_router(oidc_config_router, prefix="/api/v1")
app.include_router(oidc_auth_router, prefix="/api/v1")
app.include_router(metrics_router)  # /metrics — no prefix, Prometheus standard


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
        headers=dict(exc.headers) if exc.headers else None,
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

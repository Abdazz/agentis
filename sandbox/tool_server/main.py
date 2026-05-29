import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any

sys.path.insert(0, "/app")

from sandbox.tool_server.dispatcher import dispatch, register_browser

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tool_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        register_browser()
        log.info("Browser handler registered")
    except ImportError as e:
        log.warning(f"Browser handler not available: {e}")
    log.info("Tool server ready on port 9999")
    yield


app = FastAPI(lifespan=lifespan)


class RpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = {}
    id: int | str | None = None


@app.post("/rpc")
async def rpc_endpoint(req: RpcRequest):
    try:
        result = await dispatch(req.method, req.params)
        return {"jsonrpc": "2.0", "result": result, "id": req.id}
    except ValueError as e:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32600, "message": str(e)},
                "id": req.id,
            },
        )
    except Exception as e:
        log.exception(f"Tool error: {req.method}")
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": f"Tool execution failed: {str(e)}"},
                "id": req.id,
            },
        )


@app.get("/health")
async def health():
    return {"status": "ok"}

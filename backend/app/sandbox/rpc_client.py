import httpx
from typing import Any


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"RPC error {code}: {message}")


class SandboxRpcClient:
    """
    Async JSON-RPC 2.0 client over HTTP.
    Connects to the tool server running inside a sandbox container.
    """

    def __init__(self, endpoint: str, timeout_s: float = 130.0):
        self._url = f"{endpoint.rstrip('/')}/rpc"
        self._timeout = timeout_s
        self._counter = 0

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._counter += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._counter,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._url, json=payload)
            resp.raise_for_status()
            body = resp.json()

        if "error" in body:
            err = body["error"]
            raise RpcError(code=err.get("code", -1), message=err.get("message", "Unknown error"))

        return body.get("result", {})

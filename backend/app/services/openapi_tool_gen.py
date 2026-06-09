"""Generate BaseTool instances from an OpenAPI 3.0 spec (spec §6.5, Phase 3A)."""
from __future__ import annotations
import json
from typing import Any
import httpx
from app.tools.base import BaseTool, SessionContext, ToolResult


async def _fetch_spec(url: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        if url.endswith(".yaml") or url.endswith(".yml") or "yaml" in resp.headers.get("content-type", ""):
            import yaml
            return yaml.safe_load(resp.text)
        return resp.json()


def _build_input_schema_from_operation(op: dict) -> dict:
    """Derive a JSON Schema object from OpenAPI operation parameters + requestBody."""
    props: dict[str, Any] = {}
    required: list[str] = []

    for param in op.get("parameters", []):
        name = param["name"]
        schema = param.get("schema", {"type": "string"})
        props[name] = {**schema, "description": param.get("description", "")}
        if param.get("required", False):
            required.append(name)

    body = op.get("requestBody", {})
    for media_type, media in body.get("content", {}).items():
        if "json" in media_type:
            body_schema = media.get("schema", {})
            for k, v in body_schema.get("properties", {}).items():
                props[k] = v
            for r in body_schema.get("required", []):
                if r not in required:
                    required.append(r)
            break

    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


class OpenApiProxyTool(BaseTool):
    """Dynamic BaseTool that routes calls through HttpCallerTool's sandbox RPC.

    BaseTool.__init_subclass__ only validates concrete (non-abstract) subclasses,
    checking that *class-level* name/description are non-empty.  We satisfy it with
    non-empty class-level sentinel values and then override per-instance in __init__.
    """

    # Class-level sentinels that satisfy BaseTool.__init_subclass__ validation.
    name: str = "openapi__proxy"
    description: str = "Dynamic OpenAPI proxy tool"
    input_schema: dict = {}

    def __init__(self, operation_id: str, method: str, base_url: str,
                 path: str, description: str, input_schema: dict):
        # Override at instance level — these shadow the class-level attributes.
        self.name = f"openapi__{operation_id}"
        self.description = description
        self.input_schema = input_schema
        self._method = method.upper()
        self._base_url = base_url.rstrip("/")
        self._path = path

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        from app.tools.http_caller import HttpCallerTool
        http_tool = HttpCallerTool()

        path = self._path
        url = self._base_url + path
        http_params: dict = {"method": self._method, "url": url}

        if self._method == "GET":
            if params:
                from urllib.parse import urlencode
                url = f"{url}?{urlencode(params)}"
                http_params["url"] = url
        else:
            if params:
                http_params["body"] = json.dumps(params)
                http_params["headers"] = {"Content-Type": "application/json"}

        return await http_tool.execute(http_params, session)


def generate_tools_from_spec(spec: dict, spec_url: str) -> list[OpenApiProxyTool]:
    """Parse an OpenAPI 3.0 spec dict and return a list of OpenApiProxyTool instances."""
    base_url = ""
    for server in spec.get("servers", []):
        base_url = server.get("url", "")
        break
    if not base_url and spec_url:
        from urllib.parse import urlparse
        p = urlparse(spec_url)
        base_url = f"{p.scheme}://{p.netloc}"

    tools = []
    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            operation_id = op.get("operationId")
            if not operation_id:
                operation_id = f"{method.upper()}_{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"
            description = op.get("summary") or op.get("description") or operation_id
            input_schema = _build_input_schema_from_operation(op)
            tools.append(OpenApiProxyTool(
                operation_id=operation_id,
                method=method,
                base_url=base_url,
                path=path,
                description=description,
                input_schema=input_schema,
            ))
    return tools


async def fetch_and_generate(spec_url: str) -> list[OpenApiProxyTool]:
    """Fetch an OpenAPI spec from URL and generate tools."""
    spec = await _fetch_spec(spec_url)
    return generate_tools_from_spec(spec, spec_url)

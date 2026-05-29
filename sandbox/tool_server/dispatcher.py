from sandbox.tool_server.handlers import file_system, code_executor

_HANDLERS = {
    "file_system": file_system.handle,
    "code_executor": code_executor.handle,
}


def register_browser():
    from sandbox.tool_server.handlers import browser
    _HANDLERS["browser"] = browser.handle


async def dispatch(method: str, params: dict) -> dict:
    """method format: "{tool_name}.{action}" e.g. "file_system.write" """
    parts = method.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid method format: {method!r}. Expected 'tool.action'")

    tool_name, action = parts
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown tool: {tool_name!r}")

    return await handler(action, params)

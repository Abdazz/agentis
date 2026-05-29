import asyncio
import os
from pathlib import Path

WORKSPACE = Path("/workspace")
OUTPUTS = WORKSPACE / "outputs"


async def _run(cmd: list[str], timeout_s: int, env: dict | None = None) -> dict:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    before = set(OUTPUTS.rglob("*"))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(WORKSPACE),
        env={**os.environ, **(env or {})},
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {
            "stdout": "", "stderr": f"Execution timed out after {timeout_s}s",
            "exit_code": -1, "generated_files": [], "truncated": False,
        }

    after = set(OUTPUTS.rglob("*"))
    new_files = [str(p.relative_to(WORKSPACE)) for p in (after - before) if p.is_file()]

    max_chars = 10_000
    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")
    truncated = len(stdout) > max_chars or len(stderr) > max_chars

    return {
        "stdout": stdout[:max_chars],
        "stderr": stderr[:max_chars],
        "exit_code": proc.returncode,
        "generated_files": new_files,
        "truncated": truncated,
    }


async def handle(action: str, params: dict) -> dict:
    timeout = params.get("timeout_s", 120)

    if action == "run_python":
        return await _run(
            ["python3", "-c", params["code"]],
            timeout_s=timeout,
        )

    elif action == "run_node":
        return await _run(
            ["node", "-e", params["code"]],
            timeout_s=timeout,
        )

    elif action == "run_bash":
        return await _run(
            ["bash", "-c", params["command"]],
            timeout_s=timeout,
        )

    raise ValueError(f"Unknown code_executor action: {action}")

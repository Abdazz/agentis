import os
import shutil
from pathlib import Path

WORKSPACE = Path("/workspace")


def _safe_path(path: str) -> Path:
    """Resolve path and ensure it stays within /workspace. Raises ValueError otherwise."""
    if not path:
        raise ValueError("Path must not be empty")
    resolved = (WORKSPACE / path.lstrip("/")).resolve()
    # Use parents check to avoid prefix collision (e.g. /workspace-evil)
    if resolved != WORKSPACE and WORKSPACE not in resolved.parents:
        raise ValueError(f"Path '{path}' escapes /workspace")
    return resolved


async def handle(action: str, params: dict) -> dict:
    if action == "write":
        p = _safe_path(params["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        content = params["content"]
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(bytes(content))
        return {"success": True, "size_bytes": p.stat().st_size}

    elif action == "read":
        p = _safe_path(params["path"])
        text = p.read_text(encoding="utf-8", errors="replace")
        max_chars = params.get("max_chars", 50_000)
        truncated = len(text) > max_chars
        return {"content": text[:max_chars], "truncated": truncated}

    elif action == "list":
        p = _safe_path(params.get("directory", "."))
        entries = []
        for item in sorted(p.iterdir()):
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            })
        return {"entries": entries}

    elif action == "delete":
        p = _safe_path(params["path"])
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"success": True}

    elif action == "copy":
        src = _safe_path(params["src"])
        dst = _safe_path(params["dst"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return {"success": True}

    elif action == "compress":
        paths = [_safe_path(p) for p in params["paths"]]
        archive = _safe_path(params["archive_name"])
        import tarfile
        with tarfile.open(archive, "w:gz") as tar:
            for p in paths:
                tar.add(p, arcname=p.name)
        return {"archive_path": str(archive.relative_to(WORKSPACE))}

    raise ValueError(f"Unknown file_system action: {action}")

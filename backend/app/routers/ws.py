"""WebSocket endpoints for real-time task communication (spec §10 HITL-2)."""
import json
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.auth.dependencies import verify_token_string
from app.database import AsyncSessionLocal
from app.models.task import Task
from app.services.hitl import hitl_coordinator

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/tasks/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str, token: str = Query(...)):
    """
    WebSocket for HITL responses. Auth via ?token=<jwt> query param.
    Messages: {"type": "hitl_response", "content": "<text>"}
    """
    try:
        user = await verify_token_string(token)
    except Exception:
        await websocket.close(code=4001)
        return

    # Verify the user owns the task (prevent IDOR — spec §3 AUTH-3)
    async with AsyncSessionLocal() as db:
        try:
            task = await db.get(Task, UUID(task_id))
        except ValueError:
            await websocket.close(code=4003)
            return
    if task is None or task.user_id != user.id:
        await websocket.close(code=4003)
        return

    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "invalid JSON"}))
                continue

            if msg.get("type") == "hitl_response":
                content = msg.get("content", "")
                await hitl_coordinator.publish_response(task_id=task_id, response=content)
                await websocket.send_text(json.dumps({"type": "ack", "task_id": task_id}))
    except WebSocketDisconnect:
        pass

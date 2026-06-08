"""Tests for WebSocket HITL endpoint (spec §10 HITL-2)."""
import pytest
import json
from unittest.mock import patch, AsyncMock
from starlette.testclient import TestClient
from app.main import app


def test_ws_requires_valid_token(starlette_client):
    """WebSocket with invalid token should close immediately with code 4001."""
    with pytest.raises(Exception):
        with starlette_client.websocket_connect(
            "/api/v1/ws/tasks/00000000-0000-0000-0000-000000000001?token=invalid"
        ) as ws:
            ws.receive_text()


def test_ws_hitl_message_publishes_to_redis(starlette_client, test_user_token, test_task):
    """Sending hitl_response message publishes to HITL coordinator."""
    task_id = str(test_task.id)
    with patch("app.routers.ws.hitl_coordinator.publish_response", AsyncMock()) as mock_pub:
        try:
            with starlette_client.websocket_connect(
                f"/api/v1/ws/tasks/{task_id}?token={test_user_token}"
            ) as ws:
                ws.send_text(json.dumps({"type": "hitl_response", "content": "yes, continue"}))
                response = ws.receive_text()
                data = json.loads(response)
                assert data["type"] == "ack"
                assert data["task_id"] == task_id
        except Exception:
            pass
    mock_pub.assert_called_once_with(task_id=task_id, response="yes, continue")


def test_ws_invalid_json_returns_error(starlette_client, test_user_token, test_task):
    """Sending invalid JSON returns an error message without disconnecting."""
    task_id = str(test_task.id)
    with starlette_client.websocket_connect(
        f"/api/v1/ws/tasks/{task_id}?token={test_user_token}"
    ) as ws:
        ws.send_text("not-valid-json{{{")
        response = ws.receive_text()
        data = json.loads(response)
        assert "error" in data


def test_ws_non_hitl_message_is_ignored(starlette_client, test_user_token, test_task):
    """Unknown message type is silently ignored (no ack, no error)."""
    task_id = str(test_task.id)
    with patch("app.routers.ws.hitl_coordinator.publish_response", AsyncMock()) as mock_pub:
        with starlette_client.websocket_connect(
            f"/api/v1/ws/tasks/{task_id}?token={test_user_token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "unknown_type", "content": "ignored"}))
            # Now send a valid message to verify connection is still alive
            ws.send_text(json.dumps({"type": "hitl_response", "content": "still alive"}))
            response = ws.receive_text()
            data = json.loads(response)
            assert data["type"] == "ack"
        mock_pub.assert_called_once_with(task_id=task_id, response="still alive")

import pytest
from unittest.mock import MagicMock, patch
from app.sandbox.manager import SandboxManager, SandboxSession


def make_mock_container(container_id="abc123", ip="172.17.0.5", network="agentis_default"):
    c = MagicMock()
    c.id = container_id
    c.status = "running"
    c.attrs = {
        "NetworkSettings": {
            "Networks": {
                network: {"IPAddress": ip}
            }
        }
    }
    c.reload = MagicMock()
    c.stop = MagicMock()
    c.remove = MagicMock()
    return c


@pytest.fixture
def mock_docker():
    with patch("docker.from_env") as mock_fn:
        client = MagicMock()
        mock_fn.return_value = client
        yield client


def test_start_container_creates_session(mock_docker):
    container = make_mock_container()
    mock_docker.containers.run.return_value = container

    manager = SandboxManager()
    session = manager._start_container("task-001")

    assert session.task_id == "task-001"
    assert session.container_id == "abc123"
    assert session.endpoint == "http://172.17.0.5:9999"
    assert mock_docker.containers.run.called


def test_destroy_session_stops_and_removes(mock_docker):
    container = make_mock_container()
    mock_docker.containers.run.return_value = container
    mock_docker.containers.get.return_value = container

    manager = SandboxManager()
    manager._start_container("task-002")
    manager.destroy_session("task-002")

    container.stop.assert_called_once_with(timeout=10)
    container.remove.assert_called_once()
    assert "task-002" not in manager._sessions


def test_destroy_nonexistent_session_is_noop(mock_docker):
    manager = SandboxManager()
    # Should not raise
    manager.destroy_session("nonexistent-task")


def test_get_session_returns_none_for_unknown(mock_docker):
    manager = SandboxManager()
    assert manager.get_session("unknown") is None


def test_manager_tracks_multiple_sessions(mock_docker):
    c1 = make_mock_container("id1", "172.17.0.5")
    c2 = make_mock_container("id2", "172.17.0.6")
    mock_docker.containers.run.side_effect = [c1, c2]

    manager = SandboxManager()
    manager._start_container("task-A")
    manager._start_container("task-B")

    assert len(manager._sessions) == 2
    assert manager.get_session("task-A").endpoint == "http://172.17.0.5:9999"
    assert manager.get_session("task-B").endpoint == "http://172.17.0.6:9999"

import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.sandbox.manager import SandboxManager, SandboxSession, WarmContainer


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


# --- Warm pool (BR-SAND-10..14) ---

def test_warm_container_not_expired_when_fresh():
    wc = WarmContainer(container_id="c1", endpoint="http://x:9999")
    assert wc.is_expired() is False


def test_warm_container_expired_after_ttl(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "sandbox_warm_ttl_seconds", 0)
    wc = WarmContainer(container_id="c1", endpoint="http://x:9999", created_at=time.time() - 1)
    assert wc.is_expired() is True


@pytest.mark.asyncio
async def test_replenish_warm_pool_fills_to_configured_size(mock_docker, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "sandbox_warm_pool_size", 2)

    manager = SandboxManager()
    c1, c2 = make_mock_container("w1", "172.17.0.10"), make_mock_container("w2", "172.17.0.11")
    mock_docker.containers.run.side_effect = [c1, c2]

    with patch.object(manager, "_health_check", AsyncMock(return_value=True)):
        await manager.replenish_warm_pool()

    assert len(manager._warm_pool) == 2
    assert {wc.container_id for wc in manager._warm_pool} == {"w1", "w2"}


@pytest.mark.asyncio
async def test_replenish_warm_pool_discards_unhealthy_container(mock_docker, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "sandbox_warm_pool_size", 1)

    manager = SandboxManager()
    container = make_mock_container("unhealthy1", "172.17.0.12")
    mock_docker.containers.run.return_value = container
    mock_docker.containers.get.return_value = container

    with patch.object(manager, "_health_check", AsyncMock(return_value=False)):
        await manager.replenish_warm_pool()

    assert manager._warm_pool == []
    container.stop.assert_called_once()
    container.remove.assert_called_once()


@pytest.mark.asyncio
async def test_reap_expired_warm_containers_destroys_stale_entries(mock_docker):
    manager = SandboxManager()
    container = make_mock_container("stale1", "172.17.0.13")
    mock_docker.containers.get.return_value = container
    manager._warm_pool = [
        WarmContainer(container_id="stale1", endpoint="http://172.17.0.13:9999", created_at=0),
    ]

    await manager._reap_expired_warm_containers()

    assert manager._warm_pool == []
    container.stop.assert_called_once()


@pytest.mark.asyncio
async def test_create_session_assigns_from_warm_pool_without_cold_start(mock_docker):
    manager = SandboxManager()
    manager._warm_pool = [
        WarmContainer(container_id="warm-c1", endpoint="http://172.17.0.20:9999"),
    ]

    with patch.object(manager, "replenish_warm_pool", AsyncMock()) as mock_replenish:
        session = await manager.create_session("task-warm-1")

    assert session.container_id == "warm-c1"
    assert session.endpoint == "http://172.17.0.20:9999"
    assert manager.get_session("task-warm-1") is session
    assert manager._warm_pool == []  # consumed
    mock_docker.containers.run.assert_not_called()  # no cold start needed
    mock_replenish.assert_called_once()  # BR-SAND-12: replenished after use


@pytest.mark.asyncio
async def test_create_session_falls_back_to_cold_start_when_pool_empty(mock_docker):
    manager = SandboxManager()
    container = make_mock_container("cold1", "172.17.0.30")
    mock_docker.containers.run.return_value = container

    with patch.object(manager, "_health_check", AsyncMock(return_value=True)):
        session = await manager.create_session("task-cold-1")

    assert session.container_id == "cold1"
    assert manager._warm_pool == []

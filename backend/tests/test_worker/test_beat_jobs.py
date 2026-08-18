import pytest
from unittest.mock import MagicMock, patch


def test_decay_memory_importance_calls_decay():
    mock_ltm = MagicMock()
    mock_ltm.decay_all.return_value = 42
    with patch("app.worker.beat_jobs.long_term_memory", mock_ltm):
        from app.worker.beat_jobs import decay_memory_importance
        result = decay_memory_importance()
        mock_ltm.decay_all.assert_called_once_with(factor=0.95)
        assert result["updated"] == 42


def test_prune_memory_calls_prune():
    mock_ltm = MagicMock()
    mock_ltm.prune.return_value = 3
    with patch("app.worker.beat_jobs.long_term_memory", mock_ltm):
        from app.worker.beat_jobs import prune_memory
        result = prune_memory()
        mock_ltm.prune.assert_called_once_with(threshold=0.05)
        assert result["deleted"] == 3


def test_replenish_sandbox_warm_pool_calls_manager():
    from unittest.mock import AsyncMock
    from app.sandbox.manager import sandbox_manager, WarmContainer

    with patch.object(sandbox_manager, "replenish_warm_pool", AsyncMock()) as mock_replenish:
        sandbox_manager._warm_pool = [WarmContainer(container_id="w1", endpoint="http://x:9999")]
        from app.worker.beat_jobs import replenish_sandbox_warm_pool
        result = replenish_sandbox_warm_pool()

    mock_replenish.assert_called_once()
    assert result["pool_size"] == 1
    sandbox_manager._warm_pool = []  # don't leak state into other tests

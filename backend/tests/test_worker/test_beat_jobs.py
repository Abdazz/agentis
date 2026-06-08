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

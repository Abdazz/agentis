import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_write_audit_event_inserts_row():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    with patch("app.services.audit.AsyncSessionLocal") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.services.audit import write_audit_event
        await write_audit_event(
            actor_id="u1",
            actor_email="admin@test.com",
            action="user.suspend",
            resource_type="user",
            resource_id="r1",
            metadata={"reason": "spam"},
        )
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_write_audit_event_stores_correct_action():
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    added_obj = None

    def capture_add(obj):
        nonlocal added_obj
        added_obj = obj

    mock_session.add.side_effect = capture_add

    with patch("app.services.audit.AsyncSessionLocal") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        from app.services.audit import write_audit_event
        await write_audit_event(
            actor_id="u1",
            actor_email="a@b.com",
            action="llm.config.update",
            resource_type="llm_config",
        )
        assert added_obj is not None
        assert added_obj.event_type == "llm.config.update"
        assert added_obj.event_data["actor_email"] == "a@b.com"

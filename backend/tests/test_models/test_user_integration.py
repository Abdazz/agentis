import uuid
from datetime import datetime, timezone

import pytest

from app.models.user_integration import UserIntegration


@pytest.mark.asyncio
async def test_user_integration_create(db_session):
    from app.models.user import User
    from app.auth.password import hash_password

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"integ_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    integ = UserIntegration(
        user_id=user_id,
        provider="smtp",
        credentials_encrypted="FAKEENCRYPTED",
    )
    db_session.add(integ)
    await db_session.commit()
    await db_session.refresh(integ)

    assert integ.id is not None
    assert integ.provider == "smtp"
    assert integ.credentials_encrypted == "FAKEENCRYPTED"
    assert integ.is_active is True
    assert integ.created_at is not None


@pytest.mark.asyncio
async def test_user_integration_cascade_delete(db_session):
    """Deleting a user cascades to their integrations."""
    from app.models.user import User
    from app.auth.password import hash_password
    from sqlalchemy import select

    user = User(
        id=uuid.uuid4(),
        email=f"cascade_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    integ = UserIntegration(
        user_id=user.id,
        provider="caldav",
        credentials_encrypted="ENCRYPTED",
    )
    db_session.add(integ)
    await db_session.commit()

    integ_id = integ.id
    await db_session.delete(user)
    await db_session.commit()

    result = await db_session.execute(
        select(UserIntegration).where(UserIntegration.id == integ_id)
    )
    assert result.scalar_one_or_none() is None

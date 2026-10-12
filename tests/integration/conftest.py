"""Fixtures for driving the real FastAPI app without Postgres or Docker.

`get_db` is overridden with a stub session, and the `TestClient` is used
without a `with` block so the startup hook (which connects to Postgres and
re-raises on failure, see `api/main.py`) never runs.
"""

from collections.abc import AsyncGenerator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from api.main import app
from core.config import settings
from core.database import get_db
from core.models.user import User

USER_ID = "11111111-1111-1111-1111-111111111111"


class StubResult:
    """Stand-in for a SQLAlchemy result, shaped for the queries on the profile route."""

    def scalar_one_or_none(self) -> User:
        """Return a fixed user, as the user lookup in `get_current_user` expects.

        Returns:
            A `User` whose id is `USER_ID`.
        """
        user = User()
        user.id = USER_ID
        user.email = "jane@example.com"
        return user

    def scalars(self) -> "StubResult":
        """Return self so `result.scalars().first()` works.

        Returns:
            This result.
        """
        return self

    def first(self) -> None:
        """Return no row, as the profile lookup in `get_profile` expects.

        Returns:
            None, so the route responds 404.
        """
        return None


class StubSession:
    """Stand-in for `AsyncSession` that records every `execute` call."""

    def __init__(self) -> None:
        """Start with no recorded calls."""
        self.calls: list[Any] = []

    async def execute(self, stmt: Any) -> StubResult:
        """Record the statement and return a stub result.

        Args:
            stmt: The SQLAlchemy statement the caller executed.

        Returns:
            A `StubResult`.
        """
        self.calls.append(stmt)
        return StubResult()


@pytest.fixture
def db_stub() -> StubSession:
    """Return a fresh stub session for one test.

    Returns:
        A `StubSession` with no recorded calls.
    """
    return StubSession()


@pytest.fixture
def client(db_stub: StubSession) -> Iterator[TestClient]:
    """Return a client for `api.main.app` with `get_db` overridden by `db_stub`.

    Args:
        db_stub: The stub session the overridden `get_db` yields.

    Yields:
        A `TestClient` that does not run the app's startup hook.
    """

    async def override_get_db() -> AsyncGenerator[StubSession, None]:
        yield db_stub

    app.dependency_overrides[get_db] = override_get_db
    try:
        # No `with` block: entering it would run the startup hook, which needs Postgres.
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def make_token() -> Callable[..., str]:
    """Return a helper that signs a JWT for `USER_ID`.

    Returns:
        A function taking `secret` and `delta` that returns an encoded token
        expiring `delta` from now, signed with `settings.jwt_algorithm`.
    """

    def _make_token(
        secret: str = settings.secret_key,
        delta: timedelta = timedelta(minutes=30),
    ) -> str:
        return jwt.encode(
            {"sub": USER_ID, "exp": datetime.now(UTC) + delta},
            secret,
            algorithm=settings.jwt_algorithm,
        )

    return _make_token

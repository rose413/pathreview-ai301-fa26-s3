"""Integration tests for `api/middleware/auth.py` through a real protected route.

Each request goes to `GET /profiles/{id}` on `api.main.app`. The database is a
stub (see `conftest.py`), so these need no Postgres or Docker.
"""

from datetime import timedelta

import pytest

pytestmark = pytest.mark.integration

PROFILE_URL = "/profiles/22222222-2222-2222-2222-222222222222"


def test_missing_authorization_header(client, db_stub):
    """A request with no Authorization header is rejected before the database."""
    response = client.get(PROFILE_URL)

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db_stub.calls == []


def test_malformed_token(client, db_stub):
    """A token that is not a JWT is rejected before the database."""
    response = client.get(PROFILE_URL, headers={"Authorization": "Bearer not.a.jwt"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db_stub.calls == []


def test_wrong_signing_secret(client, db_stub, make_token):
    """A token signed with a different secret is rejected before the database."""
    token = make_token(secret="other-secret")

    response = client.get(PROFILE_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db_stub.calls == []


def test_expired_token(client, db_stub, make_token):
    """An expired token is rejected before the database."""
    token = make_token(delta=timedelta(minutes=-5))

    response = client.get(PROFILE_URL, headers={"Authorization": f"Bearer {token}"})

    # The detail is deliberately not asserted. The "Token has expired" branch in
    # auth.py is unreachable today (jose rejects the token inside
    # decode_access_token first), so pinning the generic message would lock that
    # dead branch in. See Finding 1:
    # https://github.com/codepath/pathreview-ai301-fa26-s3/issues/38#issuecomment-5864870840
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert db_stub.calls == []


def test_valid_token_reaches_route(client, db_stub, make_token):
    """A valid token passes auth and reaches the route handler (control)."""
    token = make_token()

    response = client.get(PROFILE_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Profile not found"
    # One user lookup in get_current_user, then one profile lookup in the route.
    assert len(db_stub.calls) == 2

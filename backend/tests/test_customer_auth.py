import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_db = tmp_path / "test_auth.db"
    monkeypatch.setattr(main, "DATABASE_PATH", test_db)
    main.init_database()
    with main._login_attempts_lock:
        main._login_attempts.clear()
    with TestClient(main.app) as test_client:
        yield test_client


def signup(client, email="learner@example.com", password="StrongPassword123!"):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password},
    )


def test_signup_creates_account_and_session(client):
    response = signup(client)
    assert response.status_code == 201

    data = response.json()
    assert data["account"]["email"] == "learner@example.com"
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["expires_at"]

    # Verify the issued token works.
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["authenticated"] is True


def test_signup_normalizes_email_and_rejects_duplicate(client):
    first = signup(client, "Learner@Example.com")
    second = signup(client, "learner@example.com")

    assert first.status_code == 201
    assert second.status_code == 409


def test_signup_rejects_short_password(client):
    response = signup(client, password="short")
    assert response.status_code == 422


def test_login_accepts_correct_password(client):
    signup(client)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "LEARNER@example.com",
            "password": "StrongPassword123!",
        },
    )

    assert response.status_code == 200
    assert response.json()["account"]["email"] == "learner@example.com"
    assert response.json()["access_token"]


def test_login_rejects_incorrect_password(client):
    signup(client)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "learner@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_me_rejects_missing_or_invalid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    ).status_code == 401


def test_logout_revokes_session(client):
    created = signup(client).json()
    headers = {"Authorization": f"Bearer {created['access_token']}"}

    logout = client.post("/api/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert logout.json()["status"] == "logged_out"

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 401


def test_database_stores_password_hash_and_token_hash_not_plaintext(client, tmp_path):
    password = "StrongPassword123!"
    created = signup(client, password=password).json()
    token = created["access_token"]

    # The fixture's database is in the pytest temporary directory.
    # Find the account and session through the configured database path.
    with sqlite3.connect(main.DATABASE_PATH) as connection:
        account = connection.execute(
            "SELECT password_salt, password_hash FROM customer_accounts WHERE email = ?",
            ("learner@example.com",),
        ).fetchone()
        session = connection.execute(
            "SELECT token_hash FROM customer_sessions WHERE account_id = ?",
            (created["account"]["id"],),
        ).fetchone()

    assert account is not None
    assert account[0] != password
    assert account[1] != password
    assert session is not None
    assert session[0] != token


def test_expired_session_is_rejected(client):
    import hashlib
    from datetime import datetime, timedelta, timezone

    created = signup(client).json()
    token_hash = hashlib.sha256(
        created["access_token"].encode("utf-8")
    ).hexdigest()

    expired_at = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).isoformat()

    with sqlite3.connect(main.DATABASE_PATH) as connection:
        connection.execute(
            """
            UPDATE customer_sessions
            SET expires_at = ?
            WHERE token_hash = ?
            """,
            (expired_at, token_hash),
        )

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {created['access_token']}"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic abc123",
        "Bearer ",
        "Bearer    ",
        "Bearer " + ("x" * 513),
    ],
)
def test_me_rejects_malformed_authorization_headers(client, authorization):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": authorization},
    )

    assert response.status_code == 401

def test_signup_rolls_back_account_when_session_creation_fails(
    client, monkeypatch
):
    def fail_session_creation(account_id, connection=None):
        raise RuntimeError("simulated session failure")

    monkeypatch.setattr(
        main,
        "_create_customer_session",
        fail_session_creation,
    )

    with pytest.raises(RuntimeError, match="simulated session failure"):
        signup(client, email="rollback@example.com")

    with sqlite3.connect(main.DATABASE_PATH) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM customer_accounts WHERE email = ?",
            ("rollback@example.com",),
        ).fetchone()

    assert row[0] == 0



def test_login_rate_limit_returns_429_after_five_attempts(client):
    signup(client)

    payload = {
        "email": "learner@example.com",
        "password": "WrongPassword123!",
    }

    for _ in range(5):
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401

    limited = client.post("/api/auth/login", json=payload)

    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
    assert int(limited.headers["Retry-After"]) > 0


def test_login_rate_limit_allows_login_after_window_expires(
    client, monkeypatch
):
    signup(client)

    current_time = [1000.0]
    monkeypatch.setattr(main, "monotonic", lambda: current_time[0])

    payload = {
        "email": "learner@example.com",
        "password": "WrongPassword123!",
    }

    for _ in range(5):
        response = client.post("/api/auth/login", json=payload)
        assert response.status_code == 401

    limited = client.post("/api/auth/login", json=payload)
    assert limited.status_code == 429

    current_time[0] += main.LOGIN_RATE_WINDOW_SECONDS

    after_window = client.post("/api/auth/login", json=payload)
    assert after_window.status_code == 401


def test_login_rate_limiter_enforces_ip_capacity(monkeypatch):
    current_time = [1000.0]
    monkeypatch.setattr(main, "monotonic", lambda: current_time[0])

    with main._login_attempts_lock:
        main._login_attempts.clear()

    original_capacity = main.MAX_TRACKED_LOGIN_IPS
    main.MAX_TRACKED_LOGIN_IPS = 2

    try:
        assert main.check_login_rate_limit("192.0.2.1") == (True, 0)
        assert main.check_login_rate_limit("192.0.2.2") == (True, 0)

        allowed, retry_after = main.check_login_rate_limit("192.0.2.3")
        assert allowed is False
        assert retry_after == main.LOGIN_RATE_WINDOW_SECONDS

        current_time[0] += main.LOGIN_RATE_WINDOW_SECONDS
        assert main.check_login_rate_limit("192.0.2.3") == (True, 0)

        with main._login_attempts_lock:
            assert len(main._login_attempts) <= 2
    finally:
        main.MAX_TRACKED_LOGIN_IPS = original_capacity
        with main._login_attempts_lock:
            main._login_attempts.clear()

    assert original_capacity == 10_000

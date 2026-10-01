from pathlib import Path
import os
import tempfile
from datetime import datetime, timezone, timedelta

_db = Path(tempfile.mkdtemp()) / "doom_v17.db"
os.environ.update({
    "DOOM_API_KEY": "test-key",
    "DOOM_USER_NAME": "Renan",
    "DATABASE_URL": f"sqlite:///{_db}",
    "CORTEX_PROVIDERS": "ollama",
    "AGENT_ENABLED": "false",
    "DEEP_SEARCH_ENABLED": "false",
    "SECURITY_SESSION_HOURS": "12",
    "SECURITY_LEGACY_API_KEY": "true",
})

from fastapi.testclient import TestClient
from app.main import app, SessionLocal
from app.models import UserIdentity, ApiKeyRecord, UserSession


def test_identity_bootstrap_and_cookie_session():
    with TestClient(app) as client:
        h = client.get("/health")
        assert h.status_code == 200
        assert h.json()["version"] == "1.10.0"

        unauth = client.get("/api/auth/me")
        assert unauth.status_code == 401

        login = client.post("/api/auth/session", headers={"X-Doom-Key": "test-key"})
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["authenticated"] is True
        assert body["identity"]["display_name"] == "Renan"
        assert body["identity"]["auth_method"] == "session"
        assert body["access_token"]
        assert "doom_session" in client.cookies

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user_id"].startswith("usr_")
        assert me.json()["mode"] == "single_user_owner"

        sessions = client.get("/api/auth/sessions")
        assert sessions.status_code == 200
        assert len(sessions.json()) == 1
        assert sessions.json()[0]["revoked"] is False

        with SessionLocal() as db:
            assert db.query(UserIdentity).count() == 1
            assert db.query(ApiKeyRecord).count() == 1
            assert db.query(UserSession).count() == 1
            assert db.query(ApiKeyRecord).first().key_hash != "test-key"

        # Bearer session works even without cookie.
        token = body["access_token"]
        bearer = TestClient(app)
        try:
            resp = bearer.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            assert resp.json()["auth_method"] == "session"
        finally:
            bearer.close()

        logout = client.delete("/api/auth/session")
        assert logout.status_code == 200
        assert logout.json()["revoked"] is True

        assert client.get("/api/auth/me").status_code == 401
        # The compatibility key still authenticates, and can issue a fresh session.
        legacy = client.get("/api/auth/me", headers={"X-Doom-Key": "test-key"})
        assert legacy.status_code == 200
        assert legacy.json()["auth_method"] == "api_key"


def test_revoked_session_is_denied_and_revoke_all():
    with TestClient(app) as client:
        login = client.post("/api/auth/session", headers={"X-Doom-Key": "test-key"})
        token = login.json()["access_token"]
        client.get("/api/auth/me")
        # Revoke-all also clears the current cookie and invalidates the bearer token.
        revoked = client.post("/api/auth/revoke-all", headers={"Authorization": f"Bearer {token}"})
        assert revoked.status_code == 200
        assert revoked.json()["revoked_sessions"] >= 1

        check = TestClient(app)
        try:
            assert check.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
        finally:
            check.close()

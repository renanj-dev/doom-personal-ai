import os

os.environ.setdefault("DOOM_API_KEY", "test-doom-key")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/doom_v19_integrations_test.db")
os.environ.setdefault("INTEGRATIONS_ALLOW_PRIVATE", "true")

import httpx
import pytest

from app.db import Base, engine, SessionLocal
from app.integrations import INTEGRATION_ENGINE, IntegrationError
from app.models import ExternalIntegration
from app.tools import TOOL_ENGINE


@pytest.fixture(autouse=True)
def db_setup():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.query(ExternalIntegration).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(ExternalIntegration).delete()
        db.commit()


def test_register_and_list_integration():
    row = INTEGRATION_ENGINE.register(
        name="test_service",
        base_url="http://127.0.0.1:8787/",
        allowed_paths=["/v1", "/health"],
        allowed_methods=["GET", "POST"],
    )
    assert row["name"] == "test_service"
    assert row["allowed_methods"] == ["GET", "POST"]
    assert "test_service" in [x["name"] for x in INTEGRATION_ENGINE.list()]


def test_rejects_absolute_or_disallowed_path():
    INTEGRATION_ENGINE.register(name="test_service", base_url="http://127.0.0.1:8787/", allowed_paths=["/v1"], allowed_methods=["GET"])
    with pytest.raises(IntegrationError):
        INTEGRATION_ENGINE.request(integration="test_service", method="GET", path="https://example.com")
    with pytest.raises(IntegrationError):
        INTEGRATION_ENGINE.request(integration="test_service", method="GET", path="/admin")


def test_rejects_disallowed_method():
    INTEGRATION_ENGINE.register(name="test_service", base_url="http://127.0.0.1:8787/", allowed_paths=["/v1"], allowed_methods=["GET"])
    with pytest.raises(IntegrationError):
        INTEGRATION_ENGINE.request(integration="test_service", method="POST", path="/v1/test")


def test_secret_is_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("TEST_SERVICE_TOKEN", "Bearer secret-value")
    INTEGRATION_ENGINE.register(name="test_service", base_url="http://127.0.0.1:8787/", allowed_paths=["/v1"], allowed_methods=["GET"], auth_env_var="TEST_SERVICE_TOKEN")

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def request(self, method, url, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer secret-value"
            return httpx.Response(200, json={"pong": True}, request=httpx.Request(method, url))

    import app.integrations as integrations
    monkeypatch.setattr(integrations.httpx, "Client", lambda **kwargs: FakeClient())
    result = INTEGRATION_ENGINE.request(integration="test_service", method="GET", path="/v1/ping")
    assert result["ok"] is True
    assert result["data"] == {"pong": True}


def test_redirects_are_not_followed(monkeypatch):
    INTEGRATION_ENGINE.register(name="test_service", base_url="http://127.0.0.1:8787/", allowed_paths=["/"], allowed_methods=["GET"])

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def request(self, method, url, **kwargs):
            return httpx.Response(302, headers={"Location": "https://example.com/"}, request=httpx.Request(method, url))

    import app.integrations as integrations
    monkeypatch.setattr(integrations.httpx, "Client", lambda **kwargs: FakeClient())
    result = INTEGRATION_ENGINE.request(integration="test_service", method="GET", path="/")
    assert result["status_code"] == 302
    assert result["ok"] is True
    assert result["data"] == ""


def test_external_http_tool_defaults_to_confirmation_and_catalog_mentions_active_integration():
    INTEGRATION_ENGINE.register(name="test_service", base_url="http://127.0.0.1:8787/", allowed_paths=["/"], allowed_methods=["GET"])
    tool = next(x for x in TOOL_ENGINE.catalog() if x["name"] == "external_http")
    assert tool["permission"] == "confirm"
    assert "test_service" in tool["description"]

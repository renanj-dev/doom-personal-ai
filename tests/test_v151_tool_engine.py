from pathlib import Path
import os
import tempfile

_db = Path(tempfile.mkdtemp()) / "doom.db"
os.environ.update({
    "DOOM_API_KEY": "test-key",
    "DATABASE_URL": f"sqlite:///{_db}",
    "CORTEX_PROVIDERS": "ollama",
    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    "TOOL_TIMEOUT_SECONDS": "2",
    "TOOL_MAX_RETRIES": "1",
    "TOOL_MAX_BATCH": "5",
})

from fastapi.testclient import TestClient
from app.main import app
from app import main as main_mod
from app.cortex import CortexRoute


def fake_cortex(**kwargs):
    return (
        "Ferramenta pronta para uso.",
        CortexRoute("chat", "CONVERSA", "ollama", "test-model", 0, "teste"),
        None,
    )


main_mod.ask_with_cortex = fake_cortex


def test_tool_engine_2_catalog_permissions_confirmation_and_batch():
    with TestClient(app) as client:
        headers = {"X-Doom-Key": "test-key"}

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["version"] == "1.5.1"

        catalog = client.get("/api/tools", headers=headers)
        assert catalog.status_code == 200
        data = catalog.json()
        assert data["count"] == 3
        calculator = next(item for item in data["tools"] if item["name"] == "calculator")
        assert calculator["effective_mode"] == "safe"
        assert calculator["parameters"]["expression"]["required"] is True

        invalid = client.post(
            "/api/tools/execute",
            headers=headers,
            json={"session_id": "s1", "tool": "calculator", "args": {"expression": "2+2", "extra": 1}},
        )
        assert invalid.status_code == 200
        assert invalid.json()["status"] == "invalid_args"
        assert invalid.json()["ok"] is False

        policy = client.put(
            "/api/tools/permissions",
            headers=headers,
            json={"tool_name": "calculator", "mode": "confirm", "enabled": True, "scope": "global"},
        )
        assert policy.status_code == 200
        assert policy.json()["mode"] == "confirm"

        perms = client.get("/api/tools/permissions", headers=headers, params={"session_id": "s1"})
        assert perms.status_code == 200
        calc_perm = next(x for x in perms.json()["permissions"] if x["tool_name"] == "calculator")
        assert calc_perm["mode"] == "confirm"
        assert calc_perm["source"] == "global"

        pending = client.post(
            "/api/tools/execute",
            headers=headers,
            json={"session_id": "s1", "tool": "calculator", "args": {"expression": "(10+2)*3"}},
        )
        assert pending.status_code == 200
        p = pending.json()
        assert p["status"] == "confirmation_required"
        assert p["requires_confirmation"] is True
        token = p["confirmation_token"]
        assert token

        confirmed = client.post(
            "/api/tools/execute",
            headers=headers,
            json={
                "session_id": "s1",
                "tool": "calculator",
                "args": {"expression": "(10+2)*3"},
                "confirmation_token": token,
            },
        )
        assert confirmed.json()["ok"] is True
        assert confirmed.json()["data"]["result"] == 36
        assert confirmed.json()["attempt"] == 1
        assert confirmed.json()["request_id"]

        reused = client.post(
            "/api/tools/execute",
            headers=headers,
            json={
                "session_id": "s1",
                "tool": "calculator",
                "args": {"expression": "(10+2)*3"},
                "confirmation_token": token,
            },
        )
        assert reused.json()["ok"] is False
        assert reused.json()["status"] == "blocked"
        assert reused.json()["error"]

        # Restore global policy before batch test.
        reset = client.delete("/api/tools/permissions/calculator", headers=headers, params={"scope": "global"})
        assert reset.status_code == 200

        batch = client.post(
            "/api/tools/execute-batch",
            headers=headers,
            json={
                "session_id": "s1",
                "calls": [
                    {"tool": "calculator", "args": {"expression": "6*7"}},
                    {"tool": "current_time", "args": {}},
                ],
            },
        )
        assert batch.status_code == 200
        b = batch.json()
        assert b["ok"] is True
        assert len(b["results"]) == 2
        assert b["results"][0]["data"]["result"] == 42

        audit = client.get("/api/audit/tools", headers=headers, params={"session_id": "s1", "limit": 100})
        assert audit.status_code == 200
        records = audit.json()
        assert any("request_id=" in (r["detail"] or "") for r in records)


def test_chat_schema_accepts_tool_confirmation_metadata():
    def confirm_cortex(**kwargs):
        return (
            "Aguardando sua confirmação.",
            CortexRoute("execution", "EXECUÇÃO", "ollama", "test-model", 0, "teste"),
            {
                "request_id": "req-test",
                "tool": "calculator",
                "args": {"expression": "2+2"},
                "confirmation_token": "token-test",
                "expires_in": 120,
            },
        )

    main_mod.ask_with_cortex = confirm_cortex
    with TestClient(app) as client:
        headers = {"X-Doom-Key": "test-key"}
        response = client.post(
            "/api/chat",
            headers=headers,
            json={"session_id": "chat-test", "message": "use a calculadora"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["tool_confirmation"]["tool"] == "calculator"
        assert body["tool_confirmation"]["args"]["expression"] == "2+2"

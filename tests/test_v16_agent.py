from pathlib import Path
import os
import tempfile

_db = Path(tempfile.mkdtemp()) / "doom.db"
os.environ.update({
    "DOOM_API_KEY": "test-key",
    "DOOM_USER_NAME": "Renan",
    "DATABASE_URL": f"sqlite:///{_db}",
    "CORTEX_PROVIDERS": "ollama",
    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    "AGENT_ENABLED": "false",
    "AGENT_MAX_STEPS": "8",
    "AGENT_MAX_TOOL_CALLS": "5",
    "DEEP_SEARCH_ENABLED": "false",
})

from fastapi.testclient import TestClient
from app.main import app
from app import main as main_mod
from app import agent as agent_mod
from app.cortex import CortexRoute


def fake_plan(prompt: str, provider=None):
    return '{"steps":[{"id":"step-1","action":"tool","description":"Calcular a expressão.","tool":"calculator","args":{"expression":"6*7"}},{"id":"step-2","action":"checkpoint","description":"Verificar o resultado."}]}'


def fake_answer(*args, **kwargs):
    return "A tarefa foi concluída com o resultado calculado: 42."

agent_mod.ask_planner = fake_plan
agent_mod.ask_doom = fake_answer


def test_agent_toggle_and_run():
    with TestClient(app) as client:
        headers = {"X-Doom-Key": "test-key"}
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["version"] == "1.8.0"

        status = client.get("/api/agent", headers=headers)
        assert status.json()["enabled"] is False

        toggled = client.patch("/api/agent", headers=headers, json={"enabled": True})
        assert toggled.status_code == 200
        assert toggled.json()["enabled"] is True

        response = client.post(
            "/api/chat",
            headers=headers,
            json={"session_id": "agent-test", "message": "resolva 6*7", "agent": True, "deep_search": False},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["agent"] is True
        assert body["agent_status"] == "completed"
        assert body["agent_run_id"]
        assert "42" in body["reply"]
        assert body["brain"] == "doom-agent"

        run = client.get(f"/api/agent/runs/{body['agent_run_id']}", headers=headers)
        assert run.status_code == 200
        detail = run.json()
        assert detail["status"] == "completed"
        assert len(detail["steps"]) == 2
        assert detail["steps"][0]["status"] == "completed"

        runs = client.get("/api/agent/runs", headers=headers, params={"session_id": "agent-test"})
        assert runs.status_code == 200
        assert runs.json()[0]["run_id"] == body["agent_run_id"]

        # Keep global Agent disabled after the test.
        client.patch("/api/agent", headers=headers, json={"enabled": False})


def test_agent_confirmation_resume():
    from app.main import get_db, SessionLocal
    with SessionLocal() as db:
        from app.main import set_global_agent_enabled
        set_global_agent_enabled(db, True)
    from app.security import upsert_permission
    upsert_permission("calculator", "global", None, "confirm", True)
    with TestClient(app) as client:
        headers = {"X-Doom-Key": "test-key"}
        response = client.post(
            "/api/chat",
            headers=headers,
            json={"session_id": "agent-confirm", "message": "resolva 6*7", "agent": True, "deep_search": False},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["agent_status"] == "waiting_confirmation"
        assert body["tool_confirmation"]["agent_run_id"] == body["agent_run_id"]
        token = body["tool_confirmation"]["confirmation_token"]

        resumed = client.post(
            f"/api/agent/runs/{body['agent_run_id']}/resume",
            headers=headers,
            json={"session_id": "agent-confirm", "confirmation_token": token},
        )
        assert resumed.status_code == 200, resumed.text
        resumed_body = resumed.json()
        assert resumed_body["status"] == "completed"
        assert "42" in resumed_body["reply"]

    # restore default permission for later tests/environments
    from app.security import delete_permission
    delete_permission("calculator", "global", None)
    with SessionLocal() as db:
        from app.main import set_global_agent_enabled
        set_global_agent_enabled(db, False)

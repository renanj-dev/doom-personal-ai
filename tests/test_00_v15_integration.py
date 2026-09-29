from pathlib import Path
import os
import tempfile

_db = Path(tempfile.mkdtemp()) / "doom.db"
os.environ.update({
    "DOOM_API_KEY": "test-key",
    "DATABASE_URL": f"sqlite:///{_db}",
    "DEEP_SEARCH_ENABLED": "false",
    "DEEP_SEARCH_PROVIDER": "brave",
    "BRAVE_SEARCH_API_KEY": "test-search-key",
    "CORTEX_PROVIDERS": "ollama",
    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
})

from fastapi.testclient import TestClient
from app.main import app
from app.deep_search import DeepSearchResult, DeepSearchSource
import app.main as main_mod


class FakeDeepSearch:
    def __init__(self):
        self.enabled = True

    def available(self):
        return True

    def availability_detail(self):
        return "provider_ready"

    def research(self, query, session_id="main"):
        return DeepSearchResult(
            query=query,
            provider="brave",
            queries=(query, f"{query} informações oficiais"),
            sources=(DeepSearchSource(
                "Fonte de teste",
                "https://example.com/fonte",
                "Resumo de teste",
                "Conteúdo da fonte de teste.",
            ),),
        )


main_mod.DEEP_SEARCH_ENGINE = FakeDeepSearch()


def fake_cortex(**kwargs):
    assert kwargs["research_text"]
    assert "Conteúdo da fonte de teste" in kwargs["research_text"]
    from app.cortex import CortexRoute
    return "Resposta baseada nas fontes.", CortexRoute("analysis", "ANÁLISE / POSSIBILIDADES", "ollama", "test-model", 0, "teste")

main_mod.ask_with_cortex = fake_cortex


def test_startup_toggle_and_chat():
    with TestClient(app) as client:
        h = client.get("/health")
        assert h.status_code == 200
        assert h.json()["version"] == "1.5.0"

        s = client.get("/api/deep-search", headers={"X-Doom-Key": "test-key"})
        assert s.status_code == 200
        assert s.json()["enabled"] is False
        assert s.json()["available"] is True

        t = client.patch("/api/deep-search", headers={"X-Doom-Key": "test-key"}, json={"enabled": True})
        assert t.status_code == 200
        assert t.json()["enabled"] is True

        c = client.post(
            "/api/chat",
            headers={"X-Doom-Key": "test-key"},
            json={"session_id": "deep-test", "message": "Pesquise profundamente sobre teste"},
        )
        assert c.status_code == 200, c.text
        data = c.json()
        assert data["deep_search"] is True
        assert data["deep_search_query"] == "Pesquise profundamente sobre teste"
        assert data["deep_search_sources"][0]["url"] == "https://example.com/fonte"

        runs = client.get("/api/deep-search/runs", headers={"X-Doom-Key": "test-key"})
        assert runs.status_code == 200
        assert isinstance(runs.json(), list)

        off = client.patch("/api/deep-search", headers={"X-Doom-Key": "test-key"}, json={"enabled": False})
        assert off.status_code == 200
        assert off.json()["enabled"] is False

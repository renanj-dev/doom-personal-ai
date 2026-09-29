from pathlib import Path
import os
import tempfile

# Test imports before app initialization with a temporary SQLite database.
_db = Path(tempfile.mkdtemp()) / "doom_test.db"
os.environ["DOOM_API_KEY"] = "test-key"
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["DEEP_SEARCH_ENABLED"] = "false"
os.environ["BRAVE_SEARCH_API_KEY"] = "test-search-key"

from app.deep_search import DeepSearchEngine, SearchHit


def test_query_expansion_is_bounded():
    engine = DeepSearchEngine()
    queries = engine._queries("IA na medicina")
    assert queries[0] == "IA na medicina"
    assert len(queries) <= 4


def test_context_format():
    from app.deep_search import DeepSearchResult, DeepSearchSource
    result = DeepSearchResult(
        query="teste",
        provider="brave",
        queries=("teste",),
        sources=(DeepSearchSource("Título", "https://example.com", "Resumo", "Conteúdo"),),
    )
    assert "FONTE 1" in result.context
    assert "https://example.com" in result.context
    assert "Conteúdo" in result.context


def test_html_extraction():
    from app.deep_search import _TextExtractor
    parser = _TextExtractor()
    parser.feed("<html><head><title>Teste</title></head><body><nav>menu</nav><article><h1>Olá</h1><p>Texto principal.</p><script>ignore()</script></article></body></html>")
    assert parser.title == "Teste"
    assert "Texto principal." in parser.text
    assert "ignore" not in parser.text

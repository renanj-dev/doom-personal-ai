from __future__ import annotations

import ipaddress
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from .config import get_settings
from .db import SessionLocal
from .models import DeepSearchRun


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class DeepSearchSource:
    title: str
    url: str
    snippet: str
    content: str


@dataclass(frozen=True)
class DeepSearchResult:
    query: str
    provider: str
    queries: tuple[str, ...]
    sources: tuple[DeepSearchSource, ...]

    @property
    def context(self) -> str:
        if not self.sources:
            return "Nenhuma fonte foi recuperada."
        blocks: list[str] = []
        for i, src in enumerate(self.sources, 1):
            body = src.content.strip()[:12000]
            blocks.append(
                f"FONTE {i}\n"
                f"TÍTULO: {src.title}\n"
                f"URL: {src.url}\n"
                f"RESUMO DA BUSCA: {src.snippet}\n"
                f"CONTEÚDO EXTRAÍDO:\n{body}"
            )
        return "\n\n---\n\n".join(blocks)


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "p", "div", "article", "section", "li", "h1", "h2", "h3",
        "h4", "h5", "h6", "br", "tr",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "header", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        elif tag == "title":
            self.in_title = True
        elif self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "title":
            self.in_title = False
        elif self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        else:
            self.parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        text = " ".join(x.strip() for x in self.parts if x.strip())
        return re.sub(r"\s+", " ", text).strip()


def _domain_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.port not in (None, 80, 443):
            return False
        hostname = parsed.hostname.strip(".").lower()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local") or hostname.endswith(".internal"):
            return False
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return True
        return address.is_global
    except Exception:
        return False


def _normalize_url(url: str) -> str:
    return url.split("#", 1)[0].strip()


class DeepSearchEngine:
    def __init__(self):
        self.settings = get_settings()

    def available(self) -> bool:
        provider = self.settings.deep_search_provider.strip().lower()
        if provider == "brave":
            return bool(self.settings.brave_search_api_key)
        return False

    def availability_detail(self) -> str:
        provider = self.settings.deep_search_provider.strip().lower()
        if provider == "brave" and self.settings.brave_search_api_key:
            return "provider_ready"
        if provider == "brave":
            return "BRAVE_SEARCH_API_KEY não configurada."
        return f"Provedor de Deep Search não suportado: {provider}."

    def _search(self, query: str, count: int) -> list[SearchHit]:
        provider = self.settings.deep_search_provider.strip().lower()
        if provider != "brave":
            raise RuntimeError(self.availability_detail())
        if not self.settings.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY não configurada.")

        params = {
            "q": query[:600],
            "count": max(1, min(count, 20)),
            "country": self.settings.deep_search_country,
            "search_lang": self.settings.deep_search_lang,
            "safesearch": "moderate",
        }
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.settings.brave_search_api_key,
        }
        with httpx.Client(timeout=self.settings.deep_search_fetch_timeout, follow_redirects=True) as client:
            response = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        results: list[SearchHit] = []
        for item in (data.get("web", {}).get("results", []) or []):
            url = _normalize_url(str(item.get("url", "")))
            if not _domain_allowed(url):
                continue
            title = str(item.get("title", "")).strip() or url
            snippet = str(item.get("description", "")).strip()
            results.append(SearchHit(title, url, snippet))
        return results

    def _queries(self, query: str) -> list[str]:
        clean = query.strip()
        candidates = [
            clean,
            f"{clean} informações oficiais",
            f"{clean} pesquisa estudos",
            f"{clean} atualizações recentes",
        ]
        seen: list[str] = []
        for item in candidates:
            if item and item not in seen:
                seen.append(item)
        return seen[: max(1, self.settings.deep_search_max_queries)]

    def _fetch(self, hit: SearchHit) -> DeepSearchSource | None:
        headers = {
            "User-Agent": "Doom-Deep-Search/1.5",
            "Accept": "text/html,application/xhtml+xml",
        }
        try:
            with httpx.Client(
                timeout=self.settings.deep_search_fetch_timeout,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = client.get(hit.url)
                response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return DeepSearchSource(hit.title, hit.url, hit.snippet, hit.snippet)

            parser = _TextExtractor()
            parser.feed(response.text[:900_000])
            content = parser.text[: self.settings.deep_search_max_page_chars]
            title = parser.title or hit.title
            if len(content) < 80:
                content = hit.snippet
            return DeepSearchSource(title, hit.url, hit.snippet, content)
        except Exception:
            return None

    def research(self, query: str, session_id: str = "main") -> DeepSearchResult:
        started = time.perf_counter()
        query = query.strip()
        if not query:
            raise ValueError("A consulta de Deep Search não pode ficar vazia.")
        if len(query) > 600:
            query = query[:600]
        if not self.available():
            raise RuntimeError(self.availability_detail())

        search_queries = self._queries(query)
        collected: dict[str, SearchHit] = {}
        try:
            per_query = max(1, self.settings.deep_search_max_results)
            for subquery in search_queries:
                for hit in self._search(subquery, per_query):
                    if hit.url not in collected:
                        collected[hit.url] = hit
                    if len(collected) >= per_query * 2:
                        break
                if len(collected) >= per_query * 2:
                    break

            sources: list[DeepSearchSource] = []
            for hit in collected.values():
                source = self._fetch(hit)
                if source:
                    sources.append(source)
                if len(sources) >= max(1, self.settings.deep_search_max_sources):
                    break

            result = DeepSearchResult(
                query=query,
                provider=self.settings.deep_search_provider,
                queries=tuple(search_queries),
                sources=tuple(sources),
            )
            self._audit(
                session_id,
                query,
                "completed",
                len(search_queries),
                len(sources),
                int((time.perf_counter() - started) * 1000),
                "",
            )
            return result
        except Exception as exc:
            self._audit(
                session_id,
                query,
                "error",
                len(search_queries),
                0,
                int((time.perf_counter() - started) * 1000),
                str(exc)[:2000],
            )
            raise

    @staticmethod
    def _audit(session_id, query, status, query_count, source_count, duration_ms, error):
        try:
            with SessionLocal() as db:
                db.add(
                    DeepSearchRun(
                        session_id=session_id,
                        query=query,
                        provider=settings.deep_search_provider,
                        status=status,
                        query_count=query_count,
                        source_count=source_count,
                        duration_ms=duration_ms,
                        error=error,
                    )
                )
                db.commit()
        except Exception:
            # Search results remain usable if audit persistence is temporarily unavailable.
            pass


DEEP_SEARCH_ENGINE = DeepSearchEngine()

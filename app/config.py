from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    doom_api_key: str
    doom_user_name: str = "Renan"

    # Legacy/default provider setting. Cortex uses cortex_providers when configured.
    llm_provider: str = "openrouter"

    # Legacy/default model setting. Provider-specific models below are preferred by Cortex.
    doom_model: str = "openrouter/free"

    # Doom Cortex: comma-separated provider priority pool.
    cortex_providers: str = "openrouter"

    # Local Ollama settings.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:0.6b"

    # OpenAI settings.
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"

    # OpenRouter settings.
    openrouter_api_key: str | None = None
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str | None = None
    openrouter_site_name: str = "Doom Personal AI"

    # Local testing: SQLite. Cloud: PostgreSQL (Neon, Supabase, etc.).
    database_url: str = "sqlite:///./data/doom.db"

    # Optional CORS. Comma separated origins. For the built-in web UI, leave blank.
    cors_origins: str = ""

    # Seed the curated initial memory on startup when set to true.
    seed_memories: bool = False

    # Doom Deep Search v1.5. Global default can be overridden per chat request.
    deep_search_enabled: bool = False
    deep_search_provider: str = "brave"
    brave_search_api_key: str | None = None
    deep_search_country: str = "BR"
    deep_search_lang: str = "pt-br"
    deep_search_max_results: int = 6
    deep_search_max_sources: int = 4
    deep_search_max_queries: int = 4
    deep_search_fetch_timeout: float = 12.0
    deep_search_max_page_chars: int = 12000

    # Doom Planner / Agent v1.6
    agent_enabled: bool = False
    agent_max_steps: int = 8
    agent_max_tool_calls: int = 5

    # Doom Security + Identity v1.7
    security_session_hours: int = 12
    security_legacy_api_key: bool = True

    # Doom Safety & Legal Engine v1.8
    safety_enabled: bool = True
    safety_jurisdiction: str = "BR"
    emergency_break_glass_enabled: bool = True
    emergency_session_minutes: int = 5
    emergency_max_attempts: int = 5
    emergency_cooldown_minutes: int = 10
    emergency_require_reason: bool = True

    # Doom External Integrations v1.9
    integrations_enabled: bool = True
    integrations_allow_private: bool = False
    integrations_default_timeout: float = 10.0
    integrations_max_body_chars: int = 12000
    integrations_max_response_chars: int = 12000

    # Doom Knowledge Engine v1.10
    knowledge_engine_enabled: bool = True
    knowledge_max_file_mb: int = 12
    knowledge_max_context_chars: int = 18000

    # Doom Tool Engine 2.0
    tool_timeout_seconds: float = 8.0
    tool_max_retries: int = 1
    tool_max_batch: int = 5

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def provider(self) -> str:
        return self.llm_provider.strip().lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()

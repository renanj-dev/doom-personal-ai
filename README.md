# Doom Personal AI v1.2

Doom is a personal AI assistant project with its own identity, personality, curated user profile, persistent memory, web UI and switchable model providers.

## Providers

- `ollama` — local/offline brain
- `openrouter` — cloud brain, recommended for the free cloud prototype
- `openai` — OpenAI API

## Local quick start

Copy `.env.example` to `.env`, set `LLM_PROVIDER=ollama`, use `DOOM_MODEL=qwen3:0.6b`, create `data/`, then run `scripts/local_run.ps1`.

## Cloud prototype

See `README_CLOUD.md` and `render.yaml` for the Render + Neon + OpenRouter deployment path.

## Visual Codex Forest Core

A interface usa o sistema semântico de estados documentado em `DOOM_CODEX.md`.


## Doom Cortex v1.0

Doom now uses a routing layer that selects among configured AI providers and can fall back when a provider fails. See `DOOM_CORTEX.md`.


## Memory Engine v1.1

Doom now separates conversation history from persistent memory and current context. Conversations can be created, resumed, searched, archived, and deleted through the Memory Engine.

See `DOOM_MEMORY_ENGINE.md` for the data model and API.


## Memory Intelligence v1.2

Doom now supports explicit memory proposals, confirmation-based persistence, relevance-ranked memory context, memory search, and memory management from the web UI.

See `DOOM_MEMORY_ENGINE.md` for details.

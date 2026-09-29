# Doom Personal AI v1.5.0

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

## Context Engine v1.3

Doom v1.3 introduces a dedicated Context Engine that builds a focused context for each request:

```text
Current request
    ↓
Recent conversation
    + relevant historical recall
    + relevant persistent memories
    + focused user profile
    ↓
Doom Cortex
    ↓
Selected AI provider
```

This first semantic layer is deterministic and dependency-free. It can later be replaced by embeddings/vector search without changing the Cortex or Doom UI contracts.

The Command Center exposes context telemetry so the user can see how much recent history, recalled history, and persistent memory were included in a request.


## Doom v1.4.5 — Core Integration

This release consolidates the Tool Engine, Security & Permissions, persistent Tool Audit, manual history deletion, and reliable persistent memory editing into the Doom server itself. See `DOOM_V1_4_4.md`.


## Doom v1.4.5

The v1.4.5 release consolidates tools, permissions, audit, manual history deletion, and reliable memory editing directly into the Doom Cloud core. See `DOOM_V1_4_4.md`.


### v1.4.5 — DB migration hotfix
Compatibilidade com bancos existentes da v1.3: o startup aplica as mudanças aditivas necessárias na tabela `memories` antes das consultas da Memory Engine.


## Doom v1.5 — Deep Search
Deep Search é um modo opcional, desligado por padrão. Quando ativado, o Core executa pesquisas em múltiplas consultas, recupera fontes e entrega o material ao Cortex para síntese. As fontes recuperadas também aparecem na interface.

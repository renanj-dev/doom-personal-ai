# Doom Personal AI v1.8.1

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


## Doom v1.4.6 — Memory UI hotfix

Corrige a camada de interação da gaveta de Memória para manter o painel acima do backdrop e preservar cliques e rolagem.


### v1.4.5 — DB migration hotfix
Compatibilidade com bancos existentes da v1.3: o startup aplica as mudanças aditivas necessárias na tabela `memories` antes das consultas da Memory Engine.


## Doom v1.5 — Deep Search
Deep Search é um modo opcional, desligado por padrão. Quando ativado, o Core executa pesquisas em múltiplas consultas, recupera fontes e entrega o material ao Cortex para síntese. As fontes recuperadas também aparecem na interface.


## v1.5.1 — Tool Engine 2.0
A camada de ferramentas foi evoluída com catálogo estruturado, validação de argumentos, permissões persistentes (global/usuário/sessão), confirmação interativa, execução em lote limitada, timeout/retry controlados e auditoria com request_id.

Endpoints principais: `GET /api/tools`, `GET /api/tools/permissions`, `PUT /api/tools/permissions`, `DELETE /api/tools/permissions/{tool_name}`, `POST /api/tools/execute`, `POST /api/tools/execute-batch` e `GET /api/audit/tools`.


## Doom v1.7.0 — Planner / Agent
O Agent é um modo opcional do Core, desligado por padrão. Ele transforma uma tarefa em um plano estruturado de até 8 etapas, executa somente ferramentas presentes no catálogo sob as políticas do Tool Engine, pode coordenar Deep Search quando habilitado e registra cada execução no banco.

Endpoints principais: `GET /api/agent`, `PATCH /api/agent`, `GET /api/agent/runs`, `GET /api/agent/runs/{run_id}` e `POST /api/agent/runs/{run_id}/resume`.


## v1.7.0 — Security + Identity
- identidade persistente do proprietário Doom;
- API keys registradas somente por hash;
- sessões autenticadas com cookie HttpOnly e expiração configurável;
- suporte a Bearer token para clientes externos;
- logout e revogação de todas as sessões;
- endpoint de identidade e listagem de sessões;
- compatibilidade temporária com `X-Doom-Key`;
- registro sem armazenar tokens de sessão em texto.


## Doom v1.7.0 — Security + Identity

A v1.7 adiciona a fundação de identidade e sessão do Core:
- identidade persistente do proprietário;
- registro das API keys somente por hash;
- sessões com cookie HttpOnly e expiração configurável;
- autenticação por Bearer token para clientes externos;
- logout e revogação de sessões;
- painel de identidade no Command Center;
- compatibilidade temporária com `X-Doom-Key`.

A v1.7 ainda opera em modo single-user. O isolamento completo de dados por múltiplos usuários será tratado em uma etapa posterior.


## Doom v1.8.0 — Safety & Legal

A v1.8 adiciona uma camada determinística de Safety & Legal e o Emergency Override / Break Glass com autorização temporária, uso único, motivo obrigatório, auditoria e bloqueios absolutos não ignoráveis. Para registrar a chave via PowerShell: `python scripts\register_emergency_key.py`.


## v1.8.1 — Interromper raciocínio
A interface possui um botão **Interromper** durante uma solicitação. O browser cancela a espera imediatamente e envia um sinal de cancelamento ao Core, que evita persistir uma resposta final depois da interrupção e permite ao Agent parar entre etapas. Como os provedores ainda usam chamadas não-streaming, uma chamada externa que já esteja em andamento pode terminar internamente; o resultado é descartado.

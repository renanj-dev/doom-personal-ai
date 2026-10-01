# Changelog

## 1.9.0 — External Integrations
- Adicionado `ExternalIntegration` e `IntegrationEngine`.
- Adicionada ferramenta `external_http` no Tool Engine 2.0.
- Adicionadas rotas de registry, habilitação/desabilitação, teste e remoção.
- Adicionadas políticas contra SSRF, redirects, URLs arbitrárias e segredos em banco.

## 1.8.2 — Context Isolation
- Current user request is explicitly appended as the final user turn for Cortex calls.
- Historical cross-conversation recall now uses only user-authored messages.
- Unrelated memories are no longer inserted merely because they are recent.
- Greetings, self-introduction and direct memory questions use an isolated recent-turn window.
- Added context-priority system rules to prevent old answers from overriding the current request.
# Changelog

## 1.8.1 — Interrupt Control

- Added per-request cancellation registry and request IDs.
- Added `POST /api/chat/cancel`.
- Added cooperative cancellation checks before/after expensive orchestration stages.
- Agent can stop between plan steps and records `cancelled`.
- Added UI button `Interromper` with AbortController + server cancel signal.
- Added `INTERROMPIDO` semantic state to Forest Core.
- Documented limitation: non-streaming provider calls already in flight may still finish internally, but their result is not committed to the conversation.


## 1.8.0 — Safety & Legal + Emergency Override

- Adicionado Safety & Legal Engine.
- Adicionados níveis `allow`, `review`, `break_glass` e `blocked`.
- Adicionado Emergency Override / Break Glass com hash PBKDF2, expiração, uso único, vínculo de sessão, motivo obrigatório, tentativas e cooldown.
- Bloqueios absolutos permanecem não ignoráveis.
- Adicionada auditoria persistente de eventos de segurança.
- Adicionados endpoints e painel visual de Safety & Legal.


## 1.7.0 — Security + Identity
- Added persistent Doom owner identity.
- Added hashed API-key registry.
- Added expiring HttpOnly session cookies.
- Added Bearer session authentication for external clients.
- Added logout and revoke-all session controls.
- Added identity/session endpoints and UI drawer.
- Kept `X-Doom-Key` as a compatibility path during migration.

# CHANGELOG

## v1.7.0 — Security + Identity
- identidade persistente do proprietário Doom;
- API keys registradas somente por hash;
- sessões autenticadas com expiração configurável;
- cookie HttpOnly para o navegador e Bearer token para clientes externos;
- logout e revogação de sessões;
- painel de identidade no Command Center;
- compatibilidade temporária com `X-Doom-Key`.

## v1.6.0 — Planner / Agent
- modo Agent global ON/OFF e override por requisição;
- planejamento estruturado em JSON com limites de etapas e ferramentas;
- execução sequencial de ferramentas e coordenação opcional do Deep Search;
- confirmação integrada ao Agent e retomada após autorização;
- persistência de AgentRun/AgentStep e endpoints de inspeção;
- síntese final baseada nos resultados das etapas;
- interface com botão e telemetria próprias para o Agent;
- Agent desligado por padrão.

## v1.5.0 — Deep Search Engine
- Deep Search global ON/OFF com persistência em `system_settings`.
- Pesquisa em múltiplas consultas derivadas.
- Busca web estruturada e recuperação das páginas das fontes.
- Até 4 fontes são passadas ao Cortex como contexto de pesquisa.
- Fontes recuperadas são exibidas na interface.
- Auditoria das execuções em `deep_search_runs`.
- Deep Search permanece desligado por padrão.

v1.5.0

- Corrigida a camada visual da aba Memória: o drawer agora fica acima do backdrop e recebe cliques/rolagem normalmente.
- Ao abrir Memória, o Histórico é fechado para evitar sobreposição de overlays.

# Changelog

## v1.5.1 — Tool Engine 2.0

- catálogo de ferramentas estruturado e dinâmico no protocolo do Cortex;
- validação de argumentos antes da execução;
- request_id e métricas básicas por execução;
- timeout e retries controlados;
- execução em lote limitada e interrompida diante de falhas/confirmações;
- permissões persistentes por escopo global, usuário e sessão;
- confirmação interativa com token único e validade de 120s;
- painel de ferramentas na UI;
- auditoria das etapas do Tool Engine;
- preservação das ferramentas já existentes da v1.4.x e do Deep Search da v1.5.0.



## 1.4.5
- Correção de migração incremental do PostgreSQL/SQLite para bancos existentes da v1.3.
- `memories.updated_at` e `memories.revision` agora são adicionados automaticamente sem apagar dados.


## v1.4.4 — Core Integration


- integrated Tool Engine into the actual Doom server;
- added persistent tool permissions and confirmations;
- added persistent tool audit;
- added manual conversation deletion in the UI;
- added reliable memory PATCH editing with revision control;
- added additive migration for v1.3 memory rows;
- updated server version to 1.4.4.


## v1.3.0 — Doom Context Engine

- Added a dedicated Context Engine between Memory and Cortex.
- Uses 12 recent messages plus up to 8 relevant recalled messages.
- Supports cross-conversation lexical recall in the first semantic layer.
- Uses up to 8 relevant persistent memories.
- Uses a focused user profile for normal requests to reduce unnecessary context.
- Added context telemetry to chat responses and the Command Center.
- Added authenticated `/api/context/preview` for diagnostics.
- Kept profile/identity questions deterministic to avoid Doom/Renan identity confusion.
- Updated the project documentation and UI version markers to v1.3.

# CHANGELOG

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

# Doom Cloud v1.5.0 — Deep Search Engine

A v1.5 adiciona um modo de pesquisa profunda ativável/desativável.

## Componentes
- `app/deep_search.py`: planejamento simples de subconsultas, busca estruturada, recuperação de páginas e extração textual.
- `app/main.py`: estado global, toggle, histórico de execuções e integração com chat.
- `app/llm.py`: bloco de contexto de pesquisa e instrução para uso das fontes.
- `app/static/doom-state.js`: toggle e apresentação das fontes.
- `app/static/doom.css`: estado visual Deep Search.

## Configuração
`DEEP_SEARCH_ENABLED=false` mantém o recurso desligado por padrão.
`BRAVE_SEARCH_API_KEY` habilita o provedor de busca configurado em `DEEP_SEARCH_PROVIDER`.

## Fluxo
1. Usuário ativa Deep Search.
2. A mensagem pode usar o estado global ou sobrescrever o modo por requisição via `deep_search`.
3. O Engine gera consultas derivadas.
4. Busca resultados e recupera páginas.
5. As fontes são passadas ao Cortex como contexto.
6. A resposta é exibida com as fontes recuperadas.

## Auditoria
Execuções são persistidas em `deep_search_runs`, sem armazenar o conteúdo integral das páginas.

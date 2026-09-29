### Hotfix v1.4.6

Correção de interação da interface da aba Memória (z-index/backdrop) e sincronização de versão.

# Doom v1.4.4 — Core Integration

Esta é a atualização consolidada sobre o **Doom Cloud v1.3 enviado por Renan**.

## Incluído

- Tool Engine integrado ao servidor real.
- Cortex capaz de interpretar pedidos de ferramenta em JSON estrito.
- Execução limitada ao catálogo de ferramentas registradas.
- Security & Permissions aplicado antes da execução.
- Tokens de confirmação para ferramentas `confirm`.
- Tool Audit persistente no banco.
- `GET /api/tools` e `POST /api/tools/execute`.
- `GET /api/audit/tools`.
- Exclusão manual de históricos no frontend e API.
- Edição persistente de memórias via `PATCH /api/memories/{memory_id}`.
- Revisão de memória (`revision`) para evitar sobrescrita silenciosa.
- Migração aditiva de `memories` para instalações criadas na v1.3.
- Command Center e Forest Core preservados.

## Operações manuais

### Excluir histórico
No painel **Histórico**, use `Excluir` em uma conversa. A operação remove a conversa e suas mensagens. Memórias permanentes ficam intactas.

### Editar memória
No painel **Memória**, use `Editar`. O servidor valida e grava a alteração; o frontend usa o retorno canônico do servidor e a revisão atualizada.

## Segurança

A v1.4.5 não habilita shell livre, PowerShell, subprocess ou execução arbitrária de código. As ferramentas iniciais são `calculator`, `current_time` e `system_info`.


## Hotfix 1.4.5
Correção da migração incremental da tabela `memories` para instalações que já possuíam o banco da v1.3.

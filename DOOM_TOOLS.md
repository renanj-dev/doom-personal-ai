# Doom Tools v1.4

## Objetivo

O Tool Engine é a camada entre o Cortex e ações externas. A Doom não deve conceder acesso irrestrito ao sistema operacional só porque um modelo pediu uma ferramenta.

## Permissões

- `safe`: pode executar sem confirmação.
- `confirm`: cria um token de confirmação; só executa após confirmação explícita do usuário.
- `blocked`: não pode ser executada pelo Engine.

## Ferramentas iniciais

| Ferramenta | Permissão | Função |
|---|---|---|
| `calculator` | safe | cálculo matemático seguro |
| `current_time` | safe | horário UTC do servidor |
| `system_info` | safe | informações básicas do ambiente |

## Auditoria

Cada tentativa gera um `AuditEvent` com timestamp, ferramenta, ação, permissão, sessão e resultado. O próximo passo é persistir esses eventos no banco da Doom.

## Confirmação

Uma ferramenta `confirm` nunca é executada na primeira chamada. O Engine devolve um `confirmation_token`. Esse token é único e fica associado à sessão, nome e argumentos exatos da solicitação.

## Não existe shell livre

A v1.4 deliberadamente não implementa `subprocess`, shell, PowerShell, execução de código arbitrário ou acesso irrestrito a arquivos. Ferramentas de alto impacto só entram depois que houver sandbox, escopo e confirmação bem definidos.

## Integração futura

```text
Usuário
  ↓
Doom Core
  ↓
Context Engine
  ↓
Cortex
  ├── cérebro
  └── Tool Engine
        ↓
   política de permissão
        ↓
   ferramenta
        ↓
   auditoria
```

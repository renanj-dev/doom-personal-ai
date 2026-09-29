# Doom Cloud v1.5.1 — Tool Engine 2.0

## Objetivo
Evoluir o Tool Engine da v1.4.x para uma camada operacional estruturada, com validação, permissões persistentes, confirmação interativa, execução controlada e auditoria.

## Componentes
- catálogo dinâmico consumido pelo protocolo do Cortex;
- validação de tipos, obrigatoriedade, tamanho e parâmetros desconhecidos;
- request_id, duração e tentativa em cada execução;
- timeout e retry com limites globais;
- execução em lote com máximo configurável;
- permissões global, usuário e sessão;
- confirmação de uso único, vinculada à sessão, usuário, ferramenta e argumentos;
- painel web para escolher Seguro, Confirmar ou Bloqueado;
- confirmação clicável dentro do chat;
- auditoria sem registrar tokens de confirmação.

## Segurança
As ferramentas continuam sendo uma allowlist explícita. A v1.5.1 não adiciona shell livre, PowerShell, subprocess ou execução arbitrária de código.

## Ferramentas atuais
- `calculator`
- `current_time`
- `system_info`

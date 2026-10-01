# DOOM v1.9 — External Integrations

A v1.9 transforma o Tool Engine em uma camada segura para serviços externos previamente cadastrados.

## O que entrou
- Registry persistente de integrações externas.
- Tipo inicial `http_json`.
- URL base validada e host resolvido antes da chamada.
- Allowlist de caminhos e métodos por integração.
- HTTP sem TLS bloqueado por padrão para hosts não locais.
- Redes privadas/locais bloqueadas por padrão (`INTEGRATIONS_ALLOW_PRIVATE=false`).
- Segredos ficam fora do banco: o Doom recebe apenas o nome de uma variável de ambiente.
- Redirecionamentos HTTP não são seguidos automaticamente.
- Limites para body, resposta e timeout.
- Ferramenta `external_http`, com `CONFIRM` por padrão.
- Endpoints para listar, cadastrar, habilitar/desabilitar, testar e remover integrações.

## Exemplo de integração
Registre uma integração `meu-servico` com:
- base URL: `https://api.exemplo.com/`
- paths: `/v1`
- methods: `GET,POST`
- auth env var: `MEU_SERVICO_TOKEN`
- auth header: `Authorization`

No ambiente do servidor, configure `MEU_SERVICO_TOKEN` com o valor completo do header.

## Limites da v1.9
Ainda não existe um Plugin Engine genérico, OAuth interativo, adapters nativos de aplicativos ou catálogo de MCP. Essas capacidades ficam para uma etapa posterior de Custom Tool / Plugin Engine / Tool Hub.

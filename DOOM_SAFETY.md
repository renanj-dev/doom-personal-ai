# Doom Safety & Legal Engine v1.8

O v1.8 introduz uma camada de política determinística antes do Cortex. Ela separa pedidos em quatro estados:

- `allow`: fluxo normal;
- `review`: tema de alto impacto, com resposta cuidadosa;
- `break_glass`: pedido restrito que pode receber autorização temporária e limitada;
- `blocked`: bloqueio absoluto que não pode ser removido pelo Emergency Override.

O mecanismo é deliberadamente conservador e não é um motor jurídico completo. `SAFETY_JURISDICTION` identifica a jurisdição de referência, mas não substitui aconselhamento jurídico profissional nem atualizações legislativas.

## Break Glass

O Emergency Override é um mecanismo de **autorização limitada**, não um desligamento global de segurança.

Proteções principais:

- chave gerada aleatoriamente;
- Doom armazena somente hash PBKDF2 + salt;
- autorização vinculada à sessão;
- token temporário com expiração padrão de 5 minutos;
- motivo obrigatório;
- limite de tentativas com cooldown;
- token de uso único;
- revogação global;
- eventos persistentes de auditoria;
- `hard blocks` permanecem bloqueados.

## Fluxo

```text
Solicitação
    ↓
Safety & Legal Engine
    ├── ALLOW → Cortex
    ├── REVIEW → Cortex + contexto de cautela
    ├── BREAK_GLASS → pedir autorização temporária
    └── BLOCKED → recusar sem consultar o modelo
```

Após a autorização, o cliente envia o `X-Doom-Emergency-Grant` apenas para a nova tentativa daquela sessão. O grant é consumido uma única vez.

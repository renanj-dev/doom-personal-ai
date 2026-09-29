# Doom v1.4.4 — History & Memory Management

Esta versão corrige o gerenciamento manual que faltava/estava inconsistente em duas áreas:

1. **Histórico:** exclusão manual de uma conversa pelo `session_id`, removendo a conversa e suas mensagens em uma única transação.
2. **Memória:** edição persistente do registro de memória, com validação, retorno do estado efetivamente salvo e controle de revisão para impedir que uma edição antiga sobrescreva uma alteração mais recente.

## Regra de separação

Excluir um histórico **não exclui memórias persistentes**.
Editar uma memória **não modifica o histórico da conversa**.

```text
Histórico
  conversations
       └── messages

Memória persistente
  memories
```

## Segurança v1.4.3

As mutações passam por uma função `authorize(...)` opcional. No Doom completo, conecte essa função ao:

```python
SecureToolGate.authorize
```

Use os identificadores:

- `history_delete`
- `memory_edit`

Recomendação de padrão: `CONFIRM`.

## API

O `router.py` oferece um adaptador FastAPI:

- `GET /api/conversations`
- `DELETE /api/conversations/{session_id}`
- `GET /api/memories`
- `PATCH /api/memories/{memory_id}?session_id=<id>`

Na edição de memória, envie apenas os campos que deseja alterar:

```json
{
  "content": "Novo conteúdo",
  "category": "project",
  "enabled": true,
  "expected_revision": 3,
  "confirmation_token": "..."
}
```

`expected_revision` é opcional, mas o frontend do Doom deve enviá-lo. Assim, se a memória já tiver sido alterada em outro lugar, o backend responde `409` em vez de sobrescrever a mudança.

## Correção do bug de edição

O frontend não deve considerar uma edição concluída apenas porque o texto mudou localmente. O fluxo correto é:

```text
abrir memória
   ↓
editar no formulário
   ↓
PATCH /api/memories/{id}
   ↓
backend valida + grava + incrementa revision
   ↓
backend devolve memória salva
   ↓
frontend substitui o objeto local pelo retorno do backend
```

Isso elimina o estado visual "editado" que não foi persistido no banco. Para confirmações do v1.4.3, o conteúdo é representado por SHA-256 no material de autorização; o texto da memória não entra no log de auditoria.

## Testes

```bash
python -m unittest -v test_memory_history.py
```

O conjunto cobre:

- exclusão de conversa + mensagens;
- independência entre histórico e memória;
- persistência da edição;
- rejeição de conteúdo vazio;
- conflito de revisão;
- autorização via v1.4.3;
- auditoria sem gravar o conteúdo da memória.

O módulo não adiciona shell, PowerShell, subprocess ou execução arbitrária.

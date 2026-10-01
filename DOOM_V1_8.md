# Doom Cloud v1.8.2 — Context Isolation + Safety & Legal + Emergency Override + Interrupt Control

## Entregue

- Safety & Legal Engine determinístico com quatro decisões: `allow`, `review`, `break_glass`, `blocked`.
- Bloqueios absolutos não podem ser liberados pelo Emergency Override.
- Emergency Override / Break Glass com chave aleatória, armazenamento somente por hash PBKDF2 + salt, autorização temporária, vinculada à sessão, de uso único e com motivo obrigatório.
- Limite de tentativas e cooldown para autenticação da chave.
- Revogação de autorizações.
- Auditoria persistente em `safety_events`.
- API e painel visual de Safety & Legal.
- Integração do Safety Engine antes do Cortex/Agent.

## Registro da chave

No Windows/PowerShell, a partir da raiz do projeto:

```powershell
python scripts\register_emergency_key.py
```

A chave aparece uma única vez. Não coloque a chave em código, Git, README ou `.env` versionado.

## Uso

1. Abra `⚿ Safety & Legal`.
2. Registre a Emergency Override ou use o script acima.
3. Informe a chave e o motivo quando uma solicitação for classificada como `break_glass`.
4. A autorização dura o período configurado e pode ser usada uma única vez.
5. Reenvie a solicitação original.

## Limite de segurança

O Break Glass não é um bypass universal. Solicitações classificadas como `blocked` permanecem bloqueadas.

## v1.8.1 — Interrupt Control

A interface now exposes an **Interromper** button during active chat requests. Each request receives a request_id and the server maintains a cooperative cancellation registry. Cancelling marks the request immediately; the browser aborts its waiting fetch and the backend checks the cancellation between orchestration stages and Agent steps before committing a final response.

Important: provider calls in this version remain non-streaming. Therefore a provider network call already in progress may still finish internally; the user-facing request is nevertheless interrupted immediately and its result is discarded.

## v1.8.2 — Context Isolation
The Context Engine now separates the current request from historical support context, excludes recalled assistant answers, removes irrelevant memory backfill, and uses smaller context windows for greetings/identity/memory queries.

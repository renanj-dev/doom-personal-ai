# Doom Cloud v1.7.0 — Security + Identity

A v1.7 adiciona a fundação de identidade e sessão do Core.

## Componentes
- `app/identity.py`: Identity Engine, API-key registry, session issuance and revocation.
- `doom_users`: persistent Doom owner identity.
- `doom_api_keys`: hashed API key registry.
- `doom_sessions`: hashed expiring sessions.
- FastAPI accepts HttpOnly cookie, Bearer session token, or legacy `X-Doom-Key`.

## Sessão
- duração padrão: 12 horas (`SECURITY_SESSION_HOURS`);
- token armazenado somente por hash no banco;
- cookie `HttpOnly`, `SameSite=Lax`, `Secure` em HTTPS;
- logout revoga a sessão atual;
- revoke-all revoga as sessões do usuário.

## Segurança
A v1.7 é uma camada de fundação single-user. Os dados existentes continuam no espaço do proprietário configurado em `DOOM_USER_NAME`. Isolamento completo de dados para múltiplos usuários é uma etapa posterior.

## Compatibilidade
`X-Doom-Key` continua habilitado por padrão para evitar quebra das integrações atuais. Depois que o novo cliente estiver migrado para sessões, a opção `SECURITY_LEGACY_API_KEY=false` pode ser adotada.

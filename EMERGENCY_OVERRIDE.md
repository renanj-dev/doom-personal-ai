# Registro do Emergency Override / Break Glass

## Método recomendado — Windows / PowerShell

Abra o PowerShell na pasta do Doom:

```powershell
cd C:\Users\Renan\Downloads\doom_server\
```

> Use a pasta real onde o seu projeto estiver instalado. O comando abaixo precisa ser executado na raiz que contém `app` e `scripts`.

Execute:

```powershell
python scripts\register_emergency_key.py
```

O Doom pedirá um nome para a credencial. Pressione Enter para usar o padrão `Emergency Override`.

Em seguida, será mostrada uma chave semelhante a:

```text
DOOM-EG-<valor-longo>
```

### 1. Copie a chave imediatamente

Essa é a única vez em que a chave original será mostrada pelo comando.

### 2. Guarde a chave fora do projeto

Não coloque a chave em `README`, Git, screenshots públicas, `.env` versionado ou código-fonte.

### 3. Confirme o registro

Abra o Doom e entre em **Safety & Legal → Break Glass**. O painel deve mostrar `REGISTRADO`.

### 4. Autorize uma emergência controlada

No painel, informe:

- a chave Emergency Override;
- o motivo;

e clique em **Autorizar por 5 minutos**.

O Doom devolverá um token temporário. A próxima solicitação restrita da sessão poderá usar esse token.

### 5. Depois do uso

O token é consumido uma vez. Também existe a opção **Revogar todas as autorizações** para invalidar grants ativos.

## API

Status:

```http
GET /api/safety/status
X-Doom-Key: <chave normal do Doom>
```

Registrar nova chave:

```http
POST /api/safety/break-glass/register
X-Doom-Key: <chave normal do Doom>
```

Autorizar:

```http
POST /api/safety/break-glass/authorize
X-Doom-Key: <chave normal do Doom>
Content-Type: application/json
```

Exemplo de corpo:

```json
{
  "session_id": "main",
  "key": "DOOM-EG-...",
  "reason": "Motivo da emergência",
  "scope": "chat-restricted"
}
```

## Regras de segurança

O Emergency Override não remove bloqueios absolutos. Ele existe para permitir uma autorização limitada em situações que exigem revisão adicional, mantendo expiração, escopo, auditoria e revogação.

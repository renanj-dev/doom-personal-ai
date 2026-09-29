# Doom v1.4.3 — Security & Permissions Engine

This module adds persistent authorization rules in front of the existing Tool Engine.
It does **not** execute tools and does **not** add shell, PowerShell, subprocess,
arbitrary code execution, or unrestricted filesystem access.

## Flow

```text
Cortex / Tool request
        ↓
Security & Permissions Engine
        ↓
ALLOW ───────────────→ Tool Engine
CONFIRM → user confirms → Tool Engine
BLOCKED ─────────────→ stop
        ↓
AuditSink (v1.4.2)
```

## Policy precedence

The effective rule is resolved in this order:

1. session override
2. user override
3. global rule
4. tool's default permission

A disabled matching rule immediately blocks the tool.

## Permission modes

- `safe`: authorization succeeds without a confirmation token.
- `confirm`: a short-lived, one-time confirmation token is required.
- `blocked`: execution is denied.

## Database tables

### `tool_permissions`

Stores persistent tool policies with scopes `global`, `user`, or `session`.

### `tool_confirmations`

Stores only a SHA-256 hash of the confirmation token. The raw token is returned
once to the caller, with a default lifetime of 120 seconds and one-time use.
The confirmation is also bound to session, user, tool, and a canonical hash of
its arguments.

## Example

```python
from security_permissions import PermissionEngine, PermissionMode, PermissionStore

store = PermissionStore("sqlite:///./data/doom.db")
store.init()

store.upsert_permission(
    tool_name="calculator",
    mode=PermissionMode.SAFE,
)

engine = PermissionEngine(store)
decision = engine.decide(
    tool_name="calculator",
    session_id="main",
    user_id="renan",
    default_mode=PermissionMode.BLOCKED,
)

assert decision.allowed
```

## Confirmation example

```python
decision = engine.decide(
    tool_name="sensitive_tool",
    session_id="main",
    user_id="renan",
    default_mode=PermissionMode.CONFIRM,
)

if decision.requires_confirmation:
    token = engine.issue_confirmation(
        decision=decision,
        session_id="main",
        user_id="renan",
        args={"example": True},
    )

# After the user confirms, pass the same token and exact arguments:
authorized = engine.confirm_and_authorize(
    tool_name="sensitive_tool",
    session_id="main",
    user_id="renan",
    args={"example": True},
    confirmation_token=token,
)
```

## v1.4.2 Audit integration

`security_audit_bridge.audit_decision(...)` accepts the existing v1.4.2 `AuditSink`.
It records the permission decision without logging raw confirmation tokens or full
argument payloads.

## Important security boundary

This engine is a policy layer, not a sandbox. High-impact capabilities should remain
`BLOCKED` until a dedicated, constrained implementation exists.

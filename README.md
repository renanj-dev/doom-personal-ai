# Doom v1.4.2 — Persistent Tool Audit

This step adds persistent storage for Tool Engine audit events.

## Architecture

```text
Doom Cortex
    ↓
Tool Engine
    ↓
AuditEvent
    ↓
AuditSink
    ↓
PostgreSQL / SQLite
    ↓
tool_audit_log
```

Each event records timestamp, session, tool, action, permission, success/failure and a detail field.

## Local

```python
from audit_store import ToolAuditStore

store = ToolAuditStore("sqlite:///./data/doom.db")
store.init()
```

## Cloud

Use the same PostgreSQL `DATABASE_URL` already used by the Doom server.

## Integration

The `AuditSink` can receive the existing `AuditEvent` objects from the Tool Engine. The storage layer is intentionally independent of FastAPI and of the AI provider.

No shell/code execution or new privileged tools are introduced by this step.

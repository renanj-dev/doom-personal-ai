# Doom v1.4.3

Security & Permissions Engine for the Doom Tool stack.

## Files

- `security_permissions.py` — persistence, policy resolution, confirmation tokens and secure gate.
- `security_audit_bridge.py` — adapter for the v1.4.2 AuditSink.
- `test_security_permissions.py` — unit tests.
- `DOOM_SECURITY.md` — architecture and integration notes.

## Validation

Run:

```bash
python -m unittest -v test_security_permissions.py
```

Expected result: **7 tests passing**.

## Integration point

Before the existing Tool Engine executes a tool, call `SecureToolGate.authorize(...)`.
Only execute when `allowed == true`.

For a `confirm` decision, return the confirmation request to the UI, then call
`authorize(...)` again with the same tool arguments and the user's confirmation token.

No arbitrary execution capabilities are introduced by this version.

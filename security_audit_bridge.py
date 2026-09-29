"""Optional bridge for v1.4.2 AuditSink integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from security_permissions import PermissionDecision


@dataclass(frozen=True)
class SecurityAuditEvent:
    session_id: str
    tool: str
    action: str
    permission: str
    ok: bool
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def audit_decision(
    sink: Callable[[Any], Any],
    *,
    session_id: str,
    decision: PermissionDecision,
    action: str = "authorize",
) -> Any:
    """Send a safe decision event to the existing v1.4.2 AuditSink.

    Sensitive data such as raw confirmation tokens and full tool arguments are
    intentionally excluded from the event.
    """
    event = SecurityAuditEvent(
        session_id=session_id,
        tool=decision.tool_name,
        action=action,
        permission=decision.mode.value,
        ok=decision.allowed,
        detail=decision.reason,
        metadata={
            "decision": decision.decision.value,
            "source_scope": decision.source_scope.value if decision.source_scope else "default",
        },
    )
    return sink(event)

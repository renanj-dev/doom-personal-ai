from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, delete
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, get_db, init_db
from .models import Conversation, Message, Memory, MemoryProposal, ToolPermission, ToolAuditRecord, SystemSetting, DeepSearchRun, AgentRun
from .schemas import (ChatRequest, ChatResponse, ConversationCreate, ConversationDetailOut, ConversationOut, ConversationUpdate, HistoryMessageOut, MemoryCreate, MemoryOut, MemoryProposalOut, MemoryUpdate, ToolExecuteRequest, DeepSearchToggleRequest, DeepSearchSourceOut, ToolPermissionUpdate, ToolPermissionOut, ToolConfirmationOut, AgentToggleRequest, AgentRunResumeRequest, IdentitySessionOut, IdentityOut, SessionLoginOut, SafetyStatusOut, SafetyAuthorizeRequest, SafetyAuthorizeOut, BreakGlassRegisterOut, ChatCancelRequest)
from .llm import build_user_profile, is_profile_query
from .cortex import ask_with_cortex, route_task, configured_providers, provider_model
from scripts.seed_memories import seed_memories
from .memory_engine import (backfill_legacy_conversations, delete_conversation, get_messages, get_or_create_conversation, list_conversations, new_session_id, search_history, touch_conversation, detect_memory_intent, extract_memory_content, infer_memory_category, create_memory_proposal, get_pending_proposal, resolve_memory_proposal, cancel_memory_proposal, relevant_memories, AFFIRMATIVE_MEMORY, NEGATIVE_MEMORY)
from .context_engine import build_context
from .tools import TOOL_ENGINE
from .security import VALID_MODES, VALID_SCOPES, get_effective_policy, upsert_permission, delete_permission
from .deep_search import DEEP_SEARCH_ENGINE
from .agent import run as run_agent, resume_after_confirmation, run_list as agent_run_list
from .identity import IDENTITY_ENGINE, SESSION_COOKIE_NAME, Principal
from .safety_legal import SafetyDecision, assess_request, authorize_break_glass, consume_grant, register_break_glass, revoke_all as revoke_all_break_glass, status as safety_status
from .cancellation import CANCELLATIONS

settings = get_settings()
app = FastAPI(title="Doom Personal AI", version="1.8.2")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

if settings.cors_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def startup() -> None:
    init_db()
    IDENTITY_ENGINE.bootstrap()
    db = SessionLocal()
    try:
        backfill_legacy_conversations(db)
    finally:
        db.close()
    if settings.seed_memories:
        seed_memories()




def get_global_deep_search_enabled(db: Session) -> bool:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == "deep_search_enabled"))
    if row is None:
        return bool(settings.deep_search_enabled)
    return row.value.strip().lower() == "true"


def get_global_agent_enabled(db: Session) -> bool:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == "agent_enabled"))
    if row is None:
        return bool(settings.agent_enabled)
    return row.value.strip().lower() == "true"


def set_global_agent_enabled(db: Session, enabled: bool) -> None:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == "agent_enabled"))
    if row is None:
        row = SystemSetting(key="agent_enabled", value="true" if enabled else "false")
        db.add(row)
    else:
        row.value = "true" if enabled else "false"
    from datetime import datetime, timezone
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


def set_global_deep_search_enabled(db: Session, enabled: bool) -> None:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == "deep_search_enabled"))
    if row is None:
        row = SystemSetting(key="deep_search_enabled", value="true" if enabled else "false")
        db.add(row)
    else:
        row.value = "true" if enabled else "false"
    from datetime import datetime, timezone
    row.updated_at = datetime.now(timezone.utc)
    db.commit()


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def auth(
    request: Request,
    x_doom_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    principal = IDENTITY_ENGINE.authenticate_session(session_token)
    if principal is not None:
        return principal

    bearer = _extract_bearer(authorization)
    principal = IDENTITY_ENGINE.authenticate_session(bearer)
    if principal is not None:
        return principal

    if settings.security_legacy_api_key:
        principal = IDENTITY_ENGINE.authenticate_api_key(x_doom_key)
        if principal is not None:
            return principal

    raise HTTPException(status_code=401, detail="Sessão Doom inválida ou expirada.")


@app.get("/health")
def health() -> dict:
    return {"status": "online", "name": "Doom", "version": app.version}


@app.post("/api/auth/session", response_model=SessionLoginOut)
def create_auth_session(
    request: Request,
    response: Response,
    x_doom_key: Annotated[str | None, Header()] = None,
):
    created = IDENTITY_ENGINE.create_session(x_doom_key, request.headers.get("user-agent"))
    if created is None:
        raise HTTPException(status_code=401, detail="Chave Doom inválida.")
    token, principal, expires_at = created
    secure = request.url.scheme.lower() == "https"
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max(1, settings.security_session_hours) * 3600,
        expires=expires_at,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return SessionLoginOut(
        authenticated=True,
        identity=IdentityOut(**IDENTITY_ENGINE.me(principal)),
        expires_at=expires_at,
        # Returned only for non-browser API clients. The built-in UI uses the HttpOnly cookie.
        access_token=token,
    )


@app.get("/api/auth/me", response_model=IdentityOut)
def auth_me(principal: Principal = Depends(auth)):
    return IdentityOut(**IDENTITY_ENGINE.me(principal))


@app.get("/api/auth/sessions", response_model=list[IdentitySessionOut])
def auth_sessions(principal: Principal = Depends(auth)):
    return [IdentitySessionOut(**row) for row in IDENTITY_ENGINE.active_sessions(principal.user_id)]


@app.delete("/api/auth/session")
def logout(request: Request, response: Response, principal: Principal = Depends(auth)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    revoked = IDENTITY_ENGINE.revoke_session(token, principal.user_id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True, "revoked": revoked}


@app.post("/api/auth/revoke-all")
def revoke_all_sessions(response: Response, principal: Principal = Depends(auth)):
    count = IDENTITY_ENGINE.revoke_all_sessions(principal.user_id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True, "revoked_sessions": count}

@app.get("/api/safety/status", response_model=SafetyStatusOut, dependencies=[Depends(auth)])
def get_safety_status(db: Session = Depends(get_db)):
    return safety_status(db)


@app.post("/api/safety/break-glass/register", response_model=BreakGlassRegisterOut, dependencies=[Depends(auth)])
def register_emergency_override(label: str = "Emergency Override", db: Session = Depends(get_db)):
    if not settings.emergency_break_glass_enabled:
        raise HTTPException(status_code=503, detail="Emergency Override está desativado na configuração do servidor.")
    row, key = register_break_glass(db, label)
    return BreakGlassRegisterOut(
        registered=True, credential_id=row.id, label=row.label, key=key,
        warning="A chave é exibida somente nesta resposta. Armazene-a em local seguro; o Doom guarda apenas o hash."
    )


@app.post("/api/safety/break-glass/authorize", response_model=SafetyAuthorizeOut, dependencies=[Depends(auth)])
def authorize_emergency_override(payload: SafetyAuthorizeRequest, db: Session = Depends(get_db)):
    try:
        authorization = authorize_break_glass(
            db, session_id=payload.session_id, key=payload.key, reason=payload.reason, scope=payload.scope
        )
    except PermissionError as exc:
        raise HTTPException(status_code=429 if "Limite" in str(exc) else 401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SafetyAuthorizeOut(
        authorized=True, grant_token=authorization.token, expires_at=authorization.expires_at,
        scope=authorization.scope,
        warning="Autorização temporária e de uso único. Ela não libera bloqueios absolutos."
    )


@app.post("/api/safety/break-glass/revoke-all", dependencies=[Depends(auth)])
def revoke_emergency_overrides(db: Session = Depends(get_db)):
    return {"ok": True, "revoked": revoke_all_break_glass(db)}


@app.get("/api/cortex", dependencies=[Depends(auth)])
def cortex_status() -> dict:
    providers = configured_providers()
    return {
        "mode": "auto",
        "providers": providers,
        "primary": providers[0] if providers else None,
        "models": {p: provider_model(p) for p in providers},
    }




@app.get("/api/deep-search", dependencies=[Depends(auth)])
def deep_search_status(db: Session = Depends(get_db)) -> dict:
    return {
        "enabled": get_global_deep_search_enabled(db),
        "available": DEEP_SEARCH_ENGINE.available(),
        "provider": settings.deep_search_provider,
        "detail": DEEP_SEARCH_ENGINE.availability_detail(),
        "max_sources": settings.deep_search_max_sources,
    }


@app.patch("/api/deep-search", dependencies=[Depends(auth)])
def toggle_deep_search(payload: DeepSearchToggleRequest, db: Session = Depends(get_db)) -> dict:
    if payload.enabled and not DEEP_SEARCH_ENGINE.available():
        raise HTTPException(status_code=503, detail=DEEP_SEARCH_ENGINE.availability_detail())
    set_global_deep_search_enabled(db, payload.enabled)
    return deep_search_status(db)


@app.get("/api/deep-search/runs", dependencies=[Depends(auth)])
def deep_search_runs(limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    limit = max(1, min(limit, 100))
    rows = db.scalars(select(DeepSearchRun).order_by(DeepSearchRun.created_at.desc()).limit(limit)).all()
    return [{
        "id": row.id, "session_id": row.session_id, "query": row.query, "provider": row.provider,
        "status": row.status, "query_count": row.query_count, "source_count": row.source_count,
        "duration_ms": row.duration_ms, "created_at": row.created_at, "error": row.error,
    } for row in rows]


@app.get("/api/agent", dependencies=[Depends(auth)])
def agent_status(db: Session = Depends(get_db)) -> dict:
    return {
        "enabled": get_global_agent_enabled(db),
        "max_steps": settings.agent_max_steps,
        "max_tool_calls": settings.agent_max_tool_calls,
    }


@app.patch("/api/agent", dependencies=[Depends(auth)])
def toggle_agent(payload: AgentToggleRequest, db: Session = Depends(get_db)) -> dict:
    set_global_agent_enabled(db, payload.enabled)
    return agent_status(db)


@app.get("/api/agent/runs", dependencies=[Depends(auth)])
def list_agent_runs(limit: int = 20, session_id: str | None = None) -> list[dict]:
    return agent_run_list(limit, session_id)


@app.get("/api/agent/runs/{run_id}", dependencies=[Depends(auth)])
def get_agent_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.query(AgentRun).filter(AgentRun.run_id == run_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Execução do Agent não encontrada.")
    from .models import AgentStep
    steps = db.query(AgentStep).filter(AgentStep.run_id == run_id).order_by(AgentStep.step_index.asc()).all()
    return {
        "run_id": row.run_id, "session_id": row.session_id, "task": row.task, "status": row.status,
        "max_steps": row.max_steps, "tool_calls": row.tool_calls, "started_at": row.started_at,
        "finished_at": row.finished_at, "error": row.error,
        "steps": [{"step_index": s.step_index, "step_id": s.step_id, "action": s.action, "description": s.description,
                   "tool_name": s.tool_name, "args": s.args, "status": s.status, "output": s.output,
                   "error": s.error, "request_id": s.request_id, "finished_at": s.finished_at} for s in steps],
    }


@app.post("/api/agent/runs/{run_id}/resume", dependencies=[Depends(auth)])
def resume_agent(run_id: str, payload: AgentRunResumeRequest, db: Session = Depends(get_db)):
    execution = resume_after_confirmation(run_id, payload.session_id, settings.doom_user_name, payload.confirmation_token)
    if execution.status == "failed":
        raise HTTPException(status_code=409, detail=execution.reply)
    if execution.status == "completed":
        db.add(Message(session_id=payload.session_id, role="assistant", content=execution.reply))
        db.commit()
        touch_conversation(db, payload.session_id)
    return {
        "run_id": execution.run_id, "status": execution.status, "reply": execution.reply,
        "tool_confirmation": execution.confirmation,
    }


@app.get("/api/context/preview", dependencies=[Depends(auth)])
def context_preview(session_id: str = "main", q: str = "") -> dict:
    db = SessionLocal()
    try:
        bundle = build_context(db, session_id, q)
        return {
            "strategy": bundle.strategy,
            "recent": bundle.recent_messages,
            "recalled": bundle.recalled_messages,
            "memories_used": bundle.memory_count,
            "recent_count": bundle.recent_count,
            "recalled_count": bundle.recalled_count,
        }
    finally:
        db.close()


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/memories", response_model=list[MemoryOut], dependencies=[Depends(auth)])
def list_memories(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Memory).where(Memory.active.is_(True)).order_by(Memory.created_at.desc())
    ).all()
    return rows


@app.post("/api/memories", response_model=MemoryOut, dependencies=[Depends(auth)])
def create_memory(payload: MemoryCreate, db: Session = Depends(get_db)):
    row = Memory(category=payload.category, content=payload.content, updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc), revision=1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.patch("/api/memories/{memory_id}", response_model=MemoryOut, dependencies=[Depends(auth)])
def edit_memory(memory_id: int, payload: MemoryUpdate, db: Session = Depends(get_db)):
    row = db.get(Memory, memory_id)
    if not row:
        raise HTTPException(status_code=404, detail="Memória não encontrada.")
    if payload.expected_revision is not None and getattr(row, "revision", 1) != payload.expected_revision:
        raise HTTPException(status_code=409, detail={"message":"Memória foi alterada em outro lugar.","current_revision":getattr(row,"revision",1)})
    if payload.content is None and payload.category is None and payload.active is None:
        raise HTTPException(status_code=422, detail="Nenhuma alteração foi enviada.")
    if payload.content is not None:
        row.content = payload.content.strip()
    if payload.category is not None:
        row.category = payload.category.strip()
    if payload.active is not None:
        row.active = payload.active
    row.revision = getattr(row, "revision", 1) + 1
    row.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db.commit(); db.refresh(row)
    return row


@app.delete("/api/memories/{memory_id}", dependencies=[Depends(auth)])
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    row = db.get(Memory, memory_id)
    if not row:
        raise HTTPException(status_code=404, detail="Memória não encontrada.")
    row.active = False
    db.commit()
    return {"ok": True}


@app.get("/api/memory/pending/{session_id}", response_model=MemoryProposalOut | None, dependencies=[Depends(auth)])
def pending_memory(session_id: str, db: Session = Depends(get_db)):
    return get_pending_proposal(db, session_id)


@app.post("/api/memory/propose", response_model=MemoryProposalOut, dependencies=[Depends(auth)])
def propose_memory(session_id: str, content: str, db: Session = Depends(get_db)):
    proposal = create_memory_proposal(db, session_id, content, infer_memory_category(content))
    return proposal


@app.post("/api/memory/proposals/{proposal_id}/approve", response_model=MemoryOut, dependencies=[Depends(auth)])
def approve_memory(proposal_id: int, db: Session = Depends(get_db)):
    proposal = db.get(MemoryProposal, proposal_id)
    if not proposal or proposal.status != "pending":
        raise HTTPException(status_code=404, detail="Proposta de memória não encontrada ou já resolvida.")
    try:
        return resolve_memory_proposal(db, proposal, True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/memory/proposals/{proposal_id}/reject", dependencies=[Depends(auth)])
def reject_memory(proposal_id: int, db: Session = Depends(get_db)):
    proposal = db.get(MemoryProposal, proposal_id)
    if not proposal or proposal.status != "pending":
        raise HTTPException(status_code=404, detail="Proposta de memória não encontrada ou já resolvida.")
    cancel_memory_proposal(db, proposal)
    return {"ok": True, "proposal_id": proposal_id}


@app.get("/api/memories/search", response_model=list[MemoryOut], dependencies=[Depends(auth)])
def search_memories(q: str, db: Session = Depends(get_db)):
    return relevant_memories(db, q, limit=20)


@app.get("/api/tools", dependencies=[Depends(auth)])
def tools_catalog(session_id: str = "main"):
    catalog = []
    for tool in TOOL_ENGINE.catalog():
        policy = get_effective_policy(tool["name"], session_id, settings.doom_user_name, tool["permission"])
        catalog.append(tool | {"effective_mode": policy["mode"], "policy_source": policy["source"]})
    return {"tools": catalog, "count": len(catalog)}


@app.get("/api/tools/permissions", dependencies=[Depends(auth)])
def tool_permissions(session_id: str = "main"):
    output = []
    for tool in TOOL_ENGINE.catalog():
        policy = get_effective_policy(tool["name"], session_id, settings.doom_user_name, tool["permission"])
        output.append(ToolPermissionOut(tool_name=tool["name"], scope=policy["scope"] or "default", scope_id=policy["scope_id"], mode=policy["mode"], enabled=policy["enabled"], source=policy["source"]))
    return {"session_id": session_id, "permissions": output}


@app.put("/api/tools/permissions", dependencies=[Depends(auth)])
def update_tool_permission(payload: ToolPermissionUpdate):
    if payload.tool_name not in TOOL_ENGINE.tools:
        raise HTTPException(status_code=404, detail="Ferramenta não encontrada.")
    if payload.mode not in VALID_MODES:
        raise HTTPException(status_code=422, detail="Modo de permissão inválido.")
    if payload.scope not in VALID_SCOPES:
        raise HTTPException(status_code=422, detail="Escopo de permissão inválido.")
    if payload.scope == "user" and payload.scope_id not in (None, settings.doom_user_name):
        raise HTTPException(status_code=403, detail="O usuário informado não corresponde ao usuário configurado da Doom.")
    if payload.scope == "user" and not payload.scope_id:
        payload.scope_id = settings.doom_user_name
    try:
        row = upsert_permission(payload.tool_name, payload.scope, payload.scope_id, payload.mode, payload.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ToolPermissionOut(tool_name=row.tool_name, scope=row.scope, scope_id=row.scope_id, mode=row.mode, enabled=row.enabled, source=row.scope)


@app.delete("/api/tools/permissions/{tool_name}", dependencies=[Depends(auth)])
def reset_tool_permission(tool_name: str, scope: str = "global", scope_id: str | None = None):
    if tool_name not in TOOL_ENGINE.tools:
        raise HTTPException(status_code=404, detail="Ferramenta não encontrada.")
    if scope == "user" and scope_id not in (None, settings.doom_user_name):
        raise HTTPException(status_code=403, detail="O usuário informado não corresponde ao usuário configurado da Doom.")
    if scope == "user" and not scope_id:
        scope_id = settings.doom_user_name
    try:
        deleted = delete_permission(tool_name, scope, scope_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "deleted": deleted, "tool_name": tool_name, "scope": scope, "scope_id": scope_id}


@app.post("/api/tools/execute", dependencies=[Depends(auth)])
def execute_tool(payload: ToolExecuteRequest):
    return TOOL_ENGINE.execute(payload.tool, payload.args, payload.session_id, settings.doom_user_name, payload.confirmation_token)


@app.post("/api/tools/execute-batch", dependencies=[Depends(auth)])
def execute_tools_batch(payload: dict):
    session_id = str(payload.get("session_id") or "main")
    calls = payload.get("calls")
    return TOOL_ENGINE.execute_many(calls, session_id, settings.doom_user_name)


@app.get("/api/audit/tools", dependencies=[Depends(auth)])
def tool_audit(limit: int = 100, session_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(ToolAuditRecord).order_by(ToolAuditRecord.timestamp.desc()).limit(min(max(1, limit), 500))
    if session_id:
        stmt = stmt.where(ToolAuditRecord.session_id == session_id)
    rows = db.scalars(stmt).all()
    return [{"timestamp":r.timestamp.isoformat() if r.timestamp else None,"session_id":r.session_id,"tool":r.tool,"action":r.action,"permission":r.permission,"ok":r.ok,"detail":r.detail} for r in rows]


@app.get("/api/conversations", response_model=list[ConversationOut], dependencies=[Depends(auth)])
def list_conversation_history(include_archived: bool = False, db: Session = Depends(get_db)):
    rows = list_conversations(db, include_archived=include_archived)
    output = []
    for row in rows:
        count = db.scalar(select(func.count(Message.id)).where(Message.session_id == row.session_id)) or 0
        output.append(ConversationOut(
            session_id=row.session_id, title=row.title, archived=row.archived,
            created_at=row.created_at, updated_at=row.updated_at, message_count=int(count),
        ))
    return output


@app.post("/api/conversations", response_model=ConversationOut, dependencies=[Depends(auth)])
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)):
    session_id = new_session_id()
    row = get_or_create_conversation(db, session_id, payload.title)
    row.title = payload.title.strip()
    db.commit()
    db.refresh(row)
    return ConversationOut(session_id=row.session_id, title=row.title, archived=row.archived, created_at=row.created_at, updated_at=row.updated_at, message_count=0)


@app.get("/api/conversations/{session_id}", response_model=ConversationDetailOut, dependencies=[Depends(auth)])
def get_conversation(session_id: str, db: Session = Depends(get_db)):
    row = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
    if not row:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    messages = [HistoryMessageOut(id=m.id, session_id=m.session_id, role=m.role, content=m.content, created_at=m.created_at) for m in get_messages(db, session_id)]
    count = len(messages)
    conversation = ConversationOut(session_id=row.session_id, title=row.title, archived=row.archived, created_at=row.created_at, updated_at=row.updated_at, message_count=count)
    return ConversationDetailOut(conversation=conversation, messages=messages)


@app.patch("/api/conversations/{session_id}", response_model=ConversationOut, dependencies=[Depends(auth)])
def update_conversation(session_id: str, payload: ConversationUpdate, db: Session = Depends(get_db)):
    row = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
    if not row:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    if payload.title is not None:
        row.title = payload.title.strip()
    if payload.archived is not None:
        row.archived = payload.archived
    row.updated_at = touch_conversation(db, session_id).updated_at
    db.commit()
    db.refresh(row)
    count = db.scalar(select(func.count(Message.id)).where(Message.session_id == session_id)) or 0
    return ConversationOut(session_id=row.session_id, title=row.title, archived=row.archived, created_at=row.created_at, updated_at=row.updated_at, message_count=int(count))


@app.delete("/api/conversations/{session_id}", dependencies=[Depends(auth)])
def remove_conversation(session_id: str, db: Session = Depends(get_db)):
    if not delete_conversation(db, session_id):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"ok": True, "session_id": session_id}


@app.get("/api/history/search", response_model=list[HistoryMessageOut], dependencies=[Depends(auth)])
def search_conversation_history(q: str, db: Session = Depends(get_db)):
    rows = search_history(db, q)
    return [HistoryMessageOut(id=m.id, session_id=m.session_id, role=m.role, content=m.content, created_at=m.created_at) for m in rows]


@app.delete("/api/sessions/{session_id}", dependencies=[Depends(auth)])
def clear_session(session_id: str, db: Session = Depends(get_db)):
    delete_conversation(db, session_id)
    return {"ok": True, "session_id": session_id}



def infer_mode(message: str) -> str:
    t = (message or "").strip().lower()
    if any(k in t for k in ("quem sou eu", "o que você sabe sobre mim", "o que sabe sobre mim", "memória", "lembra", "lembrar", "esquecer")):
        return "memory"
    if any(k in t for k in ("estud", "aprender", "exercício", "matemática", "enem", "aula")):
        return "study"
    if any(k in t for k in ("analise", "análise", "possibilidade", "possibilidades", "compare", "cenário", "hipótese")):
        return "analysis"
    if any(k in t for k in ("crie", "criar", "escreva", "desenhe", "ideia", "projeto")):
        return "creation"
    if any(k in t for k in ("execute", "executar", "abra", "rodar", "rode", "faça isso")):
        return "execution"
    if any(k in t for k in ("talvez", "especul", "e se", "hipotetic")):
        return "speculation"
    return "thinking"

@app.post("/api/chat/cancel", dependencies=[Depends(auth)])
def cancel_chat(payload: ChatCancelRequest):
    cancelled = CANCELLATIONS.cancel(payload.request_id, payload.session_id)
    return {"ok": True, "request_id": payload.request_id, "session_id": payload.session_id, "cancelled": cancelled}


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(auth)])
def chat(
    payload: ChatRequest,
    x_doom_emergency_grant: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    request_id = payload.request_id or __import__("uuid").uuid4().hex
    CANCELLATIONS.start(request_id, payload.session_id)
    safety = assess_request(payload.message)
    emergency_authorized = False

    if safety.decision == SafetyDecision.BLOCKED:
        get_or_create_conversation(db, payload.session_id, payload.message)
        db.add(Message(session_id=payload.session_id, role="user", content=payload.message))
        reply = (
            "Não posso executar essa solicitação porque ela acionou um bloqueio absoluto do Safety & Legal Engine. "
            "O Emergency Override não pode liberar esse tipo de bloqueio."
        )
        from .safety_legal import _log_event
        _log_event(db, event_type="request_blocked", session_id=payload.session_id, decision=safety.decision.value, category=safety.category, detail=safety.reason)
        db.add(Message(session_id=payload.session_id, role="assistant", content=reply))
        db.commit()
        touch_conversation(db, payload.session_id)
        CANCELLATIONS.finish(request_id)
        return ChatResponse(
            request_id=request_id, session_id=payload.session_id, reply=reply, mode="safety_blocked", brain="safety-engine", task="safety",
            safety_decision=safety.decision.value, safety_category=safety.category, safety_reason=safety.reason,
            break_glass_required=False,
        )

    if safety.decision == SafetyDecision.BREAK_GLASS:
        if x_doom_emergency_grant:
            emergency_authorized = consume_grant(db, session_id=payload.session_id, token=x_doom_emergency_grant)
        if not emergency_authorized:
            get_or_create_conversation(db, payload.session_id, payload.message)
            db.add(Message(session_id=payload.session_id, role="user", content=payload.message))
            reply = (
                "A solicitação foi classificada como restrita pelo Safety & Legal Engine. Para um uso de emergência "
                "compatível, gere uma autorização temporária em Segurança → Break Glass e envie novamente a solicitação. "
                "A autorização é limitada, expira rapidamente e não libera bloqueios absolutos."
            )
            db.add(Message(session_id=payload.session_id, role="assistant", content=reply))
            from .safety_legal import _log_event
            _log_event(db, event_type="request_requires_break_glass", session_id=payload.session_id, decision=safety.decision.value, category=safety.category, detail=safety.reason)
            db.commit()
            touch_conversation(db, payload.session_id)
            CANCELLATIONS.finish(request_id)
            return ChatResponse(
                request_id=request_id, session_id=payload.session_id, reply=reply, mode="safety_break_glass", brain="safety-engine", task="safety",
                safety_decision=safety.decision.value, safety_category=safety.category, safety_reason=safety.reason,
                break_glass_required=True,
            )

    get_or_create_conversation(db, payload.session_id, payload.message)
    db.add(Message(session_id=payload.session_id, role="user", content=payload.message))
    db.commit()
    touch_conversation(db, payload.session_id, payload.message)

    recent_db = db.scalars(
        select(Message)
        .where(Message.session_id == payload.session_id)
        .order_by(Message.created_at.desc())
        .limit(24)
    ).all()
    recent_db.reverse()

    mode = infer_mode(payload.message)
    route = None
    tool_confirmation = None
    context_bundle = None
    deep_search_used = False
    deep_search_result = None
    agent_used = False
    agent_run_id = None
    agent_status = None
    agent_deep_search_query = None
    agent_deep_search_sources = []
    try:
        if CANCELLATIONS.is_cancelled(request_id):
            CANCELLATIONS.finish(request_id)
            return ChatResponse(request_id=request_id, session_id=payload.session_id, reply="Raciocínio interrompido.", mode="interrupted", brain="doom-core", task="interrupt", interrupted=True)
        context_bundle = build_context(db, payload.session_id, payload.message)
        recent = recent_db
        pending = get_pending_proposal(db, payload.session_id)
        normalized = payload.message.strip().lower()

        if pending and normalized in AFFIRMATIVE_MEMORY:
            row = resolve_memory_proposal(db, pending, True)
            reply = f"Entendido. Registrei essa informação na minha memória, em {row.category}."
            mode = "memory"
        elif pending and normalized in NEGATIVE_MEMORY:
            cancel_memory_proposal(db, pending)
            reply = "Entendido. Não vou registrar essa informação."
            mode = "memory"
        elif detect_memory_intent(payload.message):
            content = extract_memory_content(payload.message)
            if not content:
                raise RuntimeError("Não consegui identificar o conteúdo que deveria ser memorizado.")
            proposal = create_memory_proposal(db, payload.session_id, content, infer_memory_category(content))
            reply = (
                f"Entendido. Posso registrar isto na minha memória como {proposal.category}:\n\n"
                f'“{proposal.content}”\n\n'
                "Deseja que eu memorize permanentemente? Responda 'sim' ou 'não'."
            )
            mode = "memory"
        elif is_profile_query(payload.message):
            all_memories = db.scalars(select(Memory).where(Memory.active.is_(True)).order_by(Memory.created_at.desc())).all()
            profile_rows = [(m.category, m.content) for m in all_memories]
            reply = build_user_profile(profile_rows, settings.doom_user_name)
            mode = "memory"
        else:
            recent_user_texts = [m.content.strip().lower() for m in recent if m.role == "user"]
            followups = {"por favor", "sim", "continue", "continue, por favor", "pode", "pode sim", "claro"}
            prior_profile = any(is_profile_query(t) for t in recent_user_texts[:-1])
            if normalized in followups and prior_profile:
                all_memories = db.scalars(select(Memory).where(Memory.active.is_(True)).order_by(Memory.created_at.desc())).all()
                profile_rows = [(m.category, m.content) for m in all_memories]
                reply = build_user_profile(profile_rows, settings.doom_user_name)
                mode = "memory"
            else:
                combined_messages = context_bundle.recent_messages + context_bundle.recalled_messages
                # Historical/contextual messages must never replace the current
                # request. The Cortex receives the current user message separately.
                seen_pairs = set()
                compact_messages = []
                for item in combined_messages:
                    pair = (item["role"], item["content"])
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    compact_messages.append(item)
                # Remove the just-persisted current user turn from the history
                # bundle; ask_with_cortex appends it explicitly as the final user turn.
                for idx in range(len(compact_messages) - 1, -1, -1):
                    item = compact_messages[idx]
                    if item.get("role") == "user" and item.get("content", "").strip() == payload.message.strip():
                        compact_messages.pop(idx)
                        break
                deep_search_used = get_global_deep_search_enabled(db) if payload.deep_search is None else payload.deep_search
                agent_used = get_global_agent_enabled(db) if payload.agent is None else payload.agent
                if agent_used:
                    if CANCELLATIONS.is_cancelled(request_id):
                        CANCELLATIONS.finish(request_id)
                        return ChatResponse(request_id=request_id, session_id=payload.session_id, reply="Raciocínio interrompido.", mode="interrupted", brain="doom-agent", task="interrupt", interrupted=True)
                    agent_result = run_agent(
                        user_message=payload.message,
                        session_id=payload.session_id,
                        user_id=settings.doom_user_name,
                        context_text=context_bundle.memory_text + "\n\n" + (context_bundle.profile_text or ""),
                        deep_search_allowed=deep_search_used,
                        provider=None,
                        cancel_check=lambda: CANCELLATIONS.is_cancelled(request_id),
                    )
                    reply = agent_result.reply
                    agent_run_id = agent_result.run_id
                    agent_status = agent_result.status
                    tool_confirmation = agent_result.confirmation
                    agent_deep_search_query = agent_result.deep_search_query
                    agent_deep_search_sources = list(agent_result.deep_search_sources)
                    route = None
                else:
                    if CANCELLATIONS.is_cancelled(request_id):
                        CANCELLATIONS.finish(request_id)
                        return ChatResponse(request_id=request_id, session_id=payload.session_id, reply="Raciocínio interrompido.", mode="interrupted", brain="doom-core", task="interrupt", interrupted=True)
                    if deep_search_used:
                        deep_search_result = DEEP_SEARCH_ENGINE.research(payload.message, payload.session_id)
                    reply, route, tool_confirmation = ask_with_cortex(
                        memory_text=context_bundle.memory_text,
                        recent_messages=compact_messages,
                        user_message=payload.message,
                        profile_text=context_bundle.profile_text,
                        session_id=payload.session_id,
                        research_text=deep_search_result.context if deep_search_result else None,
                    )
    except Exception as exc:
        CANCELLATIONS.finish(request_id)
        # Remove the just-added user message only when the provider fails, so a retry is clean.
        db.delete(recent[-1])
        db.commit()
        raise HTTPException(status_code=502, detail=f"Falha ao consultar o cérebro da Doom: {exc}") from exc

    db.add(Message(session_id=payload.session_id, role="assistant", content=reply))
    from .safety_legal import _log_event
    _log_event(
        db, event_type="request_processed", session_id=payload.session_id,
        decision=("emergency_authorized" if emergency_authorized else safety.decision.value),
        category=safety.category,
        detail=("Break Glass aplicado" if emergency_authorized else safety.reason),
    )
    db.commit()
    touch_conversation(db, payload.session_id)
    CANCELLATIONS.finish(request_id)
    return ChatResponse(
        request_id=request_id,
        session_id=payload.session_id,
        reply=reply,
        mode=("agent" if agent_used else ("success" if mode == "thinking" else ("deep_search" if deep_search_used else mode))),
        brain=("doom-agent" if agent_used else (route.provider if route else "doom-core")),
        model=(route.model if route else None),
        task=("agent" if agent_used else (route.task if route else "memory")),
        fallback_count=(route.fallback_count if route else 0),
        context_strategy=(context_bundle.strategy if context_bundle and route else None),
        context_recent=(context_bundle.recent_count if context_bundle and route else 0),
        context_recalled=(context_bundle.recalled_count if context_bundle and route else 0),
        memories_used=(context_bundle.memory_count if context_bundle and route else 0),
        deep_search=deep_search_used,
        deep_search_query=(agent_deep_search_query if agent_used else (deep_search_result.query if deep_search_result else None)),
        deep_search_sources=([DeepSearchSourceOut(**x) for x in agent_deep_search_sources] if agent_used else [DeepSearchSourceOut(title=x.title, url=x.url, snippet=x.snippet) for x in (deep_search_result.sources if deep_search_result else ())]),
        tool_confirmation=ToolConfirmationOut(**tool_confirmation) if tool_confirmation else None,
        agent=agent_used,
        agent_run_id=agent_run_id,
        agent_status=agent_status,
        safety_decision=("emergency_authorized" if emergency_authorized else safety.decision.value),
        safety_category=safety.category,
        safety_reason=safety.reason,
        break_glass_required=False,
    )

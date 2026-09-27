from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, delete
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, get_db, init_db
from .models import Conversation, Message, Memory
from .schemas import (ChatRequest, ChatResponse, ConversationCreate, ConversationDetailOut, ConversationOut, ConversationUpdate, HistoryMessageOut, MemoryCreate, MemoryOut)
from .llm import build_user_profile, is_profile_query
from .cortex import ask_with_cortex, route_task, configured_providers, provider_model
from scripts.seed_memories import seed_memories
from .memory_engine import backfill_legacy_conversations, delete_conversation, get_messages, get_or_create_conversation, list_conversations, new_session_id, search_history, touch_conversation

settings = get_settings()
app = FastAPI(title="Doom Personal AI", version="1.1.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

if settings.cors_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def startup() -> None:
    init_db()
    db = SessionLocal()
    try:
        backfill_legacy_conversations(db)
    finally:
        db.close()
    if settings.seed_memories:
        seed_memories()


def auth(x_doom_key: Annotated[str | None, Header()] = None) -> None:
    if not x_doom_key or x_doom_key != settings.doom_api_key:
        raise HTTPException(status_code=401, detail="Chave Doom inválida.")


@app.get("/health")
def health() -> dict:
    return {"status": "online", "name": "Doom", "version": app.version}

@app.get("/api/cortex", dependencies=[Depends(auth)])
def cortex_status() -> dict:
    providers = configured_providers()
    return {
        "mode": "auto",
        "providers": providers,
        "primary": providers[0] if providers else None,
        "models": {p: provider_model(p) for p in providers},
    }


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
    row = Memory(category=payload.category, content=payload.content)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/api/memories/{memory_id}", dependencies=[Depends(auth)])
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    row = db.get(Memory, memory_id)
    if not row:
        raise HTTPException(status_code=404, detail="Memória não encontrada.")
    row.active = False
    db.commit()
    return {"ok": True}


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

@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(auth)])
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    get_or_create_conversation(db, payload.session_id, payload.message)
    db.add(Message(session_id=payload.session_id, role="user", content=payload.message))
    db.commit()
    touch_conversation(db, payload.session_id, payload.message)

    recent = db.scalars(
        select(Message)
        .where(Message.session_id == payload.session_id)
        .order_by(Message.created_at.desc())
        .limit(24)
    ).all()
    recent.reverse()

    memories = db.scalars(
        select(Memory)
        .where(Memory.active.is_(True))
        .order_by(Memory.created_at.desc())
        .limit(50)
    ).all()
    memory_text = "\n".join(f"[{m.category}] {m.content}" for m in memories)

    mode = infer_mode(payload.message)
    route = None
    try:
        recent_payload = [{"role": m.role, "content": m.content} for m in recent]
        if is_profile_query(payload.message):
            profile_rows = [(m.category, m.content) for m in memories]
            reply = build_user_profile(profile_rows, settings.doom_user_name)
            mode = "memory"
        else:
            # A short affirmative follow-up can mean "continue the profile".
            recent_user_texts = [m.content.strip().lower() for m in recent if m.role == "user"]
            followups = {"por favor", "sim", "continue", "continue, por favor", "pode", "pode sim", "claro"}
            prior_profile = any(is_profile_query(t) for t in recent_user_texts[:-1])
            if payload.message.strip().lower() in followups and prior_profile:
                profile_rows = [(m.category, m.content) for m in memories]
                reply = build_user_profile(profile_rows, settings.doom_user_name)
                mode = "memory"
            else:
                reply, route = ask_with_cortex(
                    memory_text=memory_text,
                    recent_messages=recent_payload,
                    user_message=payload.message,
                )
    except Exception as exc:
        # Remove the just-added user message only when the provider fails, so a retry is clean.
        db.delete(recent[-1])
        db.commit()
        raise HTTPException(status_code=502, detail=f"Falha ao consultar o cérebro da Doom: {exc}") from exc

    db.add(Message(session_id=payload.session_id, role="assistant", content=reply))
    db.commit()
    touch_conversation(db, payload.session_id)
    return ChatResponse(
        session_id=payload.session_id,
        reply=reply,
        mode="success" if mode == "thinking" else mode,
        brain=(route.provider if route else "doom-core"),
        model=(route.model if route else None),
        task=(route.task if route else "memory"),
        fallback_count=(route.fallback_count if route else 0),
    )

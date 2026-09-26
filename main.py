from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, init_db
from .models import Message, Memory
from .schemas import ChatRequest, ChatResponse, MemoryCreate, MemoryOut
from .llm import ask_doom, build_user_profile, is_profile_query
from scripts.seed_memories import seed_memories

settings = get_settings()
app = FastAPI(title="Doom Personal AI", version="0.8.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

if settings.cors_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def startup() -> None:
    init_db()
    if settings.seed_memories:
        seed_memories()


def auth(x_doom_key: Annotated[str | None, Header()] = None) -> None:
    if not x_doom_key or x_doom_key != settings.doom_api_key:
        raise HTTPException(status_code=401, detail="Chave Doom inválida.")


@app.get("/health")
def health() -> dict:
    return {"status": "online", "name": "Doom", "version": app.version}


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


@app.delete("/api/sessions/{session_id}", dependencies=[Depends(auth)])
def clear_session(session_id: str, db: Session = Depends(get_db)):
    db.execute(delete(Message).where(Message.session_id == session_id))
    db.commit()
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
    db.add(Message(session_id=payload.session_id, role="user", content=payload.message))
    db.commit()

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
                reply = ask_doom(
                    memory_text=memory_text,
                    recent_messages=recent_payload,
                )
    except Exception as exc:
        # Remove the just-added user message only when the provider fails, so a retry is clean.
        db.delete(recent[-1])
        db.commit()
        raise HTTPException(status_code=502, detail=f"Falha ao consultar o cérebro da Doom: {exc}") from exc

    db.add(Message(session_id=payload.session_id, role="assistant", content=reply))
    db.commit()
    return ChatResponse(session_id=payload.session_id, reply=reply, mode="success" if mode == "thinking" else mode)

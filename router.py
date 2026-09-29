"""Optional FastAPI router for Doom v1.4.4.

The main app supplies a MemoryHistoryService dependency so this router can be
plugged into the existing Doom API without embedding database details here.
"""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from memory_history_engine import MemoryHistoryService, MemoryPatch, MutationStatus, conversation_to_dict, memory_to_dict


class MemoryPatchBody(BaseModel):
    content: str | None = Field(default=None, max_length=4000)
    category: str | None = None
    enabled: bool | None = None
    expected_revision: int | None = Field(default=None, ge=1)
    confirmation_token: str | None = None


class HistoryDeleteBody(BaseModel):
    confirmation_token: str | None = None


def build_router(service_dependency: Callable[[], MemoryHistoryService], *, user_id_dependency: Callable[[], str] | None = None) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["history-memory"])

    def get_user_id() -> str | None:
        return user_id_dependency() if user_id_dependency else None

    @router.get("/conversations")
    def list_conversations(
        limit: int = Query(default=100, ge=1, le=500),
        service: MemoryHistoryService = Depends(service_dependency),
    ):
        return [conversation_to_dict(row) for row in service.store.list_conversations(limit=limit)]

    @router.delete("/conversations/{session_id}")
    def delete_conversation(
        session_id: str,
        body: HistoryDeleteBody | None = None,
        service: MemoryHistoryService = Depends(service_dependency),
    ):
        result = service.delete_history(
            session_id=session_id,
            user_id=get_user_id(),
            confirmation_token=body.confirmation_token if body else None,
        )
        if result.status is MutationStatus.NOT_FOUND:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        if result.status is MutationStatus.INVALID:
            return {"status": result.status.value, "message": result.data or result.__dict__}
        if result.status is MutationStatus.FORBIDDEN:
            raise HTTPException(status_code=403, detail=result.data or "action_forbidden")
        return {
            "status": result.status.value,
            "session_id": result.session_id,
            "deleted_messages": result.deleted_messages,
            "deleted_conversation": result.deleted_conversation,
        }

    @router.get("/memories")
    def list_memories(
        include_disabled: bool = True,
        limit: int = Query(default=500, ge=1, le=1000),
        service: MemoryHistoryService = Depends(service_dependency),
    ):
        rows = service.store.list_memories(user_id=get_user_id(), include_disabled=include_disabled, limit=limit)
        return [memory_to_dict(row) for row in rows]

    @router.patch("/memories/{memory_id}")
    def edit_memory(
        memory_id: int,
        body: MemoryPatchBody,
        session_id: str = Query(..., min_length=1, max_length=128),
        service: MemoryHistoryService = Depends(service_dependency),
    ):
        patch = MemoryPatch(
            content=body.content,
            category=body.category,
            enabled=body.enabled,
            expected_revision=body.expected_revision,
        )
        result = service.edit_memory(
            memory_id=memory_id,
            session_id=session_id,
            patch=patch,
            user_id=get_user_id(),
            confirmation_token=body.confirmation_token,
        )
        if result.status is MutationStatus.NOT_FOUND:
            raise HTTPException(status_code=404, detail="memory_not_found")
        if result.status is MutationStatus.FORBIDDEN:
            raise HTTPException(status_code=403, detail=result.message)
        if result.status is MutationStatus.CONFLICT:
            raise HTTPException(status_code=409, detail=result.data or result.message)
        if result.status is MutationStatus.INVALID:
            raise HTTPException(status_code=422, detail=result.message)
        return result.data

    return router

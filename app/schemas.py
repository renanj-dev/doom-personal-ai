from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(default="main", min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=20000)
    # None = use the global Deep Search setting; True/False overrides it for this request.
    deep_search: bool | None = None


class DeepSearchSourceOut(BaseModel):
    title: str
    url: str
    snippet: str = ""


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    mode: str = "success"
    brain: str | None = None
    model: str | None = None
    task: str | None = None
    fallback_count: int = 0
    context_strategy: str | None = None
    context_recent: int = 0
    context_recalled: int = 0
    memories_used: int = 0
    deep_search: bool = False
    deep_search_query: str | None = None
    deep_search_sources: list[DeepSearchSourceOut] = Field(default_factory=list)


class MemoryCreate(BaseModel):
    category: str = Field(default="general", min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=5000)


class MemoryOut(BaseModel):
    id: int
    category: str
    content: str
    active: bool
    created_at: datetime
    updated_at: datetime | None = None
    revision: int = 1


class ConversationCreate(BaseModel):
    title: str = Field(default="Nova conversa", min_length=1, max_length=160)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    archived: bool | None = None


class ConversationOut(BaseModel):
    session_id: str
    title: str
    archived: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class HistoryMessageOut(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[HistoryMessageOut]


class MemoryProposalOut(BaseModel):
    id: int
    session_id: str
    category: str
    content: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None

class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    active: bool | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class ToolExecuteRequest(BaseModel):
    session_id: str = Field(default="main", min_length=1, max_length=128)
    tool: str = Field(min_length=1, max_length=128)
    args: dict = Field(default_factory=dict)
    confirmation_token: str | None = None


class DeepSearchToggleRequest(BaseModel):
    enabled: bool

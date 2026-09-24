from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(default="main", min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=20000)


class ChatResponse(BaseModel):
    session_id: str
    reply: str


class MemoryCreate(BaseModel):
    category: str = Field(default="general", min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=5000)


class MemoryOut(BaseModel):
    id: int
    category: str
    content: str
    active: bool
    created_at: datetime

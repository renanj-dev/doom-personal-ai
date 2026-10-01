from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    session_id: str = Field(default="main", min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=20000)
    # None = use the global Deep Search setting; True/False overrides it for this request.
    deep_search: bool | None = None
    # None = use the global Agent setting; True/False overrides it for this request.
    agent: bool | None = None


class DeepSearchSourceOut(BaseModel):
    title: str
    url: str
    snippet: str = ""


class ToolConfirmationOut(BaseModel):
    request_id: str | None = None
    tool: str
    args: dict = Field(default_factory=dict)
    confirmation_token: str
    expires_in: int = 120
    agent_run_id: str | None = None
    agent_step_id: str | None = None


class ChatResponse(BaseModel):
    request_id: str | None = None
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
    tool_confirmation: ToolConfirmationOut | None = None
    agent: bool = False
    agent_run_id: str | None = None
    agent_status: str | None = None
    safety_decision: str | None = None
    safety_category: str | None = None
    safety_reason: str | None = None
    break_glass_required: bool = False
    interrupted: bool = False


class ChatCancelRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(default="main", min_length=1, max_length=128)


class SafetyStatusOut(BaseModel):
    enabled: bool
    registered_credentials: int
    active_grants: int
    grant_minutes: int
    max_attempts: int
    cooldown_minutes: int
    hard_blocks_overridable: bool


class SafetyAuthorizeRequest(BaseModel):
    session_id: str = Field(default="main", min_length=1, max_length=128)
    key: str = Field(min_length=8, max_length=200)
    reason: str = Field(min_length=5, max_length=1000)
    scope: str = Field(default="chat-restricted", min_length=1, max_length=64)


class SafetyAuthorizeOut(BaseModel):
    authorized: bool
    grant_token: str
    expires_at: datetime
    scope: str
    warning: str


class BreakGlassRegisterOut(BaseModel):
    registered: bool
    credential_id: int
    label: str
    key: str
    warning: str


class ExternalIntegrationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(default="http_json", min_length=1, max_length=32)
    base_url: str = Field(min_length=8, max_length=500)
    allowed_paths: list[str] = Field(default_factory=lambda: ["/"])
    allowed_methods: list[str] = Field(default_factory=lambda: ["GET"])
    auth_env_var: str = Field(default="", max_length=120)
    auth_header: str = Field(default="Authorization", max_length=100)
    enabled: bool = True
    timeout_seconds: float | None = Field(default=None, ge=0.5, le=30.0)


class ExternalIntegrationToggle(BaseModel):
    enabled: bool


class ExternalIntegrationOut(BaseModel):
    id: int
    name: str
    kind: str
    base_url: str
    allowed_paths: list[str]
    allowed_methods: list[str]
    auth_env_var: str = ""
    auth_header: str = "Authorization"
    enabled: bool
    timeout_seconds: float
    created_at: datetime
    updated_at: datetime
    last_test_status: str = ""
    last_test_at: datetime | None = None


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


class ToolPermissionUpdate(BaseModel):
    tool_name: str = Field(min_length=1, max_length=128)
    mode: str = Field(min_length=1, max_length=16)
    enabled: bool = True
    scope: str = Field(default="global", min_length=1, max_length=16)
    scope_id: str | None = Field(default=None, max_length=128)


class ToolPermissionOut(BaseModel):
    tool_name: str
    scope: str
    scope_id: str | None = None
    mode: str
    enabled: bool
    source: str


class AgentToggleRequest(BaseModel):
    enabled: bool


class AgentRunResumeRequest(BaseModel):
    session_id: str = Field(default="main", min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=1, max_length=256)


class IdentitySessionOut(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime
    revoked: bool
    expired: bool
    user_agent: str = ""


class IdentityOut(BaseModel):
    user_id: str
    username: str
    display_name: str
    active: bool
    auth_method: str
    session_id: str | None = None
    session_hours: int | None = None
    mode: str
    created_at: datetime
    updated_at: datetime


class SessionLoginOut(BaseModel):
    authenticated: bool
    identity: IdentityOut
    expires_at: datetime
    access_token: str | None = None

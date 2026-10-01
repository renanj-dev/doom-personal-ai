from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
database_url = settings.database_url.strip()

# SQLAlchemy's psycopg v3 dialect is explicit here so the same URL works locally and in cloud.
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://") :]
elif database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgres://") :]

connect_args = {}
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _migrate_existing_schema() -> None:
    """Apply only additive schema changes needed by v1.4.x.

    SQLAlchemy's create_all() does not ALTER tables that already exist. The Render/Neon
    database can therefore still contain the v1.3 `memories` table. This migration is
    intentionally small and idempotent: it adds missing columns without deleting data.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "memories" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("memories")}
    dialect = engine.dialect.name

    with engine.begin() as conn:
        if "updated_at" not in columns:
            if dialect == "postgresql":
                conn.execute(text("ALTER TABLE memories ADD COLUMN updated_at TIMESTAMPTZ"))
            elif dialect == "sqlite":
                conn.execute(text("ALTER TABLE memories ADD COLUMN updated_at DATETIME"))
            else:
                raise RuntimeError(f"Banco não suportado para migração de memories: {dialect}")
            conn.execute(text("UPDATE memories SET updated_at = created_at WHERE updated_at IS NULL"))

        if "revision" not in columns:
            if dialect == "postgresql":
                conn.execute(text("ALTER TABLE memories ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"))
            elif dialect == "sqlite":
                conn.execute(text("ALTER TABLE memories ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"))
            else:
                raise RuntimeError(f"Banco não suportado para migração de memories: {dialect}")


def init_db() -> None:
    from .models import (  # noqa: F401
        Conversation,
        Memory,
        Message,
        MemoryProposal,
        ToolPermission,
        ToolConfirmation,
        ToolAuditRecord,
        SystemSetting,
        DeepSearchRun,
        AgentRun,
        AgentStep,
        UserIdentity,
        ApiKeyRecord,
        UserSession,
        BreakGlassCredential,
        BreakGlassGrant,
        SafetyEvent,
    )

    Base.metadata.create_all(bind=engine)
    _migrate_existing_schema()


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""
db.py — SQLAlchemy async engine + ORM models for AlloyDB (PostgreSQL).
Run `alembic upgrade head` to apply migrations.
"""

from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import (
    Column, String, Text, DateTime, JSON, Integer, ForeignKey, func
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from config import get_settings

settings = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.alloydb_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# ── Base ──────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Models ────────────────────────────────────────────────────────────────────

class Session(Base):
    """Tracks a user's conversation session across agents."""
    __tablename__ = "sessions"

    id = Column(String(64), primary_key=True)            # UUID or token
    user_id = Column(String(256), nullable=False, index=True)
    context = Column(JSON, default=dict)                 # shared agent context
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    events = relationship("AgentEvent", back_populates="session")
    notes = relationship("Note", back_populates="session")
    tasks = relationship("Task", back_populates="session")


class AgentEvent(Base):
    """Audit log of every agent invocation."""
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.id"), index=True)
    agent = Column(String(64))                           # calendar/notes/maps/tasks
    action = Column(String(128))                         # tool called
    payload = Column(JSON)                               # request params
    result = Column(JSON)                                # response summary
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("Session", back_populates="events")


class Note(Base):
    """Persisted note created or synced via the Notes agent."""
    __tablename__ = "notes"

    id = Column(String(128), primary_key=True)           # Google Keep note ID
    session_id = Column(String(64), ForeignKey("sessions.id"), index=True)
    title = Column(String(512), nullable=True)
    body = Column(Text)
    labels = Column(JSON, default=list)
    synced_at = Column(DateTime, server_default=func.now())

    session = relationship("Session", back_populates="notes")


class Task(Base):
    """Persisted task created or synced via the Tasks agent."""
    __tablename__ = "tasks"

    id = Column(String(128), primary_key=True)           # Google Tasks task ID
    session_id = Column(String(64), ForeignKey("sessions.id"), index=True)
    title = Column(String(512))
    notes = Column(Text, nullable=True)
    due = Column(DateTime, nullable=True)
    status = Column(String(32), default="needsAction")   # needsAction | completed
    synced_at = Column(DateTime, server_default=func.now())

    session = relationship("Session", back_populates="tasks")


# ── Schema creation helper (used in tests / first-run) ───────────────────────
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

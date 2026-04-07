"""
main.py — FastAPI application.
Cloud Run serves this via uvicorn.

Endpoints:
  POST /chat            — main agent interaction
  GET  /health          — liveness probe
  GET  /sessions/{id}   — retrieve session context
  DELETE /sessions/{id} — clear session
"""

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from agents.orchestrator import Orchestrator
from config import get_settings
from db import AgentEvent, Session, create_tables, get_db

# ── Logging ───────────────────────────────────────────────────────────────────
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))
logger = structlog.get_logger()

settings = get_settings()

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    logger.info("DB tables ready")
    yield

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Multi-Agent Google Assistant",
    description="Orchestrates Calendar, Notes, Maps, and Tasks agents over Google APIs",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None    # omit to start a new session
    user_id: str = "anonymous"


class ChatResponse(BaseModel):
    session_id: str
    routed_to: list[str]
    summary: str
    responses: list[dict[str, Any]]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_create_session(
    db: AsyncSession, session_id: str | None, user_id: str
) -> Session:
    if session_id:
        result = await db.execute(select(Session).where(Session.id == session_id))
        session = result.scalar_one_or_none()
        if session:
            return session
    # Create new session
    new_session = Session(id=str(uuid.uuid4()), user_id=user_id, context={})
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return new_session


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "multi-agent-google"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    session = await _get_or_create_session(db, req.session_id, req.user_id)

    # Run orchestrator
    try:
        output = orchestrator.handle(req.message, session_context=session.context)
    except Exception as exc:
        logger.error("Orchestrator error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    # Persist event log
    for resp in output["responses"]:
        event = AgentEvent(
            session_id=session.id,
            agent=resp.get("agent"),
            action=resp.get("tool_called"),
            payload={"message": req.message},
            result={"summary": resp.get("result")},
            error=resp.get("error"),
        )
        db.add(event)

    # Update session context with latest agent outputs
    session.context = session.context or {}
    session.context["last_message"] = req.message
    session.context["last_agents"] = output["routed_to"]

    await db.commit()

    return ChatResponse(
        session_id=session.id,
        routed_to=output["routed_to"],
        summary=output["summary"],
        responses=output["responses"],
    )


@app.get("/sessions/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    events_result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.session_id == session_id)
        .order_by(AgentEvent.created_at)
    )
    events = events_result.scalars().all()
    return {
        "session_id": session.id,
        "user_id": session.user_id,
        "context": session.context,
        "events": [
            {"agent": e.agent, "action": e.action, "created_at": str(e.created_at)}
            for e in events
        ],
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()
    return {"deleted": True, "session_id": session_id}

"""
AlloyDB client for the Agentic AI Google Ecosystem.

Supports two connection modes:
  1. Via AlloyDB Connector (IAM / service account – preferred for GCP)
  2. Via a direct DATABASE_URL (for local development / Cloud SQL proxy)

Usage
-----
  from database.alloydb_client import AlloyDBClient

  db = AlloyDBClient()
  await db.init()
  async with db.session() as session:
      ...
  await db.close()
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import settings
from database.models import Base

logger = logging.getLogger(__name__)


class AlloyDBClient:
    """Async SQLAlchemy client for AlloyDB (PostgreSQL-compatible)."""

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._connector = None  # google-cloud-alloydb-connector handle

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def init(self) -> None:
        """Initialise the engine and create tables if they don't exist."""
        url = await self._build_url()
        # When using the AlloyDB Connector the engine is already created in
        # _build_connector_url(); skip creating a second engine.
        if self._engine is None:
            self._engine = create_async_engine(url, echo=False, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        await self._create_tables()
        logger.info("AlloyDB client initialised.")

    async def close(self) -> None:
        """Dispose the engine and close the connector (if any)."""
        if self._engine:
            await self._engine.dispose()
        if self._connector:
            await self._connector.close()
        logger.info("AlloyDB client closed.")

    # ------------------------------------------------------------------ #
    # Session context manager
    # ------------------------------------------------------------------ #

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield an async SQLAlchemy session with automatic rollback on error."""
        if self._session_factory is None:
            raise RuntimeError("AlloyDBClient.init() has not been called.")
        async with self._session_factory() as db_session:
            try:
                yield db_session
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                raise

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    async def _build_url(self) -> str:
        """Return an async-compatible SQLAlchemy connection URL."""
        # Highest priority: explicit DATABASE_URL env var
        if settings.database_url:
            logger.info("Using DATABASE_URL for AlloyDB connection.")
            return settings.database_url

        # Second option: AlloyDB Connector (recommended on GCP)
        if settings.alloydb_instance_uri:
            logger.info("Using AlloyDB Connector for connection.")
            return await self._build_connector_url()

        # Fallback: warn and return an in-memory SQLite URL for local dev
        logger.warning(
            "No AlloyDB configuration found. "
            "Falling back to in-memory SQLite (data will NOT persist)."
        )
        return "sqlite+aiosqlite:///./agentic_ai_local.db"

    async def _build_connector_url(self) -> str:
        """Initialise the AlloyDB Connector and return a connection URL."""
        try:
            from google.cloud.alloydb.connector import AsyncConnector
            import asyncpg  # noqa: F401 – ensure the driver is present

            self._connector = AsyncConnector()

            async def _getconn():
                return await self._connector.connect(
                    settings.alloydb_instance_uri,
                    "asyncpg",
                    user=settings.alloydb_db_user,
                    password=settings.alloydb_db_password,
                    db=settings.alloydb_db_name,
                )

            # SQLAlchemy async engine with a custom creator callable
            from sqlalchemy.ext.asyncio import create_async_engine

            engine_url = "postgresql+asyncpg://"
            self._engine = create_async_engine(
                engine_url,
                async_creator=_getconn,
                echo=False,
                pool_pre_ping=True,
            )
            # Return sentinel – engine is already created above
            return engine_url

        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-alloydb-connector[asyncpg] is required for "
                "AlloyDB Connector mode. Run: pip install google-cloud-alloydb-connector[asyncpg]"
            ) from exc

    async def _create_tables(self) -> None:
        """Create all ORM tables if they don't already exist."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified / created.")

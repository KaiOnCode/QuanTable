"""Agentic-Quant FastAPI server.

Bridges the React frontend (localhost:3000) with the LangGraph agent pipeline.
All REST endpoints are defined in server/routes/ per docs/api-contracts.md.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on sys.path for imports
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

load_dotenv(_project_root / "properties.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Agentic-Quant server starting...")

    # Start data collector if enabled
    if os.getenv("START_COLLECTOR", "").lower() == "true":
        try:
            from scheduler import DataCollector
            app.state.collector = DataCollector()
            app.state.collector.start()
            logger.info("DataCollector started")
        except Exception as exc:
            logger.warning("DataCollector failed to start: %s", exc)

    yield

    # Shutdown
    if hasattr(app.state, "collector"):
        try:
            app.state.collector.stop()
        except Exception:
            pass
    logger.info("Agentic-Quant server stopped")


app = FastAPI(
    title="Agentic-Quant API",
    description="Multi-agent quantitative analysis framework",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routes ────────────────────────────────────────

from server.routes import analyze, strategies, memory, settings, health, market, watchlist

app.include_router(analyze.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(memory.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")

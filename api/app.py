"""
FastAPI application factory and lifespan handler.

Startup sequence:
  1. Load settings from environment
  2. Initialize PostgreSQL connection and create tables
  3. Start event bus and register all 9 agents
  4. Mount all API routers

Shutdown:
  1. Stop event bus gracefully
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.bus import bus
from core.db import init_db

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown logic."""
    # --- STARTUP ---
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://costsense_user:password@localhost:5432/costsense_db",
    )

    logger.info("app.startup", database_url=database_url.split("@")[-1])

    # 1. Initialize database
    await init_db(database_url)

    # 2. Register all agents (order matters for subscription setup)
    from agents.agent_01_data_connector import DataConnectorAgent
    from agents.agent_02_normalization import NormalizationAgent
    from agents.agent_03_anomaly_detection import AnomalyDetectionAgent
    from agents.agent_04_root_cause import RootCauseAgent
    from agents.agent_05_prioritization import PrioritizationAgent
    from agents.agent_06_merge import MergeAgent
    from agents.agent_07_action_dispatcher import ActionDispatcherAgent
    from agents.agent_08_workflow_executor import WorkflowExecutorAgent
    from agents.agent_09_audit_trail import AuditTrailAgent

    data_connector = DataConnectorAgent(bus)
    NormalizationAgent(bus)
    AnomalyDetectionAgent(bus)
    RootCauseAgent(bus)
    PrioritizationAgent(bus)
    MergeAgent(bus)
    ActionDispatcherAgent(bus)
    WorkflowExecutorAgent(bus)
    AuditTrailAgent(bus)

    # 3. Inject data connector into ingest routes
    from api.routes.ingest import set_data_connector
    set_data_connector(data_connector)

    # 4. Start the event bus (spawns drain tasks for all topics)
    await bus.start()

    logger.info("app.all_agents_started", agent_count=9)

    yield  # Application runs here

    # --- SHUTDOWN ---
    logger.info("app.shutdown")
    await bus.stop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="CostSense AI",
        description=(
            "Autonomous cost intelligence platform — "
            "detects enterprise spend anomalies and triggers corrective actions."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS — allow Streamlit UI to call the API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    from api.routes.health import router as health_router
    from api.routes.synthetic_data import router as synthetic_router
    from api.routes.ingest import router as ingest_router
    from api.routes.anomalies import router as anomalies_router
    from api.routes.audit import router as audit_router
    from api.routes.bus_events import router as bus_router
    from api.routes.summary import router as summary_router
    from api.routes.process_logs import router as logs_router

    app.include_router(health_router)
    app.include_router(synthetic_router)
    app.include_router(ingest_router)
    app.include_router(anomalies_router)
    app.include_router(audit_router)
    app.include_router(bus_router)
    app.include_router(summary_router)
    app.include_router(logs_router)

    return app


# Module-level app instance — used by uvicorn
app = create_app()

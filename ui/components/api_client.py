"""
Thin HTTP client for the Streamlit UI to communicate with the FastAPI backend.
All functions are synchronous (Streamlit is sync by default).
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TIMEOUT = 30


def _get(path: str, params: Optional[dict] = None) -> Any:
    try:
        resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return None
    except Exception as exc:
        return {"error": str(exc)}


def _post(path: str, json: Optional[dict] = None) -> Any:
    try:
        resp = requests.post(f"{BASE_URL}{path}", json=json or {}, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return None
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def get_health() -> Optional[dict]:
    return _get("/health")


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------

def get_synthetic_data(n: int = 86, seed: int = 42, include_anomalies: bool = True) -> Optional[dict]:
    return _get("/synthetic/data", params={"n": n, "seed": seed, "include_anomalies": include_anomalies})


def get_synthetic_download_url(n: int = 86, seed: int = 42, include_anomalies: bool = True) -> str:
    return f"{BASE_URL}/synthetic/download?n={n}&seed={seed}&include_anomalies={include_anomalies}"


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest_demo(n: int = 86, seed: int = 42, include_anomalies: bool = True) -> Optional[dict]:
    return _post("/ingest/demo", {"n": n, "seed": seed, "include_anomalies": include_anomalies})


def ingest_batch(records: list[dict]) -> Optional[dict]:
    return _post("/ingest/batch", records)


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------

def get_anomalies(status: Optional[str] = None, limit: int = 200) -> Optional[dict]:
    params = {"limit": limit}
    if status:
        params["status"] = status
    return _get("/anomalies", params=params)


def get_pending_approval() -> Optional[dict]:
    return _get("/anomalies/pending-approval")


def approve_anomaly(anomaly_id: str, approved_by: str = "CFO", notes: Optional[str] = None) -> Optional[dict]:
    return _post(f"/anomalies/{anomaly_id}/approve", {"approved_by": approved_by, "notes": notes})


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def get_audit_log(limit: int = 50, process_id: Optional[str] = None) -> Optional[dict]:
    params = {"limit": limit}
    if process_id:
        params["process_id"] = process_id
    return _get("/audit", params=params)


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

def get_bus_events(topic: Optional[str] = None, limit: int = 50) -> Optional[dict]:
    params = {"limit": limit}
    if topic:
        params["topic"] = topic
    return _get("/bus/events", params=params)


# ---------------------------------------------------------------------------
# Process logs
# ---------------------------------------------------------------------------

def get_process_logs(
    process_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    limit: int = 200,
) -> Optional[dict]:
    params = {"limit": limit}
    if process_id:
        params["process_id"] = process_id
    if agent_name:
        params["agent_name"] = agent_name
    return _get("/logs", params=params)


def get_process_trace(process_id: str) -> Optional[dict]:
    return _get(f"/logs/{process_id}")


def list_processes(limit: int = 50) -> Optional[dict]:
    return _get("/logs/processes", params={"limit": limit})


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def get_summary() -> Optional[dict]:
    return _get("/summary")

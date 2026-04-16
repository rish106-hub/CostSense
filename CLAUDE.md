# CostSense AI — Project Memory

## What this project is
Autonomous cost intelligence platform for the **ET Gen AI Hackathon 2026**.
Detects enterprise spend anomalies using a **9-agent choreography pipeline**, scores them by financial impact, and either auto-executes resolutions or routes to a CFO approval gate.

---

## How to run

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Copy and fill env
cp .env.example .env

# 3. Start API (port 8000)
python run.py

# 4. Start UI (port 8501)
python run_ui.py

# Docs
open http://localhost:8000/docs
open http://localhost:8501
```

---

## Tech stack

| Layer | Tech |
|-------|------|
| API | FastAPI + uvicorn |
| Agents | Python asyncio — choreography via `asyncio.Queue` |
| LLM | Google Gemini 2.5 Flash / 1.5 Flash fallback (LangChain) |
| Anomaly detection | PyOD IsolationForest + 5 custom rule detectors |
| DB | PostgreSQL + SQLAlchemy async (asyncpg driver) |
| Vector search | pgvector `vector(1536)` — cosine similarity |
| Embeddings | OpenAI `text-embedding-3-small` |
| UI | Streamlit + Plotly |
| Config | Pydantic Settings + python-dotenv |
| Retry | tenacity |
| Logging | structlog |

---

## Architecture — 9-Agent Event Bus

All agents are choreography-based. No central orchestrator. Each subscribes to a topic on `core/bus.py` (`asyncio.Queue`).

```
POST /ingest/*
  └─► Agent 01 (data_connector)      raw.spend
        └─► Agent 02 (normalization)  normalized.spend
              └─► Agent 03 (anomaly_detection)  anomaly.detected
                        ├─► Agent 04 (root_cause)     [LLM, ~2-4s]  anomaly.enriched
                        └─► Agent 05 (prioritization) [<1ms]         anomaly.scored
                                    ╲                 ╱
                               Agent 06 (merge)       anomaly.ready
                                    └─► Agent 07 (action_dispatcher)
                                              ├─► action.approval_needed
                                              └─► action.auto_execute
                                                    └─► Agent 08 (workflow_executor)

Agent 09 (audit_trail) — listens ALL 8 topics, append-only writes
```

**Key parallelism**: Agents 04 and 05 both subscribe to `anomaly.detected` and run concurrently. Net latency = `max(LLM, scoring)` not the sum.

---

## Scoring model

```
AS  = (FI × 0.40) + (FR × 0.25) + (RE × 0.20) + (SR × 0.15)   [range 1–10]
APS = AS × confidence / complexity                               [range 0–10]

Approval routing condition:
  APS >= 4.0  AND  complexity >= 2  →  action.approval_needed
  else                              →  action.auto_execute
```

**Complexity tiers** (by amount in INR):
- `< ₹50K` → 1 (fully autonomous)
- `₹50K–₹2L` → 2 (Slack approval)
- `₹2L–₹10L` → 3 (Finance Head)
- `> ₹10L` → 5 (Board level)

**Recoverability by type**: `duplicate_payment=10`, `cloud_waste=9`, `unused_saas=8.5`, `vendor_rate_anomaly=7`, `sla_penalty_risk=4`

---

## File map

```
agents/
  agent_01_data_connector.py      Pydantic validate → publish raw.spend
  agent_02_normalization.py       Category map, INR currency, SHA256 dedup
  agent_03_anomaly_detection.py   IForest (retrain every 20 records, 8% contamination) + 5 rules
  agent_04_root_cause.py          LangChain → Gemini, pgvector similar anomaly lookup
  agent_05_prioritization.py      score_anomaly() → AS/APS
  agent_06_merge.py               asyncio.Lock dual buffers, 30s TTL, persists to DB
  agent_07_action_dispatcher.py   requires_approval() → route to approval/auto topic
  agent_08_workflow_executor.py   Simulated recovery execution, execute_approved() for API
  agent_09_audit_trail.py         Append-only audit_log inserts, subscribes all topics

api/
  app.py                          FastAPI factory + lifespan (init_db → 9 agents → bus.start())
  routes/health.py                GET /health
  routes/ingest.py                POST /ingest/demo|record|batch
  routes/anomalies.py             GET /anomalies, GET /anomalies/pending-approval, POST approve
  routes/synthetic_data.py        GET /synthetic/data (JSON), GET /synthetic/download (CSV)
  routes/process_logs.py          GET /logs, GET /logs/processes, GET /logs/{process_id}
  routes/bus_events.py            GET /bus/events
  routes/audit.py                 GET /audit
  routes/summary.py               GET /summary (CFO view, supports ?process_id= filter)

core/
  bus.py                          EventBus: asyncio.Queue per topic, fan-out, ring-buffer history
  db.py                           Engine init, get_session(), CRUD helpers
  llm.py                          LangChain chain builder, Gemini fallback, tenacity retry
  scoring.py                      Pure Python AS/APS scoring (<1ms, no deps)
  vector_store.py                 embed_text(), store_anomaly_embedding(), find_similar_anomalies()

data/
  synthetic_generator.py          80 records, 15 vendors, 6 categories, 5 injected anomaly types

models/
  events.py                       Event(event_id, topic, source_agent, process_id, payload, ts)
  orm.py                          6 SQLAlchemy tables (see DB schema below)
  schemas.py                      All Pydantic request/response schemas

ui/
  streamlit_app.py                Home page + architecture diagram
  components/api_client.py        Sync requests wrapper for all endpoints
  components/agent_status_card.py 9-agent activity grid (3-col, color-coded)
  components/anomaly_card.py      Expandable anomaly detail card with approve button
  pages/01_input.py               Mode A: synthetic (slider/preview/download/run)
                                  Mode B: CSV upload or st.data_editor manual entry
  pages/02_pipeline.py            Live agent grid, event feed, execution log, auto-refresh
  pages/03_anomalies.py           KPI row, 3 charts, filterable table, Approval Gate
  pages/04_process_logs.py        Gantt waterfall, step table, JSON payload inspector
  pages/05_summary.py             Recovery metrics, breakdown charts, agent health table

run.py                            uvicorn factory entry point (--host/--port/--reload flags)
run_ui.py                         Streamlit entry point (sets API_BASE_URL env, --dark theme)
```

---

## Database schema (6 tables)

| Table | Key columns |
|-------|-------------|
| `spend_records` | record_id, vendor, amount, currency, department, category, transaction_date, source, content_hash (SHA256 dedup) |
| `anomalies` | anomaly_id, process_id, anomaly_type, isolation_score, rule_flags (JSONB), root_cause, confidence, as_score, aps_score, complexity, approval_needed, status |
| `audit_log` | log_id (BigInt), event_id, topic, source_agent, process_id, anomaly_id, payload_summary (JSONB) — **NEVER UPDATE/DELETE** |
| `watermarks` | source_id, last_cursor, records_ingested |
| `anomaly_embeddings` | embedding_id, anomaly_id, embedding (Vector(1536)), source_text |
| `process_logs` | log_id (BigInt), **process_id**, agent_name, event_id, topic_in, topic_out, input_payload (JSONB), output_payload (JSONB), status, error_message, started_at, completed_at, duration_ms |

**process_id** is a UUID assigned per ingestion batch. Every Event carries it. All 9 agents write correlated `process_logs` rows keyed to it — enables full pipeline trace reconstruction.

---

## Environment variables

| Var | Default | Notes |
|-----|---------|-------|
| `DATABASE_URL` | — | `postgresql+asyncpg://user:pass@host:5432/db` |
| `GOOGLE_API_KEY` | — | Gemini API key (aistudio.google.com) |
| `LLM_MODEL_PRIMARY` | `gemini-2.5-flash` | Agent 04 primary |
| `LLM_MODEL_FALLBACK` | `gemini-1.5-flash` | Auto-fallback via LangChain |
| `LLM_TEMPERATURE` | `0.1` | |
| `OPENAI_API_KEY` | — | For `text-embedding-3-small` only |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | pgvector dimension = 1536 |
| `EVENT_BUS_BACKEND` | `memory` | `memory` or `redis` (swappable interface) |
| `EVENT_BUS_HISTORY_SIZE` | `2000` | Ring buffer size |
| `APS_APPROVAL_THRESHOLD` | `4.0` | |
| `COMPLEXITY_APPROVAL_THRESHOLD` | `2` | |
| `APP_HOST` | `0.0.0.0` | |
| `APP_PORT` | `8000` | |
| `API_BASE_URL` | `http://localhost:8000` | UI reads this |
| `SYNTHETIC_RECORD_COUNT` | `86` | |
| `SYNTHETIC_SEED` | `42` | |

---

## Synthetic data injected anomalies

| Type | Vendor | Notes |
|------|--------|-------|
| `duplicate_payment` ×2 | AWS | Fully reversible (RE=10) |
| `cloud_waste` | GCP | Can right-size (RE=9) |
| `unused_saas` | Slack | Can deprovision (RE=8.5) |
| `vendor_rate_anomaly` | Infosys | Z-score > 2.5 rule |
| `sla_penalty_risk` | Tata | Partial avoidance (RE=4) |

15 vendors, 6 categories: Cloud Infra, SaaS, Professional Services, Telecom, Office & Facilities, Hardware.

---

## Key design decisions to remember

1. **No orchestrator** — agents subscribe independently; adding a new agent = zero changes to existing agents.
2. **Agent 06 Merge** uses `asyncio.Lock` + dual buffers + 30s TTL. If one upstream fails, TTL prevents infinite wait.
3. **pgvector over Chroma/Qdrant** — single PostgreSQL instance, no extra infra.
4. **LangChain `with_fallbacks()`** handles Gemini model rotation transparently. tenacity wraps outer call.
5. **`set_data_connector()` injection** — `api/routes/ingest.py` uses a module-level setter so the lifespan-created agent instance is shared with request handlers.
6. **Approval routing**: `APS >= 4.0 AND complexity >= 2` — both conditions must be true.
7. **CFO Summary** exposes `?process_id=` query param — filters all anomaly/agent stats to a single run.
8. **Event bus** has a `deque`-based ring buffer history (configurable size). `GET /bus/events` exposes this.

---

## Current status (last updated: April 2026)

- ✅ All 9 agents implemented and wired
- ✅ Full FastAPI backend (8 route files, 14 endpoints)
- ✅ 5 Streamlit pages + home screen
- ✅ Scoring engine (pure Python, deterministic)
- ✅ pgvector similarity search
- ✅ Synthetic data generator
- ✅ README.md pushed to GitHub
- ✅ Repo: https://github.com/rish106-hub/CostSense

## Known limitations / future work
- `agent_08_workflow_executor.py` simulates execution (no real API calls to vendors)
- `EVENT_BUS_BACKEND=redis` interface exists but Redis implementation is a stub
- No authentication on FastAPI endpoints (add before production use)
- `source_stats` in `/summary` response is always empty `{}` — not yet implemented
- Test suite scaffolded but not populated (pytest + pytest-asyncio in requirements)

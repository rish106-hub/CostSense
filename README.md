# CostSense AI

> Autonomous cost intelligence platform — detects enterprise spend anomalies, scores them by financial impact, and either auto-executes resolutions or routes high-stakes decisions to a human approver.

Built for the **ET Gen AI Hackathon 2026**.

---

## Overview

Enterprise finance teams lose millions annually to duplicate vendor payments, cloud waste, unused SaaS licences, and undetected rate anomalies. By the time these surface in quarterly reviews, the money is gone.

**CostSense AI** catches them in real time.

Spend data flows through a nine-agent choreography pipeline. Each agent subscribes to a topic on an in-memory event bus, processes its slice of work, and publishes a new event — no central orchestrator, no bottlenecks. High-impact anomalies are automatically resolved. Complex, high-value ones are surfaced to a CFO approval gate before any action is taken. Every step is logged, traceable, and inspectable via a Streamlit UI.

---

## Architecture

```
POST /ingest/*
       │
       ▼
┌─────────────────────┐
│  Agent 01           │  Data Connector — validates, enriches, publishes
│  raw.spend ─────────┼──────────────────────────────────────────────────►
└─────────────────────┘
                                ▼
                       ┌─────────────────────┐
                       │  Agent 02           │  Normalization — category map,
                       │  normalized.spend ──┼─ currency → INR, deduplication
                       └─────────────────────┘
                                ▼
                       ┌─────────────────────┐
                       │  Agent 03           │  Anomaly Detection — IForest ML
                       │  anomaly.detected ──┼─ + rule engine (5 rule types)
                       └─────────────────────┘
                            ╱           ╲
               ┌────────────┐           ┌────────────┐
               │  Agent 04  │           │  Agent 05  │  ← run in PARALLEL
               │  Root Cause│           │  Scoring   │
               │  (LLM)     │           │  (APS)     │
               │  anomaly   │           │  anomaly   │
               │  .enriched │           │  .scored   │
               └─────┬──────┘           └──────┬─────┘
                     └──────────┬──────────────┘
                                ▼
                       ┌─────────────────────┐
                       │  Agent 06           │  Merge — waits for both, TTL
                       │  anomaly.ready ─────┼─ cleanup, persists to DB
                       └─────────────────────┘
                                ▼
                       ┌─────────────────────┐
                       │  Agent 07           │  Action Dispatcher
                       │  action.*  ─────────┼─ APS ≥ 4.0 + complexity ≥ 2
                       └─────────────────────┘  → approval | else auto-execute
                            ╱           ╲
               ┌────────────┐           ┌────────────┐
               │  Agent 08  │           │  Agent 08  │
               │  Approval  │           │  Auto-exec │
               └────────────┘           └────────────┘

Agent 09 (Audit Trail) — passively listens to ALL 8 topics, append-only
```

### Scoring Model

| Dimension | Weight | Signal |
|-----------|--------|--------|
| Financial Impact (FI) | 40% | Amount vs. vendor/category baseline |
| Frequency Rank (FR) | 25% | How often this anomaly type recurs |
| Recoverability (RE) | 20% | Likelihood of recovering the spend |
| Severity Risk (SR) | 15% | Rule confidence + ML isolation score |

```
AS  = (FI × 0.40) + (FR × 0.25) + (RE × 0.20) + (SR × 0.15)   [1–10]
APS = AS × confidence / complexity                                [0–10]

Route to approval gate when:  APS ≥ 4.0  AND  complexity ≥ 2
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + uvicorn |
| Agents | Python asyncio — choreography via `asyncio.Queue` event bus |
| LLM | Google Gemini 2.5 Flash (via LangChain + fallback chain) |
| Anomaly Detection | PyOD IsolationForest + 5-rule engine |
| Database | PostgreSQL (SQLAlchemy async) |
| Vector Search | pgvector — cosine similarity for similar-anomaly retrieval |
| UI | Streamlit + Plotly |
| Config | Pydantic Settings + python-dotenv |

---

## Project Structure

```
costsense/
├── agents/
│   ├── agent_01_data_connector.py      # Ingestion + validation
│   ├── agent_02_normalization.py       # Category mapping, dedup, currency
│   ├── agent_03_anomaly_detection.py   # IForest ML + 5 rule detectors
│   ├── agent_04_root_cause.py          # LLM root cause (LangChain + Gemini)
│   ├── agent_05_prioritization.py      # AS / APS scoring
│   ├── agent_06_merge.py               # Merge enriched + scored events
│   ├── agent_07_action_dispatcher.py   # Route to approval or auto-execute
│   ├── agent_08_workflow_executor.py   # Execute / simulate recovery actions
│   └── agent_09_audit_trail.py         # Append-only audit log (all topics)
│
├── api/
│   ├── app.py                          # FastAPI factory + lifespan handler
│   └── routes/
│       ├── health.py                   # GET /health
│       ├── ingest.py                   # POST /ingest/demo|record|batch
│       ├── anomalies.py                # GET /anomalies, POST approve
│       ├── synthetic_data.py           # GET /synthetic/data|download
│       ├── process_logs.py             # GET /logs, /logs/{process_id}
│       ├── bus_events.py               # GET /bus/events
│       ├── audit.py                    # GET /audit
│       └── summary.py                  # GET /summary
│
├── core/
│   ├── bus.py                          # Event bus (asyncio.Queue + ring buffer)
│   ├── db.py                           # DB engine, session, CRUD helpers
│   ├── llm.py                          # LangChain chain builder + retry logic
│   ├── scoring.py                      # Deterministic AS/APS scoring engine
│   └── vector_store.py                 # pgvector embed + similarity search
│
├── data/
│   └── synthetic_generator.py          # 80-record synthetic spend dataset
│
├── models/
│   ├── events.py                       # Event Pydantic model + topic registry
│   ├── orm.py                          # SQLAlchemy ORM (6 tables)
│   └── schemas.py                      # FastAPI request/response schemas
│
├── ui/
│   ├── streamlit_app.py                # Home page + architecture overview
│   ├── components/
│   │   ├── api_client.py               # Sync HTTP wrapper for all endpoints
│   │   ├── agent_status_card.py        # 9-agent activity grid component
│   │   └── anomaly_card.py             # Expandable anomaly detail card
│   └── pages/
│       ├── 01_input.py                 # Synthetic data + CSV/manual input
│       ├── 02_pipeline.py              # Live pipeline + event feed
│       ├── 03_anomalies.py             # Anomaly dashboard + approval gate
│       ├── 04_process_logs.py          # Per-agent trace + payload inspector
│       └── 05_summary.py              # CFO executive summary
│
├── run.py                              # FastAPI entry point (uvicorn)
├── run_ui.py                           # Streamlit entry point
├── requirements.txt
└── .env.example
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `spend_records` | Normalised spend transactions (deduplicated by content hash) |
| `anomalies` | Detected anomalies with AS / APS scores, root cause, status |
| `audit_log` | Append-only event trail — one row per agent-event pair |
| `process_logs` | Per-agent input/output trace, keyed by `process_id` |
| `anomaly_embeddings` | pgvector(1536) embeddings for semantic similarity search |
| `watermarks` | Incremental ingestion state per data source |

Every event carries a shared `process_id` UUID so all 9 agents' log entries for a single ingestion batch can be reconstructed as a complete trace.

---

## Quickstart

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ with the `pgvector` extension
- Google Gemini API key — [get one free](https://aistudio.google.com/app/apikey)
- OpenAI API key (for text embeddings only)

### 2. Clone and install

```bash
git clone https://github.com/rish106-hub/CostSense.git
cd CostSense
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and set:
#   DATABASE_URL  — your PostgreSQL connection string
#   GOOGLE_API_KEY — Gemini key
#   OPENAI_API_KEY — for embeddings
```

### 4. Provision the database

```sql
-- In psql:
CREATE USER costsense_user WITH PASSWORD 'your_password_here';
CREATE DATABASE costsense_db OWNER costsense_user;
\c costsense_db
CREATE EXTENSION IF NOT EXISTS vector;
```

Tables are created automatically on first startup.

### 5. Run the API

```bash
python run.py
# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### 6. Run the UI

```bash
python run_ui.py
# UI available at http://localhost:8501
```

---

## UI Pages

### Data Input (`/01_input`)
Two input modes:
- **Synthetic** — configure record count and seed, preview the generated dataset, download as CSV, then fire the full pipeline with one click
- **Custom** — upload a CSV or enter rows manually via an editable table; column validation runs before ingestion

### Live Pipeline (`/02_pipeline`)
- Nine agent status cards — lights up as each agent processes
- Event bus topology with per-topic event counts
- Scrolling event feed (last 50 events)
- Full execution log for the selected process run
- Optional auto-refresh (1–10 second interval)

### Anomaly Dashboard (`/03_anomalies`)
- KPIs: total anomalies, pending approval, auto-executed, total exposure (₹)
- Three charts: breakdown by type, exposure by type, APS distribution
- Filterable table with sortable APS scores
- Expandable detail cards per anomaly
- **Approval Gate** — shows only `pending_approval` anomalies; CFO can approve with notes

### Process Logs (`/04_process_logs`)
- Process run selector (most recent first)
- Gantt waterfall chart — per-agent execution timeline with colour-coded status
- Step-by-step log table with row selection
- **Payload Inspector** — click any row to see the exact JSON the agent received and published

### CFO Summary (`/05_summary`)
- Recovery impact metrics: total exposure, recovered, pending, recovery rate
- Anomaly breakdown bar chart + status pie chart
- Highest-priority anomaly card
- Agent health table (events, errors, avg latency)
- Data source breakdown

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness check + event bus stats |
| `GET` | `/synthetic/data` | Generate synthetic spend records (JSON) |
| `GET` | `/synthetic/download` | Download synthetic data as CSV |
| `POST` | `/ingest/demo` | Run full pipeline on built-in synthetic data |
| `POST` | `/ingest/record` | Ingest a single spend record |
| `POST` | `/ingest/batch` | Ingest a batch of spend records |
| `GET` | `/anomalies` | List anomalies (filter by status, process_id) |
| `GET` | `/anomalies/pending-approval` | Anomalies awaiting CFO sign-off |
| `POST` | `/anomalies/{id}/approve` | Approve and trigger execution |
| `GET` | `/logs` | All process log entries |
| `GET` | `/logs/processes` | List distinct process runs |
| `GET` | `/logs/{process_id}` | Full trace for a specific process |
| `GET` | `/bus/events` | Recent event bus history |
| `GET` | `/audit` | Append-only audit trail |
| `GET` | `/summary` | CFO summary stats |

Full interactive docs: `http://localhost:8000/docs`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | — | PostgreSQL connection string (asyncpg driver) |
| `GOOGLE_API_KEY` | — | Gemini API key for LLM root cause analysis |
| `LLM_MODEL_PRIMARY` | `gemini-2.5-flash` | Primary Gemini model |
| `LLM_MODEL_FALLBACK` | `gemini-1.5-flash` | Fallback if primary fails |
| `LLM_TEMPERATURE` | `0.1` | LLM sampling temperature |
| `OPENAI_API_KEY` | — | OpenAI key for `text-embedding-3-small` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model for pgvector |
| `EVENT_BUS_BACKEND` | `memory` | `memory` or `redis` |
| `EVENT_BUS_HISTORY_SIZE` | `2000` | Ring buffer size for bus events |
| `APS_APPROVAL_THRESHOLD` | `4.0` | APS score above which approval is required |
| `COMPLEXITY_APPROVAL_THRESHOLD` | `2` | Minimum complexity level for approval routing |
| `APP_HOST` | `0.0.0.0` | API server bind host |
| `APP_PORT` | `8000` | API server port |
| `API_BASE_URL` | `http://localhost:8000` | UI → API base URL |
| `SYNTHETIC_RECORD_COUNT` | `86` | Default synthetic dataset size |
| `SYNTHETIC_SEED` | `42` | RNG seed for reproducible synthetic data |

---

## Synthetic Data

The built-in generator produces realistic enterprise spend with injected anomalies:

| Injected Anomaly | Vendor | Type |
|-----------------|--------|------|
| Duplicate payment (×2) | AWS | `duplicate_payment` |
| Cloud waste | GCP | `cloud_waste` |
| Unused SaaS | Slack | `unused_saas` |
| Rate anomaly | Infosys | `vendor_rate_anomaly` |
| SLA penalty risk | Tata | `sla_penalty_risk` |

15 vendors across 6 categories (Cloud Infrastructure, SaaS, Professional Services, Telecom, Office & Facilities, Hardware).

---

## Key Design Decisions

**Choreography over orchestration** — agents subscribe independently; adding a new agent requires zero changes to existing agents.

**Parallel agents 4 & 5** — root cause (LLM, ~2–4s) and scoring (<1ms) both subscribe to `anomaly.detected`. Pipeline latency = `max(LLM_time, scoring_time)`, not the sum.

**Merge agent with TTL** — Agent 6 holds dual asyncio-safe buffers with a 30-second TTL. If one upstream agent fails, the TTL prevents infinite waits.

**pgvector over a separate vector DB** — keeps infrastructure to a single PostgreSQL instance; no Chroma/Qdrant to manage.

**Process ID propagation** — every `Event` carries a `process_id` UUID. All 9 agents write correlated `process_logs` rows, enabling complete per-ingestion trace reconstruction without joins across tables.

**LangChain fallback chain** — `chain.with_fallbacks([fallback_chain])` handles model rotation transparently; tenacity wraps the outer call for retry logic.

---

## Running Tests

```bash
pytest -v
```

---

## License

MIT

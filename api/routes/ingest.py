"""
POST /ingest/demo   — run 86-record synthetic pipeline
POST /ingest/record — ingest a single spend record
POST /ingest/batch  — ingest a list of spend records (CSV upload or JSON body)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from agents.agent_01_data_connector import DataConnectorAgent
from data.synthetic_generator import generate_spend_records
from models.schemas import IngestBatchOut, IngestDemoOut, IngestRecordOut, SpendRecordIn

router = APIRouter(prefix="/ingest", tags=["ingest"])

# Agent 1 instance — injected at app startup via app state
_data_connector: DataConnectorAgent | None = None


def set_data_connector(agent: DataConnectorAgent) -> None:
    """Called at startup to inject the agent instance."""
    global _data_connector
    _data_connector = agent


def _get_connector() -> DataConnectorAgent:
    if _data_connector is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    return _data_connector


class IngestDemoRequest(BaseModel):
    n: int = 86
    seed: int = 42
    include_anomalies: bool = True


@router.post("/demo", response_model=IngestDemoOut)
async def ingest_demo(body: IngestDemoRequest = IngestDemoRequest()):
    """
    Load the synthetic dataset and push it through the full pipeline.
    Returns immediately — processing happens asynchronously via the event bus.
    """
    connector = _get_connector()
    process_id = str(uuid.uuid4())

    records = generate_spend_records(
        n=body.n,
        seed=body.seed,
        include_anomalies=body.include_anomalies,
    )

    # Fire and forget — pipeline runs in background via event bus
    import asyncio
    asyncio.create_task(connector.ingest_batch(records, process_id))

    return IngestDemoOut(
        message=f"Ingesting {len(records)} records — pipeline running asynchronously.",
        process_id=process_id,
        records=len(records),
    )


@router.post("/record", response_model=IngestRecordOut)
async def ingest_single_record(record: SpendRecordIn):
    """Ingest a single spend record and push it through the pipeline."""
    connector = _get_connector()
    process_id = str(uuid.uuid4())

    record_dict = record.model_dump()
    # Assign record_id and content_hash
    import hashlib, json
    record_dict["record_id"] = str(uuid.uuid4())
    key = json.dumps({
        "vendor": record_dict["vendor"],
        "amount": record_dict["amount"],
        "invoice_number": record_dict.get("invoice_number") or "",
        "transaction_date": record_dict["transaction_date"],
    }, sort_keys=True)
    record_dict["content_hash"] = hashlib.sha256(key.encode()).hexdigest()

    event_id = await connector.ingest_record(record_dict, process_id)

    return IngestRecordOut(
        message="Record submitted to pipeline.",
        process_id=process_id,
        record_id=record_dict["record_id"],
    )


@router.post("/batch", response_model=IngestBatchOut)
async def ingest_batch(records: list[SpendRecordIn]):
    """
    Ingest a list of spend records. Accepts JSON array body.
    All records in the batch share a single process_id for tracing.
    """
    connector = _get_connector()
    process_id = str(uuid.uuid4())

    import hashlib, json, asyncio

    record_dicts = []
    for r in records:
        d = r.model_dump()
        d["record_id"] = str(uuid.uuid4())
        key = json.dumps({
            "vendor": d["vendor"],
            "amount": d["amount"],
            "invoice_number": d.get("invoice_number") or "",
            "transaction_date": d["transaction_date"],
        }, sort_keys=True)
        d["content_hash"] = hashlib.sha256(key.encode()).hexdigest()
        record_dicts.append(d)

    asyncio.create_task(connector.ingest_batch(record_dicts, process_id))

    return IngestBatchOut(
        message=f"Batch of {len(record_dicts)} records submitted to pipeline.",
        process_id=process_id,
        records_submitted=len(record_dicts),
        records_skipped=0,
    )

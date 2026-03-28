"""
Agent 2 — Normalization

Subscribes to raw.spend. Cleans, deduplicates, and categorizes records
into a unified schema, then persists to spend_records and publishes to normalized.spend.

Subscribes to: raw.spend
Publishes to:  normalized.spend
Uses LLM:      No
Latency:       < 1ms per record
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

import structlog

from core.bus import EventBus
from core.db import get_session_factory, insert_spend_record, insert_process_log
from models.events import Event

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_02_normalization"
TOPIC_IN = "raw.spend"
TOPIC_OUT = "normalized.spend"

# Category normalization map: raw → normalized
CATEGORY_MAP = {
    "cloud": "cloud",
    "cloud_infra": "cloud",
    "aws": "cloud",
    "gcp": "cloud",
    "azure": "cloud",
    "saas": "saas",
    "saas_subscription": "saas",
    "software": "saas",
    "external_services": "external_services",
    "consulting": "external_services",
    "vendor_payment": "external_services",
    "outsourcing": "external_services",
    "people": "people",
    "payroll": "people",
    "hr": "people",
    "staffing": "people",
    "overhead": "overhead",
    "office": "overhead",
    "travel": "overhead",
    "marketing": "overhead",
    "facilities": "overhead",
    "utilities": "overhead",
}

# Currency normalization (convert to INR)
CURRENCY_CONVERSION = {
    "USD": 83.5,
    "EUR": 90.2,
    "GBP": 105.4,
    "INR": 1.0,
}


class NormalizationAgent:
    """
    Cleans raw spend records and publishes normalized versions.
    Persists records to PostgreSQL and deduplicates via content_hash.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(TOPIC_IN, self.handle)

    async def handle(self, event: Event) -> None:
        """Process one raw.spend event."""
        started_at = datetime.now(timezone.utc)
        raw = event.payload

        try:
            normalized = self._normalize(raw)
            if normalized is None:
                # Malformed record — skip
                await self._log(event, None, "skipped", "malformed_record", started_at)
                return

            # Persist to DB (deduplication handled by content_hash UNIQUE constraint)
            factory = get_session_factory()
            async with factory() as session:
                record_row = await insert_spend_record(session, normalized)
                normalized["record_id"] = record_row.record_id

            # Publish normalized record downstream
            published_event = await self._bus.publish(
                topic=TOPIC_OUT,
                source_agent=AGENT_NAME,
                process_id=event.process_id,
                payload=normalized,
            )

            await self._log(event, published_event, "success", None, started_at, normalized)

        except Exception as exc:
            logger.error("agent02.error", event_id=event.event_id, error=str(exc))
            await self._log(event, None, "error", str(exc), started_at)

    def _normalize(self, raw: dict) -> Optional[dict]:
        """
        Apply all normalization rules to a raw spend record.
        Returns None if the record is too malformed to process.
        """
        vendor = (raw.get("vendor") or "").strip()
        amount_raw = raw.get("amount")
        if not vendor or amount_raw is None:
            return None

        try:
            amount = float(amount_raw)
        except (ValueError, TypeError):
            return None

        if amount <= 0:
            return None

        # Currency normalization — convert to INR
        currency = str(raw.get("currency", "INR")).upper().strip()
        rate = CURRENCY_CONVERSION.get(currency, 1.0)
        amount_inr = round(amount * rate, 2)

        # Category normalization
        raw_category = str(raw.get("category", "overhead")).lower().strip()
        normalized_category = CATEGORY_MAP.get(raw_category, "overhead")

        # Department — trim whitespace
        department = str(raw.get("department", "General")).strip()

        # Transaction date — ensure ISO format
        txn_date = self._normalize_date(raw.get("transaction_date"))

        # Build content hash for dedup
        content_hash = self._compute_hash(vendor, amount_inr, raw.get("invoice_number"), txn_date)

        return {
            "record_id": raw.get("record_id"),
            "vendor": vendor,
            "amount": amount_inr,
            "currency": "INR",
            "department": department,
            "category": normalized_category,
            "transaction_date": txn_date,
            "source": str(raw.get("source", "manual")).strip(),
            "invoice_number": (raw.get("invoice_number") or "").strip() or None,
            "description": (raw.get("description") or "").strip() or None,
            "content_hash": content_hash,
        }

    @staticmethod
    def _normalize_date(date_value) -> str:
        """Attempt to parse various date formats and return ISO YYYY-MM-DD."""
        if not date_value:
            return datetime.now(timezone.utc).date().isoformat()
        date_str = str(date_value).strip()
        # Already ISO format
        if len(date_str) >= 10 and date_str[4] == "-":
            return date_str[:10]
        # Try common formats
        for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d"):
            try:
                from datetime import datetime as dt
                return dt.strptime(date_str[:10], fmt).date().isoformat()
            except ValueError:
                continue
        return datetime.now(timezone.utc).date().isoformat()

    @staticmethod
    def _compute_hash(
        vendor: str, amount: float, invoice_number, txn_date: str
    ) -> str:
        key = json.dumps(
            {
                "vendor": vendor,
                "amount": amount,
                "invoice_number": invoice_number or "",
                "transaction_date": txn_date,
            },
            sort_keys=True,
        )
        return hashlib.sha256(key.encode()).hexdigest()

    async def _log(
        self,
        event: Event,
        published_event,
        status: str,
        error_message: Optional[str],
        started_at: datetime,
        output_payload: Optional[dict] = None,
    ) -> None:
        try:
            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            factory = get_session_factory()
            async with factory() as session:
                await insert_process_log(session, {
                    "process_id": event.process_id,
                    "agent_name": AGENT_NAME,
                    "event_id": event.event_id,
                    "topic_in": TOPIC_IN,
                    "topic_out": TOPIC_OUT if status == "success" else None,
                    "record_id": event.payload.get("record_id"),
                    "anomaly_id": None,
                    "input_payload": event.payload,
                    "output_payload": output_payload,
                    "status": status,
                    "error_message": error_message,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": duration_ms,
                })
        except Exception as log_exc:
            logger.warning("agent02.log_failed", error=str(log_exc))

"""
Agent 3 — Anomaly Detection

Subscribes to normalized.spend. Runs two complementary detection methods:
  1. PyOD IsolationForest (ML) — retrained every 20 records
  2. Deterministic rule checks:
     - duplicate_payment: same invoice_number seen twice
     - vendor_rate_spike: z-score > 2.5 vs rolling vendor history
     - round_number_amount: suspiciously round amounts (Rs 100K, 500K, etc.)
     - weekend_transaction: transactions on Saturday/Sunday

Publishes to anomaly.detected only if isolation_score < -0.1 OR any rule fires.

Subscribes to: normalized.spend
Publishes to:  anomaly.detected
Uses LLM:      No
Latency:       < 5ms per record (after model trained)
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import structlog

from core.bus import EventBus
from core.db import get_session_factory, insert_process_log
from models.events import Event

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_03_anomaly_detection"
TOPIC_IN = "normalized.spend"
TOPIC_OUT = "anomaly.detected"

# IsolationForest configuration
IFOREST_MIN_SAMPLES = 10        # Minimum records before training
IFOREST_RETRAIN_EVERY = 20      # Retrain every N new records
IFOREST_CONTAMINATION = 0.08    # Expected fraction of anomalies
IFOREST_ANOMALY_THRESHOLD = -0.05  # score_samples below this = anomaly

# Rule thresholds
ZSCORE_SPIKE_THRESHOLD = 2.5    # Z-score for vendor rate spike


class AnomalyDetectionAgent:
    """
    Stateful agent that buffers records, trains an IsolationForest model,
    and applies rule-based checks to detect anomalies.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(TOPIC_IN, self.handle)

        # Buffer of normalized records (as feature vectors) for ML training
        self._record_buffer: list[dict] = []
        self._model = None  # PyOD IsolationForest instance
        self._records_since_retrain = 0

        # Per-vendor history for z-score spike detection
        self._vendor_history: dict[str, list[float]] = defaultdict(list)
        # Invoice number seen count for duplicate detection
        self._invoice_seen: dict[str, int] = defaultdict(int)

    async def handle(self, event: Event) -> None:
        """Process one normalized.spend event."""
        started_at = datetime.now(timezone.utc)
        record = event.payload

        try:
            # Update per-vendor history
            vendor = record.get("vendor", "unknown")
            amount = float(record.get("amount", 0))
            self._vendor_history[vendor].append(amount)

            # Update invoice seen counter
            invoice_num = record.get("invoice_number") or ""
            if invoice_num:
                self._invoice_seen[invoice_num] += 1

            # Update model buffer
            self._record_buffer.append(record)
            self._records_since_retrain += 1

            # Retrain model when buffer is large enough
            if (
                len(self._record_buffer) >= IFOREST_MIN_SAMPLES
                and self._records_since_retrain >= IFOREST_RETRAIN_EVERY
            ):
                self._retrain_model()
                self._records_since_retrain = 0

            # Compute isolation score
            isolation_score = self._compute_isolation_score(record)

            # Run rule-based checks
            rule_flags = self._run_rule_checks(record)

            # Determine if this is an anomaly
            is_anomaly = (
                (isolation_score is not None and isolation_score < IFOREST_ANOMALY_THRESHOLD)
                or len(rule_flags) > 0
            )

            if not is_anomaly:
                await self._log(event, None, "skipped", None, started_at)
                return

            # Determine anomaly type from most specific signal
            anomaly_type = self._classify_anomaly_type(rule_flags, isolation_score)

            # Estimate confidence
            confidence = self._estimate_confidence(rule_flags, isolation_score)

            anomaly_id = str(uuid.uuid4())
            payload = {
                "anomaly_id": anomaly_id,
                "record_id": record.get("record_id"),
                "process_id": event.process_id,
                "anomaly_type": anomaly_type,
                "isolation_score": isolation_score,
                "rule_flags": rule_flags,
                "confidence": confidence,
                # Denormalized spend record fields for downstream agents
                "vendor": vendor,
                "amount": amount,
                "currency": record.get("currency", "INR"),
                "department": record.get("department"),
                "category": record.get("category"),
                "transaction_date": record.get("transaction_date"),
                "invoice_number": record.get("invoice_number"),
                "description": record.get("description"),
            }

            published_event = await self._bus.publish(
                topic=TOPIC_OUT,
                source_agent=AGENT_NAME,
                process_id=event.process_id,
                payload=payload,
            )

            logger.info(
                "agent03.anomaly_detected",
                anomaly_type=anomaly_type,
                vendor=vendor,
                amount=amount,
                confidence=confidence,
            )

            await self._log(event, published_event, "success", None, started_at, payload)

        except Exception as exc:
            logger.error("agent03.error", event_id=event.event_id, error=str(exc))
            await self._log(event, None, "error", str(exc), started_at)

    # ------------------------------------------------------------------
    # ML detection
    # ------------------------------------------------------------------

    def _retrain_model(self) -> None:
        """Train PyOD IsolationForest on the current record buffer."""
        try:
            from pyod.models.iforest import IForest

            X = self._build_feature_matrix(self._record_buffer)
            if X.shape[0] < IFOREST_MIN_SAMPLES:
                return

            model = IForest(contamination=IFOREST_CONTAMINATION, random_state=42)
            model.fit(X)
            self._model = model
            logger.debug("agent03.model_retrained", n_samples=X.shape[0])
        except Exception as exc:
            logger.warning("agent03.retrain_failed", error=str(exc))

    def _compute_isolation_score(self, record: dict) -> Optional[float]:
        """
        Compute isolation score for a single record.
        Returns None if model is not yet trained.
        """
        if self._model is None:
            return None
        try:
            X = self._build_feature_matrix([record])
            # decision_function returns negative scores for anomalies
            score = float(self._model.decision_function(X)[0])
            return round(score, 6)
        except Exception:
            return None

    @staticmethod
    def _build_feature_matrix(records: list[dict]) -> "np.ndarray":
        """Convert records to a numeric feature matrix for IsolationForest."""
        features = []
        for r in records:
            amount = float(r.get("amount", 0))
            # Day of week (0=Monday, 6=Sunday)
            try:
                from datetime import date
                txn_date = date.fromisoformat(str(r.get("transaction_date", "2024-01-01"))[:10])
                day_of_week = txn_date.weekday()
            except (ValueError, AttributeError):
                day_of_week = 0

            # Category encoded as integer
            category_map = {"cloud": 0, "saas": 1, "external_services": 2, "people": 3, "overhead": 4}
            category_code = category_map.get(r.get("category", "overhead"), 4)

            features.append([amount, day_of_week, category_code])

        return np.array(features, dtype=np.float64)

    # ------------------------------------------------------------------
    # Rule-based detection
    # ------------------------------------------------------------------

    def _run_rule_checks(self, record: dict) -> list[str]:
        """Run all deterministic rules. Returns list of triggered rule names."""
        flags = []

        # Rule 1: Duplicate payment — same invoice number seen more than once
        invoice_num = record.get("invoice_number") or ""
        if invoice_num and self._invoice_seen.get(invoice_num, 0) > 1:
            flags.append("duplicate_payment")

        # Rule 2: Vendor rate spike — z-score > threshold
        vendor = record.get("vendor", "")
        amount = float(record.get("amount", 0))
        vendor_history = self._vendor_history.get(vendor, [])
        if len(vendor_history) >= 3:
            mean = np.mean(vendor_history[:-1])  # Exclude current record
            std = np.std(vendor_history[:-1])
            if std > 0:
                z_score = abs(amount - mean) / std
                if z_score > ZSCORE_SPIKE_THRESHOLD:
                    flags.append("vendor_rate_spike")

        # Rule 3: Round number amount (potential fraud signal)
        if amount > 50_000 and amount % 100_000 == 0:
            flags.append("round_number_amount")

        # Rule 4: Weekend transaction
        txn_date_str = str(record.get("transaction_date", ""))
        if txn_date_str:
            try:
                from datetime import date
                txn_date = date.fromisoformat(txn_date_str[:10])
                if txn_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                    flags.append("weekend_transaction")
            except ValueError:
                pass

        return flags

    @staticmethod
    def _classify_anomaly_type(rule_flags: list[str], isolation_score: Optional[float]) -> str:
        """Map rule flags to a canonical anomaly type."""
        if "duplicate_payment" in rule_flags:
            return "duplicate_payment"
        if "vendor_rate_spike" in rule_flags:
            return "vendor_rate_anomaly"
        if "weekend_transaction" in rule_flags:
            return "sla_penalty_risk"
        if isolation_score is not None and isolation_score < -0.2:
            return "cloud_waste"  # High ML confidence anomaly
        return "unknown"

    @staticmethod
    def _estimate_confidence(rule_flags: list[str], isolation_score: Optional[float]) -> float:
        """Estimate overall detection confidence."""
        if "duplicate_payment" in rule_flags:
            return 0.97  # Rule-based, deterministic
        if "vendor_rate_spike" in rule_flags:
            return 0.88
        if "round_number_amount" in rule_flags:
            return 0.75
        if isolation_score is not None:
            # Map isolation score to confidence: more negative = higher confidence
            return min(0.95, max(0.65, 0.80 + abs(isolation_score) * 0.5))
        return 0.70

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
                    "anomaly_id": output_payload.get("anomaly_id") if output_payload else None,
                    "input_payload": event.payload,
                    "output_payload": output_payload,
                    "status": status,
                    "error_message": error_message,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": duration_ms,
                })
        except Exception as log_exc:
            logger.warning("agent03.log_failed", error=str(log_exc))

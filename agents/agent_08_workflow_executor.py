"""
Agent 8 — Workflow Executor

Subscribes to both action.auto_execute and action.approval_needed.

For auto_execute: simulates action execution, marks anomaly as auto_executed.
For approval_needed: marks anomaly as pending_approval in DB.
For approved anomalies (via POST /anomalies/{id}/approve): executes the action.

MVP Implementation: Simulated execution with logged outcomes.
Production path:    SAP RFC, AWS boto3 resize, Slack webhook, SendGrid email.

Subscribes to: action.auto_execute, action.approval_needed
Publishes to:  (none — terminal agent for action path)
Uses LLM:      No
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from core.bus import EventBus
from core.db import get_session_factory, insert_process_log, upsert_anomaly
from models.events import Event

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_08_workflow_executor"
TOPIC_IN_AUTO = "action.auto_execute"
TOPIC_IN_APPROVAL = "action.approval_needed"

# Simulated recovery factor per anomaly type
RECOVERY_FACTORS = {
    "duplicate_payment": 0.98,   # Near-full recovery (stop the payment)
    "cloud_waste": 0.85,         # Right-size the instance
    "unused_saas": 0.90,         # Deprovision unused seats
    "vendor_rate_anomaly": 0.70, # Dispute the excess amount
    "sla_penalty_risk": 0.50,    # Partial mitigation
    "unknown": 0.60,
}

# Simulated action descriptions per type
ACTION_SIMULATIONS = {
    "duplicate_payment": "SIMULATED: Held duplicate PO in procurement system. Vendor notified. Recovery claim initiated.",
    "cloud_waste": "SIMULATED: Downgraded over-provisioned instance. Budget alert set at 80% threshold.",
    "unused_saas": "SIMULATED: Deprovisioned inactive seats. Subscription tier downgraded.",
    "vendor_rate_anomaly": "SIMULATED: Flagged PO for finance review. Rate justification request sent to vendor.",
    "sla_penalty_risk": "SIMULATED: Escalated to ops team. Workload rerouted. Account manager alerted.",
    "unknown": "SIMULATED: Flagged for manual review by finance team.",
}


class WorkflowExecutorAgent:
    """
    Executes approved actions and marks anomalies as resolved.
    Simulates real integrations (SAP, AWS, Slack) in MVP mode.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(TOPIC_IN_AUTO, self.handle_auto_execute)
        bus.subscribe(TOPIC_IN_APPROVAL, self.handle_approval_needed)

    async def handle_auto_execute(self, event: Event) -> None:
        """Execute action immediately — no human approval required."""
        started_at = datetime.now(timezone.utc)
        anomaly = event.payload

        try:
            anomaly_id = anomaly.get("anomaly_id")
            anomaly_type = anomaly.get("anomaly_type", "unknown")
            amount = float(anomaly.get("amount", 0))

            action_result = self._simulate_action(anomaly_type, amount)

            # Update anomaly status in DB
            factory = get_session_factory()
            async with factory() as session:
                try:
                    await upsert_anomaly(session, {
                        "anomaly_id": anomaly_id,
                        "status": "auto_executed",
                    })
                except Exception as db_exc:
                    logger.error(
                        "agent08.upsert_failed",
                        anomaly_id=anomaly_id,
                        error=str(db_exc),
                    )
                    raise

            logger.info(
                "agent08.auto_executed",
                anomaly_id=anomaly_id,
                anomaly_type=anomaly_type,
                recovered_inr=action_result["recovered_inr"],
            )

            await self._log(
                event,
                "success",
                None,
                started_at,
                {**anomaly, **action_result, "status": "auto_executed"},
            )

        except Exception as exc:
            logger.error("agent08.auto_execute_error", event_id=event.event_id, error=str(exc))
            await self._log(event, "error", str(exc), started_at)

    async def handle_approval_needed(self, event: Event) -> None:
        """Register the anomaly as pending approval in DB."""
        started_at = datetime.now(timezone.utc)
        anomaly = event.payload

        try:
            anomaly_id = anomaly.get("anomaly_id")
            factory = get_session_factory()
            async with factory() as session:
                try:
                    await upsert_anomaly(session, {
                        "anomaly_id": anomaly_id,
                        "status": "pending_approval",
                        "approval_needed": True,
                    })
                except Exception as db_exc:
                    logger.error(
                        "agent08.upsert_approval_failed",
                        anomaly_id=anomaly_id,
                        error=str(db_exc),
                    )
                    raise

            logger.info(
                "agent08.pending_approval_registered",
                anomaly_id=anomaly_id,
                aps_score=anomaly.get("aps_score"),
            )

            await self._log(
                event,
                "success",
                None,
                started_at,
                {**anomaly, "status": "pending_approval"},
            )

        except Exception as exc:
            logger.error(
                "agent08.approval_register_error",
                anomaly_id=event.payload.get("anomaly_id"),
                error=str(exc),
            )
            await self._log(event, "error", str(exc), started_at)

    async def execute_approved(
        self,
        anomaly_id: str,
        approved_by: str,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Called by POST /anomalies/{id}/approve API endpoint.
        Executes the action for a human-approved anomaly.
        """
        factory = get_session_factory()
        try:
            async with factory() as session:
                from core.db import approve_anomaly
                anomaly_row = await approve_anomaly(session, anomaly_id, approved_by, notes)
                if not anomaly_row:
                    raise ValueError(f"Anomaly {anomaly_id} not found")

                anomaly_type = anomaly_row.anomaly_type or "unknown"
                amount = float(anomaly_row.amount or 0)

                # Simulate execution
                action_result = self._simulate_action(anomaly_type, amount)

                # Update to executed status after approval and action execution
                await upsert_anomaly(session, {
                    "anomaly_id": anomaly_id,
                    "status": "auto_executed",
                })

            logger.info(
                "agent08.approved_executed",
                anomaly_id=anomaly_id,
                approved_by=approved_by,
                recovered_inr=action_result.get("recovered_inr", 0),
            )
            return action_result
        except Exception as exc:
            logger.error(
                "agent08.execute_approved_error",
                anomaly_id=anomaly_id,
                approved_by=approved_by,
                error=str(exc),
            )
            raise

    @staticmethod
    def _simulate_action(anomaly_type: str, amount: float) -> dict:
        """Simulate action execution and compute recovery attribution."""
        recovery_factor = RECOVERY_FACTORS.get(anomaly_type, 0.60)
        recovered_inr = round(amount * recovery_factor, 2)
        description = ACTION_SIMULATIONS.get(anomaly_type, ACTION_SIMULATIONS["unknown"])
        return {
            "action_description": description,
            "recovered_inr": recovered_inr,
            "recovery_factor": recovery_factor,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _log(
        self,
        event: Event,
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
                try:
                    await insert_process_log(session, {
                        "process_id": event.process_id,
                        "agent_name": AGENT_NAME,
                        "event_id": event.event_id,
                        "topic_in": event.topic,
                        "topic_out": None,
                        "record_id": event.payload.get("record_id"),
                        "anomaly_id": event.payload.get("anomaly_id"),
                        "input_payload": event.payload,
                        "output_payload": output_payload,
                        "status": status,
                        "error_message": error_message,
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "duration_ms": duration_ms,
                    })
                except Exception as db_exc:
                    logger.error(
                        "agent08.log_insert_failed",
                        anomaly_id=event.payload.get("anomaly_id"),
                        error=str(db_exc),
                    )
                    raise
        except Exception as log_exc:
            logger.warning("agent08.log_failed", error=str(log_exc))

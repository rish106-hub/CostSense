"""
Synthetic spend data generator for CostSense AI.

Generates realistic enterprise spend records using numpy, then injects
known anomalies to test detection quality.

Default: 86 baseline records + 6 injected anomalies (configurable).

Anomaly types injected:
  1. duplicate_payment   — same invoice processed twice (AWS India)
  2. duplicate_payment   — same invoice processed twice (AWS India)
  3. cloud_waste         — 4x spending spike vs vendor baseline (GCP Compute)
  4. unused_saas         — SaaS spend with low active seat ratio (Slack)
  5. vendor_rate_anomaly — z-score > 2.5 vs vendor mean (Infosys Consulting)
  6. sla_penalty_risk    — unexplained spike flagged by ML (Tata Communications)
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

VENDORS = {
    "cloud": ["AWS India", "GCP Compute", "Microsoft Azure", "DigitalOcean"],
    "saas": ["Slack", "Zoom", "Notion", "HubSpot", "Salesforce", "Jira"],
    "external_services": [
        "Infosys Consulting",
        "Tata Communications",
        "Wipro Technologies",
        "Accenture India",
    ],
    "people": ["Payroll Services Ltd", "TeamLease", "Naukri RPO"],
    "overhead": [
        "Office Depot",
        "MakeMyTrip Corporate",
        "India Caterers Pvt Ltd",
        "Facility Pro",
    ],
}

DEPARTMENTS = [
    "Engineering",
    "Finance",
    "Operations",
    "Marketing",
    "HR",
    "Sales",
    "Product",
]

# Typical monthly spend ranges per category (INR)
AMOUNT_RANGES = {
    "cloud": (80_000, 800_000),
    "saas": (20_000, 300_000),
    "external_services": (150_000, 1_500_000),
    "people": (500_000, 5_000_000),
    "overhead": (10_000, 150_000),
}

# Pre-defined injected anomalies (index-keyed)
INJECTED_ANOMALIES = [
    {
        "_anomaly_hint": "duplicate_payment",
        "vendor": "AWS India",
        "amount": 825_000.0,
        "currency": "INR",
        "department": "Engineering",
        "category": "cloud",
        "invoice_number": "AWS-INV-2024-9921",
        "description": "AWS Infrastructure Q1 2024",
        "source": "synthetic",
    },
    {
        "_anomaly_hint": "duplicate_payment",
        "vendor": "AWS India",
        "amount": 825_000.0,
        "currency": "INR",
        "department": "Engineering",
        "category": "cloud",
        "invoice_number": "AWS-INV-2024-9921",  # Same invoice — duplicate!
        "description": "AWS Infrastructure Q1 2024 (duplicate)",
        "source": "synthetic",
    },
    {
        "_anomaly_hint": "cloud_waste",
        "vendor": "GCP Compute",
        "amount": 980_000.0,  # 4x normal spend
        "currency": "INR",
        "department": "Engineering",
        "category": "cloud",
        "invoice_number": "GCP-2024-Q1-0055",
        "description": "GCP Compute — over-provisioned instances",
        "source": "synthetic",
    },
    {
        "_anomaly_hint": "unused_saas",
        "vendor": "Slack",
        "amount": 340_000.0,
        "currency": "INR",
        "department": "Operations",
        "category": "saas",
        "invoice_number": "SLACK-ENT-2024-447",
        "description": "Slack Enterprise — 120 seats, 35 active",
        "source": "synthetic",
    },
    {
        "_anomaly_hint": "vendor_rate_anomaly",
        "vendor": "Infosys Consulting",
        "amount": 712_000.0,  # z-score > 2.5 vs vendor mean
        "currency": "INR",
        "department": "Finance",
        "category": "external_services",
        "invoice_number": "INFY-CONSULT-Q1-2024-88",
        "description": "Consulting services — rate above contracted",
        "source": "synthetic",
    },
    {
        "_anomaly_hint": "sla_penalty_risk",
        "vendor": "Tata Communications",
        "amount": 220_000.0,
        "currency": "INR",
        "department": "Operations",
        "category": "external_services",
        "invoice_number": "TATA-COMM-2024-311",
        "description": "Network services — SLA penalty clause triggered",
        "source": "synthetic",
    },
]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def generate_spend_records(
    n: int = 80,
    seed: int = 42,
    include_anomalies: bool = True,
    start_date: Optional[date] = None,
) -> list[dict]:
    """
    Generate n baseline spend records plus injected anomalies.

    Args:
        n: Number of baseline (normal) records to generate.
        seed: Random seed for reproducibility.
        include_anomalies: If True, appends 6 known anomalies to the dataset.
        start_date: First transaction date (defaults to 90 days ago).

    Returns:
        List of spend record dicts ready for ingestion.
    """
    rng = np.random.default_rng(seed)
    if start_date is None:
        start_date = date.today() - timedelta(days=90)

    records = []

    # Build flat lists for vectorized sampling
    all_vendors: list[tuple[str, str]] = []  # (vendor, category)
    for category, vendor_list in VENDORS.items():
        for vendor in vendor_list:
            all_vendors.append((vendor, category))

    for i in range(n):
        vendor, category = all_vendors[int(rng.integers(0, len(all_vendors)))]
        low, high = AMOUNT_RANGES[category]

        # Log-normal distribution for realistic spending
        mean_log = np.log((low + high) / 2)
        std_log = 0.4
        amount = float(np.exp(rng.normal(mean_log, std_log)))
        amount = max(low * 0.5, min(amount, high * 1.5))
        amount = round(amount, 2)

        department = DEPARTMENTS[int(rng.integers(0, len(DEPARTMENTS)))]
        days_offset = int(rng.integers(0, 90))
        txn_date = start_date + timedelta(days=days_offset)
        invoice_number = f"INV-{rng.integers(10000, 99999)}-{txn_date.year}"

        record = {
            "vendor": vendor,
            "amount": amount,
            "currency": "INR",
            "department": department,
            "category": category,
            "transaction_date": txn_date.isoformat(),
            "source": "synthetic",
            "invoice_number": str(invoice_number),
            "description": f"{vendor} — {category} services",
        }
        records.append(record)

    if include_anomalies:
        # Inject known anomalies with transaction dates spread across the period
        for idx, anomaly in enumerate(INJECTED_ANOMALIES):
            anomaly_record = dict(anomaly)
            # Remove the hint field — it's not a DB column
            anomaly_record.pop("_anomaly_hint", None)
            days_offset = (idx + 1) * 10
            txn_date = start_date + timedelta(days=min(days_offset, 85))
            anomaly_record["transaction_date"] = txn_date.isoformat()
            records.append(anomaly_record)

    # Assign stable record_ids and content hashes
    for record in records:
        record["record_id"] = str(uuid.uuid4())
        record["content_hash"] = _compute_content_hash(record)

    return records


def _compute_content_hash(record: dict) -> str:
    """
    SHA256 hash of vendor + amount + invoice_number + date for deduplication.
    Two records with the same hash are considered duplicates.
    """
    key = json.dumps(
        {
            "vendor": record.get("vendor", ""),
            "amount": record.get("amount", 0),
            "invoice_number": record.get("invoice_number", ""),
            "transaction_date": record.get("transaction_date", ""),
        },
        sort_keys=True,
    )
    return hashlib.sha256(key.encode()).hexdigest()


def records_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """Convert the records list to a pandas DataFrame for display in Streamlit."""
    df = pd.DataFrame(records)
    # Drop internal fields not useful for display
    drop_cols = [c for c in ["record_id", "content_hash"] if c in df.columns]
    df = df.drop(columns=drop_cols)
    # Reorder columns for readability
    preferred_order = [
        "vendor", "amount", "currency", "category", "department",
        "transaction_date", "invoice_number", "description", "source",
    ]
    existing = [c for c in preferred_order if c in df.columns]
    remaining = [c for c in df.columns if c not in existing]
    return df[existing + remaining]


def get_anomaly_summary() -> list[dict]:
    """Return metadata about the 6 injected anomalies (for documentation)."""
    return [
        {
            "index": idx,
            "hint": a.get("_anomaly_hint", "unknown"),
            "vendor": a["vendor"],
            "amount_inr": a["amount"],
            "category": a["category"],
            "invoice_number": a["invoice_number"],
        }
        for idx, a in enumerate(INJECTED_ANOMALIES)
    ]

"""
GET /synthetic/data  — return generated records as JSON
GET /synthetic/download — return generated records as CSV file
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from data.synthetic_generator import generate_spend_records, records_to_dataframe
from models.schemas import SyntheticDataResponse

router = APIRouter(prefix="/synthetic", tags=["synthetic"])


@router.get("/data", response_model=SyntheticDataResponse)
async def get_synthetic_data(
    n: int = Query(default=86, ge=10, le=500, description="Number of baseline records"),
    seed: int = Query(default=42, description="Random seed for reproducibility"),
    include_anomalies: bool = Query(default=True, description="Include injected anomalies"),
):
    """Generate and return synthetic spend records as JSON."""
    records = generate_spend_records(n=n, seed=seed, include_anomalies=include_anomalies)
    return SyntheticDataResponse(
        count=len(records),
        seed=seed,
        include_anomalies=include_anomalies,
        records=records,
    )


@router.get("/download")
async def download_synthetic_data(
    n: int = Query(default=86, ge=10, le=500),
    seed: int = Query(default=42),
    include_anomalies: bool = Query(default=True),
):
    """Download synthetic spend records as a CSV file."""
    records = generate_spend_records(n=n, seed=seed, include_anomalies=include_anomalies)
    df = records_to_dataframe(records)

    # Write to in-memory CSV buffer
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=costsense_synthetic_n{n}_seed{seed}.csv"
        },
    )

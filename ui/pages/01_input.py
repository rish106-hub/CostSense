"""
Page 1 — Data Input

Two modes:
  A. Synthetic Data — generate via numpy, preview, download as CSV, run pipeline
  B. Custom Data    — upload CSV or enter rows manually, validate, run pipeline
"""

import io
from typing import Optional

import pandas as pd
import requests
import streamlit as st

from ui.components.api_client import (
    BASE_URL,
    get_health,
    get_synthetic_data,
    ingest_batch,
    ingest_demo,
)

st.set_page_config(page_title="Data Input — CostSense AI", page_icon="�", layout="wide")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Data Input")
st.caption("Feed spend data into the CostSense pipeline — synthetic or your own.")

# Check API connectivity
health = get_health()
if health is None:
    st.error("Cannot reach API server. Make sure `python run.py` is running on port 8000.")
    st.stop()
else:
    st.success(f"API connected — v{health.get('version', '?')} | {health.get('events_processed', 0)} events processed")

st.divider()

# ---------------------------------------------------------------------------
# Mode selector
# ---------------------------------------------------------------------------
mode = st.radio(
    "Input Mode",
    ["Synthetic Data", "Custom Data"],
    horizontal=True,
)

# ---------------------------------------------------------------------------
# MODE A — Synthetic Data
# ---------------------------------------------------------------------------
if mode == "Synthetic Data":
    st.subheader("Generate Synthetic Spend Records")
    st.caption("Uses numpy to generate realistic enterprise spend data with injected anomalies.")

    col1, col2, col3 = st.columns(3)
    with col1:
        n_records = st.slider("Number of baseline records", min_value=20, max_value=500, value=86, step=10)
    with col2:
        seed = st.number_input("Random seed", min_value=0, max_value=9999, value=42)
    with col3:
        include_anomalies = st.checkbox("Include injected anomalies", value=True, help="Adds 6 known anomalies for detection testing")

    col_preview, col_download, col_run = st.columns([2, 1, 1])

    with col_preview:
        if st.button("Generate & Preview", use_container_width=True):
            with st.spinner("Generating records..."):
                result = get_synthetic_data(n=n_records, seed=seed, include_anomalies=include_anomalies)
            if result and "records" in result:
                records = result["records"]
                st.session_state["synthetic_records"] = records
                st.session_state["synthetic_params"] = {
                    "n": n_records, "seed": seed, "include_anomalies": include_anomalies
                }
                st.success(f"Generated {len(records)} records ({result['count']} total)")
            else:
                st.error("Failed to generate records. Check API connection.")

    # Show preview table if records are in session state
    if "synthetic_records" in st.session_state:
        records = st.session_state["synthetic_records"]
        df = pd.DataFrame(records)
        display_cols = ["vendor", "amount", "currency", "category", "department", "transaction_date", "invoice_number", "source"]
        display_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, height=300)
        st.caption(f"{len(records)} records total | {df['category'].value_counts().to_dict()}")

        # Anomaly summary
        if include_anomalies:
            with st.expander("Injected Anomaly Details"):
                anomaly_info = [
                    {"Type": "duplicate_payment", "Vendor": "AWS India", "Amount (₹)": "8,25,000", "Detection": "Rule: same invoice_id"},
                    {"Type": "duplicate_payment", "Vendor": "AWS India", "Amount (₹)": "8,25,000", "Detection": "Rule: same invoice_id"},
                    {"Type": "cloud_waste", "Vendor": "GCP Compute", "Amount (₹)": "9,80,000", "Detection": "ML: 4x vendor spike"},
                    {"Type": "unused_saas", "Vendor": "Slack", "Amount (₹)": "3,40,000", "Detection": "ML: seat ratio anomaly"},
                    {"Type": "vendor_rate_anomaly", "Vendor": "Infosys Consulting", "Amount (₹)": "7,12,000", "Detection": "Rule: z-score > 2.5"},
                    {"Type": "sla_penalty_risk", "Vendor": "Tata Communications", "Amount (₹)": "2,20,000", "Detection": "ML: spend spike"},
                ]
                st.table(pd.DataFrame(anomaly_info))

        col_dl, col_go = st.columns(2)
        with col_dl:
            # Download button
            csv_buf = io.StringIO()
            df[display_cols].to_csv(csv_buf, index=False)
            st.download_button(
                label="Download as CSV",
                data=csv_buf.getvalue(),
                file_name=f"costsense_synthetic_n{len(records)}_seed{seed}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_go:
            if st.button("Run Pipeline", type="primary", use_container_width=True):
                with st.spinner("Submitting to pipeline..."):
                    params = st.session_state.get("synthetic_params", {})
                    result = ingest_demo(
                        n=params.get("n", 86),
                        seed=params.get("seed", 42),
                        include_anomalies=params.get("include_anomalies", True),
                    )
                if result and "process_id" in result:
                    st.success(f"Pipeline started! Process ID: `{result['process_id']}`")
                    st.info("Switch to **Pipeline** page to watch agents process the data in real time.")
                    st.session_state["last_process_id"] = result["process_id"]
                else:
                    st.error("Failed to start pipeline.")

# ---------------------------------------------------------------------------
# MODE B — Custom Data
# ---------------------------------------------------------------------------
else:
    st.subheader("Custom Spend Data")

    sub_mode = st.radio("Entry method", ["Upload CSV", "Enter Manually"], horizontal=True)

    REQUIRED_COLUMNS = ["vendor", "amount", "category", "department", "transaction_date"]
    OPTIONAL_COLUMNS = ["currency", "invoice_number", "description", "source"]
    TEMPLATE_ROW = {
        "vendor": "Example Vendor Ltd",
        "amount": 150000.0,
        "currency": "INR",
        "category": "cloud",
        "department": "Engineering",
        "transaction_date": "2024-03-15",
        "invoice_number": "INV-001",
        "description": "Monthly cloud infrastructure",
        "source": "manual",
    }

    records_to_submit: Optional[list[dict]] = None

    if sub_mode == "Upload CSV":
        st.caption("CSV must have these columns: " + ", ".join(REQUIRED_COLUMNS))

        uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            st.write(f"**Preview** ({len(df)} rows):")
            st.dataframe(df.head(10), use_container_width=True)

            # Validate required columns
            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                st.error(f"Missing required columns: {missing}")
            else:
                st.success("✅ All required columns present")
                records_to_submit = df.to_dict(orient="records")

    else:
        st.caption("Edit the table below. Add rows with the + button.")
        template_df = pd.DataFrame([TEMPLATE_ROW])
        edited_df = st.data_editor(
            template_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "amount": st.column_config.NumberColumn("Amount (₹)", min_value=0),
                "category": st.column_config.SelectboxColumn(
                    "Category",
                    options=["cloud", "saas", "external_services", "people", "overhead"],
                ),
                "currency": st.column_config.SelectboxColumn(
                    "Currency", options=["INR", "USD", "EUR", "GBP"]
                ),
            },
        )
        # Basic validation
        missing_rows = edited_df[REQUIRED_COLUMNS].isnull().any(axis=1).sum()
        if missing_rows > 0:
            st.warning(f"{missing_rows} rows have missing required fields")
        else:
            records_to_submit = edited_df.to_dict(orient="records")

    if records_to_submit:
        st.write(f"**{len(records_to_submit)} records ready to submit**")
        if st.button("🚀 Run Pipeline", type="primary"):
            # Convert to SpendRecordIn compatible format
            clean_records = []
            for r in records_to_submit:
                clean = {k: v for k, v in r.items() if pd.notna(v) if v != ""}
                clean["amount"] = float(clean.get("amount", 0))
                clean["currency"] = str(clean.get("currency", "INR"))
                clean["source"] = str(clean.get("source", "manual"))
                clean_records.append(clean)

            with st.spinner(f"Submitting {len(clean_records)} records..."):
                result = ingest_batch(clean_records)
            if result and "process_id" in result:
                st.success(f"✅ Submitted! Process ID: `{result['process_id']}`")
                st.info("Switch to **Pipeline** page to monitor progress.")
                st.session_state["last_process_id"] = result["process_id"]
            else:
                st.error(f"Submission failed: {result}")

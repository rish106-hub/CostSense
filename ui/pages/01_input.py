"""
Page 1 — Data Ingestion
Upload Excel/CSV or run synthetic demo data through the pipeline.
"""

import io
from typing import Optional

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Data Input — CostSense AI", page_icon="⚡", layout="wide")

from ui.components.theme import inject_global_css, page_header, kpi_card, badge
from ui.components.api_client import (
    BASE_URL,
    get_health,
    get_synthetic_data,
    ingest_batch,
    ingest_demo,
)

inject_global_css()

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 12px 4px 20px;">
        <div style="font-size:1.1rem; font-weight:800; color:#e8f0fe;">⚡ CostSense AI</div>
        <div style="font-size:10px; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-top:2px;">Data Ingestion</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    st.markdown("""
    <div style="font-size:12px; color:#4a6080; line-height:1.7;">
    <strong style="color:#8098b8;">Required columns</strong><br>
    vendor · amount · category<br>
    department · transaction_date
    <br><br>
    <strong style="color:#8098b8;">Optional columns</strong><br>
    currency · invoice_number<br>
    description · source
    </div>
    """, unsafe_allow_html=True)

# ── Health check ───────────────────────────────────────────────
health = get_health()
if health is None:
    st.markdown(
        '<div class="banner-error">⚠️ Cannot reach API — run <code>python run.py</code> first.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

page_header("Data Ingestion", "Feed spend records into the analysis pipeline.")

REQUIRED_COLS = ["vendor", "amount", "category", "department", "transaction_date"]
OPTIONAL_COLS = ["currency", "invoice_number", "description", "source"]

# ── Mode tabs ─────────────────────────────────────────────────
tab_demo, tab_upload, tab_manual = st.tabs(
    ["  Demo Dataset  ", "  Upload File (CSV / Excel)  ", "  Manual Entry  "]
)

# ═══════════════════════════════════════════════════════════════
# TAB 1 — Demo Dataset
# ═══════════════════════════════════════════════════════════════
with tab_demo:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div class="banner-info">ℹ This dataset includes 6 pre-injected anomalies '
        '(duplicate payments, cloud waste, SaaS over-spend, vendor rate spikes) '
        'so you can see the full detection pipeline in action.</div>',
        unsafe_allow_html=True,
    )

    col_params, col_info = st.columns([2, 1])
    with col_params:
        n_records = st.slider("Baseline spend records", 20, 500, 86, 10,
                              help="Number of normal records before anomaly injection")
        seed = st.number_input("Random seed", 0, 9999, 42,
                               help="Controls which anomalies are generated")
        include_anomalies = st.checkbox("Inject known anomalies", True,
                                        help="Adds 6 anomalies across duplicate, cloud, SaaS, vendor, and SLA categories")

    with col_info:
        st.markdown(
            f"""<div class="kpi-card kpi-card-blue" style="margin-top:8px;">
                <div class="kpi-label">Pre-Configured Dataset</div>
                <div class="kpi-value">{n_records + (6 if include_anomalies else 0)}</div>
                <div class="kpi-sub">total records · {'6 anomalies injected' if include_anomalies else 'no anomalies'}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Preview Dataset", use_container_width=True):
            with st.spinner("Generating…"):
                result = get_synthetic_data(n=n_records, seed=seed, include_anomalies=include_anomalies)
            if result and "records" in result:
                st.session_state["synth_records"] = result["records"]
                st.session_state["synth_params"] = {"n": n_records, "seed": seed, "include_anomalies": include_anomalies}
            else:
                st.error("Failed to fetch data — check API connection.")

    with c2:
        if st.button("▶  Start Pipeline Analysis", type="primary", use_container_width=True):
            with st.spinner("Submitting to pipeline…"):
                result = ingest_demo(n=n_records, seed=seed, include_anomalies=include_anomalies)
            if result and "process_id" in result:
                st.session_state["last_process_id"] = result["process_id"]
                st.markdown(
                    f'<div class="banner-success">✓ Pipeline started — {result["records"]} records submitted.<br>'
                    f'Process ID: <code>{result["process_id"]}</code></div>',
                    unsafe_allow_html=True,
                )
                st.info("Switch to **Live Pipeline** to watch agents process the data in real time.")
            else:
                st.error(f"Submission failed: {result}")

    # Preview table
    if "synth_records" in st.session_state:
        records = st.session_state["synth_records"]
        df = pd.DataFrame(records)
        display_cols = [c for c in ["vendor", "amount", "currency", "category", "department", "transaction_date", "invoice_number", "source"] if c in df.columns]
        st.markdown("---")
        st.markdown(f"**Preview** — {len(records)} records")
        st.dataframe(df[display_cols], use_container_width=True, height=280)

        # Download
        buf = io.StringIO()
        df[display_cols].to_csv(buf, index=False)
        st.download_button(
            "⬇  Download as CSV",
            buf.getvalue(),
            file_name=f"costsense_demo_n{len(records)}_seed{seed}.csv",
            mime="text/csv",
        )

        # Injected anomaly table
        if include_anomalies:
            with st.expander("Injected Anomaly Details"):
                anom_info = pd.DataFrame([
                    {"#": 1, "Type": "Duplicate Payment",   "Vendor": "AWS India",            "Amount": "₹8,25,000", "Detection": "Matching invoice_id rule"},
                    {"#": 2, "Type": "Duplicate Payment",   "Vendor": "AWS India",            "Amount": "₹8,25,000", "Detection": "Matching invoice_id rule"},
                    {"#": 3, "Type": "Cloud Waste",         "Vendor": "GCP Compute",          "Amount": "₹9,80,000", "Detection": "4× vendor baseline spike"},
                    {"#": 4, "Type": "Unused SaaS",         "Vendor": "Slack",                "Amount": "₹3,40,000", "Detection": "Seat utilisation anomaly"},
                    {"#": 5, "Type": "Vendor Rate Anomaly", "Vendor": "Infosys Consulting",   "Amount": "₹7,12,000", "Detection": "z-score > 2.5"},
                    {"#": 6, "Type": "SLA Penalty Risk",    "Vendor": "Tata Communications",  "Amount": "₹2,20,000", "Detection": "Spend spike pattern"},
                ])
                st.dataframe(anom_info, hide_index=True, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# TAB 2 — Upload File
# ═══════════════════════════════════════════════════════════════
with tab_upload:
    st.markdown("<br>", unsafe_allow_html=True)

    # Template download
    template_data = pd.DataFrame([{
        "vendor": "Example Vendor Ltd",
        "amount": 150000.0,
        "currency": "INR",
        "category": "cloud",
        "department": "Engineering",
        "transaction_date": "2024-03-15",
        "invoice_number": "INV-001",
        "description": "Monthly cloud infrastructure",
        "source": "erp",
    }])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        template_data.to_excel(writer, index=False, sheet_name="SpendData")
    buf.seek(0)

    col_info, col_dl = st.columns([3, 1])
    with col_info:
        st.markdown(
            '<div class="banner-info">Upload your spend export from SAP, Oracle, QuickBooks, or any ERP. '
            'Supports <strong>.xlsx</strong>, <strong>.xls</strong>, and <strong>.csv</strong> formats.</div>',
            unsafe_allow_html=True,
        )
    with col_dl:
        st.download_button(
            "⬇  Download Template (.xlsx)",
            data=buf.getvalue(),
            file_name="costsense_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    uploaded_file = st.file_uploader(
        "Drop your file here or click to browse",
        type=["csv", "xlsx", "xls"],
        help="Max 50 MB · CSV or Excel format",
    )

    records_to_submit: Optional[list[dict]] = None
    df_uploaded: Optional[pd.DataFrame] = None

    if uploaded_file:
        try:
            fname = uploaded_file.name.lower()
            if fname.endswith(".csv"):
                df_uploaded = pd.read_csv(uploaded_file)
            else:
                df_uploaded = pd.read_excel(uploaded_file, engine="openpyxl")
        except Exception as e:
            st.error(f"Could not read file: {e}")
            df_uploaded = None

    if df_uploaded is not None:
        st.markdown(f"**{len(df_uploaded)} rows loaded** from `{uploaded_file.name}`")

        # Column mapping UI
        missing = [c for c in REQUIRED_COLS if c not in df_uploaded.columns]
        if missing:
            st.markdown('<div class="banner-warning">⚠ Missing required columns — map them below:</div>', unsafe_allow_html=True)
            col_map = {}
            available_cols = ["(skip)"] + list(df_uploaded.columns)
            map_cols = st.columns(len(missing))
            for i, req_col in enumerate(missing):
                with map_cols[i]:
                    mapped = st.selectbox(f'Map to "{req_col}"', available_cols, key=f"map_{req_col}")
                    if mapped != "(skip)":
                        col_map[mapped] = req_col

            if col_map:
                df_uploaded = df_uploaded.rename(columns=col_map)

        # Re-check after mapping
        still_missing = [c for c in REQUIRED_COLS if c not in df_uploaded.columns]
        if still_missing:
            st.error(f"Still missing: {still_missing} — cannot submit.")
        else:
            st.markdown(
                '<div class="banner-success">✓ All required columns present — ready to submit.</div>',
                unsafe_allow_html=True,
            )
            display_cols = [c for c in REQUIRED_COLS + OPTIONAL_COLS if c in df_uploaded.columns]
            st.dataframe(df_uploaded[display_cols].head(10), use_container_width=True, height=250)
            st.caption(f"Showing first 10 of {len(df_uploaded)} rows")
            records_to_submit = df_uploaded.to_dict(orient="records")

    if records_to_submit:
        c_cnt, c_btn = st.columns([2, 1])
        with c_cnt:
            st.markdown(
                f"""<div class="kpi-card kpi-card-blue" style="margin-top:4px;">
                    <div class="kpi-label">Ready to Analyse</div>
                    <div class="kpi-value">{len(records_to_submit)}</div>
                    <div class="kpi-sub">spend records</div>
                </div>""",
                unsafe_allow_html=True,
            )
        with c_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("▶  Run Pipeline Analysis", type="primary", use_container_width=True):
                clean = []
                for r in records_to_submit:
                    d = {k: v for k, v in r.items() if pd.notna(v) and v != ""}
                    d["amount"]   = float(d.get("amount", 0))
                    d["currency"] = str(d.get("currency", "INR"))
                    d["source"]   = str(d.get("source", "upload"))
                    clean.append(d)
                with st.spinner(f"Submitting {len(clean)} records…"):
                    result = ingest_batch(clean)
                if result and "process_id" in result:
                    st.session_state["last_process_id"] = result["process_id"]
                    st.markdown(
                        f'<div class="banner-success">✓ {len(clean)} records submitted.<br>'
                        f'Process ID: <code>{result["process_id"]}</code></div>',
                        unsafe_allow_html=True,
                    )
                    st.info("Switch to **Live Pipeline** to monitor progress.")
                else:
                    st.error(f"Submission failed: {result}")


# ═══════════════════════════════════════════════════════════════
# TAB 3 — Manual Entry
# ═══════════════════════════════════════════════════════════════
with tab_manual:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div class="banner-info">ℹ Add rows directly — useful for spot-checking individual transactions.</div>',
        unsafe_allow_html=True,
    )

    TEMPLATE_ROW = {
        "vendor": "Example Vendor",
        "amount": 150000.0,
        "currency": "INR",
        "category": "cloud",
        "department": "Engineering",
        "transaction_date": "2024-03-15",
        "invoice_number": "INV-001",
        "description": "Monthly infrastructure",
        "source": "manual",
    }
    template_df = pd.DataFrame([TEMPLATE_ROW])

    edited_df = st.data_editor(
        template_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "amount": st.column_config.NumberColumn("Amount", min_value=0, format="₹%.0f"),
            "category": st.column_config.SelectboxColumn(
                "Category",
                options=["cloud", "saas", "external_services", "people", "overhead", "other"],
            ),
            "currency": st.column_config.SelectboxColumn(
                "Currency", options=["INR", "USD", "EUR", "GBP", "AED"]
            ),
            "transaction_date": st.column_config.TextColumn(
                "Date (YYYY-MM-DD)", help="Format: 2024-03-15"
            ),
        },
        height=280,
    )

    valid_rows = edited_df.dropna(subset=REQUIRED_COLS)
    invalid_count = len(edited_df) - len(valid_rows)

    c_info, c_btn = st.columns([2, 1])
    with c_info:
        if invalid_count > 0:
            st.markdown(
                f'<div class="banner-warning">⚠ {invalid_count} rows have empty required fields and will be skipped.</div>',
                unsafe_allow_html=True,
            )
        if len(valid_rows) > 0:
            st.markdown(
                f"""<div class="kpi-card kpi-card-green" style="margin-top:4px;">
                    <div class="kpi-label">Valid records</div>
                    <div class="kpi-value">{len(valid_rows)}</div>
                    <div class="kpi-sub">ready to submit</div>
                </div>""",
                unsafe_allow_html=True,
            )
    with c_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if len(valid_rows) > 0:
            if st.button("▶  Run Analysis", type="primary", use_container_width=True):
                clean = []
                for _, row in valid_rows.iterrows():
                    d = {k: v for k, v in row.items() if pd.notna(v) and str(v) != ""}
                    d["amount"]   = float(d.get("amount", 0))
                    d["currency"] = str(d.get("currency", "INR"))
                    d["source"]   = "manual"
                    clean.append(d)
                with st.spinner("Submitting…"):
                    result = ingest_batch(clean)
                if result and "process_id" in result:
                    st.session_state["last_process_id"] = result["process_id"]
                    st.markdown(
                        f'<div class="banner-success">✓ Submitted {len(clean)} records.<br>'
                        f'Process ID: <code>{result["process_id"]}</code></div>',
                        unsafe_allow_html=True,
                    )
                    st.info("Switch to **Live Pipeline** to monitor progress.")
                else:
                    st.error(f"Submission failed: {result}")

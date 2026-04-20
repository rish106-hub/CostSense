"""Global CSS design system for CostSense AI."""

import streamlit as st

GLOBAL_CSS = """
<style>
/* ================================================
   CostSense AI — Design System v2
   Dark B2B Dashboard Theme
   ================================================ */

/* Base */
.stApp { background-color: #070d1a; }
section[data-testid="stSidebar"] {
    background-color: #0c1525;
    border-right: 1px solid #1a2540;
}
.main .block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
    max-width: 1440px;
}

/* Hide streamlit default chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* ---- KPI Cards ---- */
.kpi-card {
    background: #0c1525;
    border: 1px solid #1a2540;
    border-radius: 12px;
    padding: 20px 22px;
    height: 100%;
    position: relative;
    overflow: hidden;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    border-radius: 12px 0 0 12px;
}
.kpi-card-green::before  { background: #22c55e; }
.kpi-card-red::before    { background: #ef4444; }
.kpi-card-orange::before { background: #f59e0b; }
.kpi-card-blue::before   { background: #3b82f6; }
.kpi-card-purple::before { background: #a78bfa; }
.kpi-label {
    font-size: 10px;
    font-weight: 700;
    color: #4a6080;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 10px;
}
.kpi-value {
    font-size: 1.9rem;
    font-weight: 700;
    color: #e8f0fe;
    line-height: 1;
    margin-bottom: 6px;
    letter-spacing: -0.03em;
}
.kpi-sub {
    font-size: 11px;
    color: #4a6080;
    margin-top: 2px;
}

/* ---- Page Header ---- */
.page-header {
    margin-bottom: 20px;
}
.page-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #e8f0fe;
    letter-spacing: -0.02em;
    margin: 0;
    line-height: 1.2;
}
.page-subtitle {
    font-size: 13px;
    color: #4a6080;
    margin: 4px 0 0;
}

/* ---- API Status Badge ---- */
.api-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 5px 13px;
    border-radius: 9999px;
    font-size: 12px;
    font-weight: 600;
}
.api-online  { background: #052e16; color: #22c55e; border: 1px solid #15803d; }
.api-offline { background: #1a0505; color: #ef4444; border: 1px solid #7f1d1d; }
.status-dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
}
.dot-green { background: #22c55e; animation: blink 1.8s ease-in-out infinite; }
.dot-red   { background: #ef4444; }

@keyframes blink {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.2; }
}

/* ---- Agent Pipeline Nodes ---- */
.agent-node {
    border-radius: 10px;
    padding: 14px 12px;
    text-align: center;
    position: relative;
    transition: transform 0.2s, box-shadow 0.2s;
}
.agent-node:hover { transform: translateY(-2px); }
.agent-num {
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 5px;
    opacity: 0.6;
}
.agent-name {
    font-size: 12px;
    font-weight: 600;
    color: #cbd5e1;
    margin-bottom: 8px;
    line-height: 1.3;
}
.agent-count {
    font-size: 1.5rem;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 2px;
}
.agent-errors {
    font-size: 10px;
    opacity: 0.7;
    margin-top: 2px;
}

/* Active — Green */
.agent-green {
    background: linear-gradient(145deg, #052e16 0%, #064e3b 100%);
    border: 1.5px solid #22c55e;
    animation: pulse-green 2.5s ease-in-out infinite;
}
.agent-green .agent-count { color: #22c55e; }
.agent-green .agent-num   { color: #22c55e; }

/* Warning — Orange */
.agent-orange {
    background: linear-gradient(145deg, #1c1007 0%, #292524 100%);
    border: 1.5px solid #f59e0b;
    animation: pulse-orange 2.5s ease-in-out infinite;
}
.agent-orange .agent-count { color: #f59e0b; }
.agent-orange .agent-num   { color: #f59e0b; }

/* Error — Red */
.agent-red {
    background: linear-gradient(145deg, #1a0505 0%, #2d0a0a 100%);
    border: 1.5px solid #ef4444;
}
.agent-red .agent-count { color: #ef4444; }
.agent-red .agent-num   { color: #ef4444; }

/* Idle — Gray */
.agent-gray {
    background: #0c1525;
    border: 1.5px solid #1a2540;
}
.agent-gray .agent-count { color: #334155; }
.agent-gray .agent-num   { color: #334155; }

@keyframes pulse-green {
    0%   { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.3); }
    70%  { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
    100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
}
@keyframes pulse-orange {
    0%   { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.25); }
    70%  { box-shadow: 0 0 0 8px rgba(245, 158, 11, 0); }
    100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
}

/* ---- Pipeline Arrows ---- */
.pipe-down {
    text-align: center;
    color: #1e3050;
    font-size: 20px;
    line-height: 1.6;
    user-select: none;
}
.pipe-connector {
    display: flex;
    align-items: center;
    justify-content: center;
    color: #1e3050;
    font-size: 13px;
    gap: 8px;
    padding: 2px 0;
}
.pipe-line {
    flex: 1;
    height: 1px;
    background: #1a2540;
    max-width: 40px;
}

/* ---- Badges ---- */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 9999px;
    font-size: 11px;
    font-weight: 600;
    line-height: 1.5;
}
.badge-green  { background: #052e16; color: #22c55e; border: 1px solid #15803d; }
.badge-orange { background: #1c1007; color: #f59e0b; border: 1px solid #b45309; }
.badge-red    { background: #1a0505; color: #ef4444; border: 1px solid #b91c1c; }
.badge-blue   { background: #0c1a2e; color: #60a5fa; border: 1px solid #1d4ed8; }
.badge-purple { background: #160d2a; color: #a78bfa; border: 1px solid #5b21b6; }
.badge-gray   { background: #0c1525; color: #64748b; border: 1px solid #1e293b; }

/* ---- Anomaly Card ---- */
.anomaly-card {
    background: #0c1525;
    border: 1px solid #1a2540;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 12px;
    transition: border-color 0.2s;
}
.anomaly-card:hover { border-color: #334155; }
.anomaly-card-pending {
    border-left: 3px solid #f59e0b;
}
.anomaly-amount {
    font-size: 1.5rem;
    font-weight: 700;
    color: #ef4444;
    letter-spacing: -0.02em;
}
.anomaly-meta {
    font-size: 11px;
    color: #4a6080;
    margin: 4px 0 10px;
}
.anomaly-detail {
    font-size: 12px;
    color: #8098b8;
    line-height: 1.6;
}
.score-bar-bg {
    background: #1a2540;
    border-radius: 9999px;
    height: 5px;
    margin-top: 6px;
    overflow: hidden;
}
.score-bar {
    height: 5px;
    border-radius: 9999px;
    transition: width 0.6s ease;
}

/* ---- Section Title ---- */
.section-title {
    font-size: 10px;
    font-weight: 700;
    color: #334155;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding-bottom: 10px;
    border-bottom: 1px solid #0f1e35;
    margin-bottom: 14px;
}

/* ---- Divider ---- */
.cs-divider {
    height: 1px;
    background: #0f1e35;
    margin: 20px 0;
}

/* ---- Alert banners ---- */
.banner-warning {
    background: #1c1007;
    border: 1px solid #b45309;
    border-left: 4px solid #f59e0b;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
    color: #d97706;
    margin-bottom: 14px;
}
.banner-error {
    background: #1a0505;
    border: 1px solid #7f1d1d;
    border-left: 4px solid #ef4444;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
    color: #ef4444;
    margin-bottom: 14px;
}
.banner-info {
    background: #061428;
    border: 1px solid #1e3a5f;
    border-left: 4px solid #3b82f6;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
    color: #60a5fa;
    margin-bottom: 14px;
}
.banner-success {
    background: #052e16;
    border: 1px solid #166534;
    border-left: 4px solid #22c55e;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
    color: #22c55e;
    margin-bottom: 14px;
}

/* ---- Streamlit Button overrides ---- */
.stButton > button {
    border-radius: 8px;
    font-weight: 500;
    font-size: 13px;
    transition: all 0.2s;
    padding: 8px 18px;
}
.stButton > button[kind="primary"] {
    background: #1d4ed8;
    border: 1px solid #2563eb;
}

/* ---- Tabs ---- */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #0c1525;
    border-radius: 10px;
    padding: 4px;
    border: 1px solid #1a2540;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 7px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 500;
    background: transparent;
    color: #4a6080;
}
.stTabs [aria-selected="true"] {
    background: #1a2f52 !important;
    color: #e8f0fe !important;
}

/* ---- Selectbox / Inputs ---- */
div[data-baseweb="select"] > div {
    background: #0c1525;
    border-color: #1a2540;
    border-radius: 8px;
}

/* ---- Metric override ---- */
div[data-testid="metric-container"] > div {
    background: transparent;
}

/* ---- Sidebar nav links ---- */
.stSidebarNav a {
    font-size: 13px;
    font-weight: 500;
    padding: 8px 12px;
    border-radius: 8px;
    margin-bottom: 2px;
    transition: background 0.15s;
}
.stSidebarNav a:hover { background: #1a2540; }

/* ---- Dataframe container ---- */
.stDataFrame { border-radius: 10px; overflow: hidden; }

/* ---- Upload area ---- */
div[data-testid="stFileUploadDropzone"] {
    border: 2px dashed #1a3060;
    border-radius: 12px;
    background: #070d1a;
    transition: border-color 0.2s;
}
div[data-testid="stFileUploadDropzone"]:hover {
    border-color: #3b82f6;
}
</style>
"""


def inject_global_css() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    html = f'<div class="page-header"><h1 class="page-title">{title}</h1>'
    if subtitle:
        html += f'<p class="page-subtitle">{subtitle}</p>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def kpi_card(label: str, value: str, sub: str = "", color: str = "default") -> str:
    color_map = {
        "green": "kpi-card-green",
        "red": "kpi-card-red",
        "orange": "kpi-card-orange",
        "blue": "kpi-card-blue",
        "purple": "kpi-card-purple",
        "default": "",
    }
    value_colors = {
        "green": "#22c55e",
        "red": "#ef4444",
        "orange": "#f59e0b",
        "blue": "#60a5fa",
        "purple": "#a78bfa",
        "default": "#e8f0fe",
    }
    cls = color_map.get(color, "")
    vc = value_colors.get(color, "#e8f0fe")
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""<div class="kpi-card {cls}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{vc};">{value}</div>
        {sub_html}
    </div>"""


def agent_node(number: str, name: str, events: int, errors: int) -> str:
    if events == 0:
        css = "agent-gray"
    elif errors == 0:
        css = "agent-green"
    elif errors / max(events, 1) < 0.25:
        css = "agent-orange"
    else:
        css = "agent-red"

    err_str = f"· {errors} error{'s' if errors != 1 else ''}" if errors > 0 else "· no errors"
    return f"""<div class="agent-node {css}">
        <div class="agent-num">AGENT {number}</div>
        <div class="agent-name">{name}</div>
        <div class="agent-count">{events}</div>
        <div class="agent-errors">{err_str}</div>
    </div>"""


def badge(text: str, color: str = "gray") -> str:
    return f'<span class="badge badge-{color}">{text}</span>'

"""Single source of truth for the frontend's color palette and the global
polish CSS layered on top of native Streamlit theming (.streamlit/config.toml
sets the base colors Streamlit itself understands — widget fills, borders,
sidebar; this module adds the semantic tokens Streamlit has no concept of —
success/warning/danger — plus the chrome-level styling that makes cards,
tabs, metrics and alerts read as one cohesive, professional app instead of
default widgets. Import PALETTE for one-off inline styles (score colors,
platform dots) instead of hardcoding hex elsewhere; call inject_global_css()
once, from streamlit_app.py, so it applies across every module page.

Palette is the conventional enterprise CRM/marketing-platform look
(Salesforce/HubSpot-style blue-on-slate, not a purple/creative-tool accent)
— keep "primary"/"primary_dark" here in sync with primaryColor/the sidebar
block in .streamlit/config.toml if either changes."""
import streamlit as st

PALETTE = {
    "primary": "#2563eb",
    "primary_dark": "#1d4ed8",
    "primary_soft": "#eff6ff",
    "success": "#15803d",
    "success_soft": "#ecfdf5",
    "warning": "#b45309",
    "warning_soft": "#fffbeb",
    "danger": "#b91c1c",
    "danger_soft": "#fef2f2",
    "text": "#0f172a",
    "text_muted": "#64748b",
    "border": "#e2e8f0",
    "surface": "#ffffff",
    "surface_alt": "#f8fafc",
    "canvas": "#f1f5f9",
}


def score_color(score: float) -> str:
    if score >= 8:
        return PALETTE["success"]
    if score >= 5:
        return PALETTE["warning"]
    return PALETTE["danger"]


def inject_global_css() -> None:
    st.html(f"""
    <style>
    :root {{
        --pal-primary: {PALETTE["primary"]};
        --pal-primary-dark: {PALETTE["primary_dark"]};
        --pal-primary-soft: {PALETTE["primary_soft"]};
        --pal-success: {PALETTE["success"]};
        --pal-success-soft: {PALETTE["success_soft"]};
        --pal-warning: {PALETTE["warning"]};
        --pal-warning-soft: {PALETTE["warning_soft"]};
        --pal-danger: {PALETTE["danger"]};
        --pal-danger-soft: {PALETTE["danger_soft"]};
        --pal-text-muted: {PALETTE["text_muted"]};
        --pal-border: {PALETTE["border"]};
        --pal-surface: {PALETTE["surface"]};
        --pal-surface-alt: {PALETTE["surface_alt"]};
        --pal-canvas: {PALETTE["canvas"]};
    }}

    /* Headings: tighter, heavier, a professional editorial feel */
    h1, [data-testid="stHeading"] h1 {{
        font-weight: 800 !important;
        letter-spacing: -0.02em;
    }}
    h2, h3, [data-testid="stHeading"] h2, [data-testid="stHeading"] h3 {{
        font-weight: 700 !important;
        letter-spacing: -0.01em;
    }}
    [data-testid="stCaptionContainer"] {{ color: var(--pal-text-muted); }}

    /* Cards (st.container(border=True)): white surfaces elevated off the
       tinted canvas, with a soft shadow + lift on hover */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: var(--pal-surface);
        border-radius: 14px !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 8px rgba(15, 23, 42, 0.04);
        transition: box-shadow .15s ease;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
        box-shadow: 0 2px 4px rgba(15, 23, 42, 0.06), 0 4px 16px rgba(15, 23, 42, 0.06);
    }}

    /* Metrics: elevate into a small stat card */
    div[data-testid="stMetric"] {{
        background: var(--pal-surface-alt);
        border: 1px solid var(--pal-border);
        border-top: 3px solid var(--pal-primary);
        border-radius: 12px;
        padding: .85rem 1rem .7rem;
    }}
    [data-testid="stMetricLabel"] {{
        text-transform: uppercase;
        letter-spacing: .05em;
        font-size: .7rem !important;
        font-weight: 700 !important;
        color: var(--pal-text-muted);
    }}

    /* Buttons: crisper primary CTA, subtle lift on hover */
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
        border-radius: 9px !important;
        font-weight: 600 !important;
        transition: transform .06s ease, box-shadow .15s ease;
    }}
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
        box-shadow: 0 1px 2px rgba(37, 99, 235, .25);
    }}
    .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {{
        background-color: var(--pal-primary-dark) !important;
        border-color: var(--pal-primary-dark) !important;
        transform: translateY(-1px);
    }}

    /* Tabs: underline-style active indicator instead of default pill */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        gap: 1.5rem;
        border-bottom: 1px solid var(--pal-border);
    }}
    [data-testid="stTabs"] [data-baseweb="tab"] {{
        font-weight: 600;
        color: var(--pal-text-muted);
        padding-bottom: .6rem;
    }}
    [data-testid="stTabs"] [aria-selected="true"] {{
        color: var(--pal-primary) !important;
    }}

    /* Alerts: left accent bar so success/warning/error/info read at a glance */
    div[data-testid="stAlertContainer"] {{
        border-radius: 10px !important;
        border-left: 4px solid currentColor;
    }}

    /* Expanders: subtle header background so nested content feels contained */
    [data-testid="stExpander"] summary {{
        border-radius: 10px;
        font-weight: 600;
    }}

    /* Code blocks (the AI-written image prompt) — tinted panel, since the
       theme's secondary background is now white and would vanish into cards */
    [data-testid="stCode"] pre {{
        background: var(--pal-surface-alt) !important;
        border: 1px solid var(--pal-border);
        border-radius: 10px;
    }}

    /* Sidebar nav: a touch more breathing room between module links */
    section[data-testid="stSidebar"] [data-testid="stPageLink"] {{
        border-radius: 8px;
        margin-bottom: 2px;
    }}
    </style>
    """)

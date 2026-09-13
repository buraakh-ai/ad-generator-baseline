"""Shared helpers for talking to a module's backend. Each module (Ad
generator today, Lead generator and others later) can point at its own
backend container — this project's stated direction is one backend per
module, each its own AWS ECS service — so the backend URL is resolved
per-module rather than as one global constant.

resolve_backend_url(module_env_var) checks that module-specific env var
first (e.g. AD_GENERATOR_BACKEND_URL), then falls back to the original
BACKEND_BASE_URL (so existing single-backend .env files keep working
unchanged), then a localhost default."""
import os

import requests
import streamlit as st


def resolve_backend_url(module_env_var: str, default: str = "http://localhost:8000") -> str:
    return os.getenv(module_env_var) or os.getenv("BACKEND_BASE_URL") or default


def make_api(base_url: str):
    """Returns an `_api(method, path, **kwargs)` bound to this module's
    backend — a thin JSON-over-HTTP call that raises on non-2xx responses."""

    def _api(method, path, **kwargs):
        r = requests.request(method, f"{base_url}{path}", timeout=180, **kwargs)
        r.raise_for_status()
        return r.json()

    return _api


@st.cache_data(ttl=30, show_spinner=False)
def backend_online(base_url: str) -> bool:
    try:
        return requests.get(f"{base_url}/", timeout=2).status_code == 200
    except Exception:
        return False

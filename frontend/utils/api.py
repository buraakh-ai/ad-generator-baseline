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


def resolve_backend_url(module_env_var: str, default: str = "http://localhost:8000") -> str:
    return os.getenv(module_env_var) or os.getenv("BACKEND_BASE_URL") or default


def env_flag(name: str, default: bool = False) -> bool:
    """Reads a boolean feature flag straight from the frontend's own env —
    for UI-visibility toggles a module wants to gate without a backend
    round-trip. Not the same env-var namespace as the backend's own
    core.config.Settings (they're separate deployables); set the flag in
    whichever .env this frontend process actually reads."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def make_api(base_url: str):
    """Returns an `_api(method, path, **kwargs)` bound to this module's
    backend — a thin JSON-over-HTTP call that raises on non-2xx responses."""

    def _api(method, path, **kwargs):
        r = requests.request(method, f"{base_url}{path}", timeout=180, **kwargs)
        r.raise_for_status()
        return r.json()

    return _api

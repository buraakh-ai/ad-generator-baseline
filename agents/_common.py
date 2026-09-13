"""Shared helper used by every platform copy agent (tiktok/instagram/
twitter/facebook/linkedin) so each of those files stays focused on just its
platform's prompt + posting logic instead of re-deriving the same
Agno-Agent-with-model_router-fallback + JSON-parsing boilerplate five times.
Not itself an agent — agents/*.py files are."""
import json

from core.agno_models import build_agno_agent
from core.model_router import generate_text
from core.prompt_loader import render


def strip_json_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def generate_platform_copy(prompt_name: str, complexity: str = "high", **prompt_kwargs) -> str:
    """Renders prompts/<prompt_name>.yaml, runs it as a real Agno Agent
    (falling back to core.model_router if Agno isn't available or its API
    doesn't match), and returns the platform's "caption" field."""
    system_prompt, user_prompt = render(prompt_name, **prompt_kwargs)

    try:
        agent = build_agno_agent(complexity=complexity, instructions=system_prompt)
        result = agent.run(user_prompt)
        raw = getattr(result, "content", None) or str(result)
    except Exception as e:
        print(f"[{prompt_name}] Agno path unavailable ({e}) — using model_router fallback")
        raw = generate_text(user_prompt, system_prompt, complexity=complexity)

    try:
        data = json.loads(strip_json_fence(raw))
        return data.get("caption", raw).strip()
    except Exception:
        return raw.strip()

"""LLM router — OpenAI only, two complexity tiers.

generate_text(prompt, system_prompt, complexity="low"|"high") calls
settings.openai_text_model (gpt-4o-mini by default) for "low" — short,
low-risk generations (the creative-brief headline, the quality-review
score) — and settings.openai_high_end_text_model (a genuinely stronger
model, gpt-5.5 by default) for "high" — brand-sensitive/creative work: ad
copy, company research, event selection, and the image poster-prompt
writer (skills/image_compositing_skill.py).

Newer OpenAI models (gpt-5.x and later) reject the legacy `max_tokens`
chat-completions parameter and require `max_completion_tokens` instead;
gpt-4o-mini accepts either, so every call here just uses
`max_completion_tokens` uniformly rather than branching per model.

Every call is bounded by settings.max_llm_attempts (retries against
transient failures) so nothing can loop forever."""
import time

from core.config import settings

call_counter = {"count": 0}


class AllProvidersExhaustedError(Exception):
    pass


def _model_for(complexity):
    return settings.openai_high_end_text_model if complexity == "high" else settings.openai_text_model


def _call_openai(prompt, system_prompt="", complexity="high"):
    import requests

    if not settings.openai_api_key:
        raise Exception("No OPENAI_API_KEY configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    model = _model_for(complexity)
    last_err = None
    for attempt in range(settings.max_llm_attempts):
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "max_completion_tokens": 2000},
                timeout=60,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            last_err = Exception(f"OpenAI {model} {r.status_code}: {r.text[:200]}")
        except Exception as e:
            last_err = e
        if attempt < settings.max_llm_attempts - 1:
            time.sleep(min(2 ** attempt, 8))
    raise last_err or Exception("OpenAI failed after all retries")


def generate_text(prompt: str, system_prompt: str = "", complexity: str = "high") -> str:
    """Generates text via OpenAI. Raises AllProvidersExhaustedError if the
    call fails after settings.max_llm_attempts retries, so callers keep the
    same exception contract as when this router tried multiple providers."""
    call_counter["count"] += 1
    try:
        return _call_openai(prompt, system_prompt, complexity=complexity)
    except Exception as e:
        raise AllProvidersExhaustedError(f"OpenAI failed: {e}") from e

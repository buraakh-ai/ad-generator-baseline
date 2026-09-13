"""LLM router — OpenAI only.

generate_text(prompt, system_prompt, complexity="low"|"high") calls a
single OpenAI chat model (settings.openai_text_model, gpt-4o-mini by
default — cheap, fast, and supports tool calling if a skill ever needs
it). The `complexity` parameter is kept purely for call-site compatibility
— every skill/agent already passes it — in case a future need reintroduces
per-tier models; both tiers currently resolve to the same provider/model.

Every call is bounded by settings.max_llm_attempts (retries against
transient failures) so nothing can loop forever."""
import time

from core.config import settings

call_counter = {"count": 0}


class AllProvidersExhaustedError(Exception):
    pass


def _call_openai(prompt, system_prompt=""):
    import requests

    if not settings.openai_api_key:
        raise Exception("No OPENAI_API_KEY configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_err = None
    for attempt in range(settings.max_llm_attempts):
        try:
            r = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
                json={"model": settings.openai_text_model, "messages": messages, "max_tokens": 2000},
                timeout=60,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            last_err = Exception(f"OpenAI {r.status_code}: {r.text[:200]}")
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
        return _call_openai(prompt, system_prompt)
    except Exception as e:
        raise AllProvidersExhaustedError(f"OpenAI failed: {e}") from e

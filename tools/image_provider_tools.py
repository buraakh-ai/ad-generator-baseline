"""Per-provider background-image generation calls (OpenAI only), plus the
dispatcher that picks the active provider (from image_config.json via
core.image_models) and reports which provider to fall forward to if it
fails. Retry counts come from settings.max_image_attempts instead of a
hardcoded loop bound."""
from io import BytesIO

import requests
from PIL import Image

from core.config import settings
from core.image_models import get_active_provider, get_next_provider


class ProviderFailedError(Exception):
    def __init__(self, message, failed_provider, next_provider_name, next_provider_label):
        super().__init__(message)
        self.failed_provider = failed_provider
        self.next_provider_name = next_provider_name
        self.next_provider_label = next_provider_label


def _generate_openai_image(prompt: str, api_key: str = "", model: str = None) -> Image.Image:
    """OpenAI's current best-quality image model (gpt-image-1) via the
    Images API."""
    key = api_key or settings.openai_api_key
    if not key:
        raise Exception("OpenAI image generation requires OPENAI_API_KEY")
    model = model or settings.openai_image_model
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "prompt": prompt[:4000], "n": 1, "size": "1024x1536"},
        timeout=120,
    )
    if r.status_code != 200:
        raise Exception(f"OpenAI {model} {r.status_code}: {r.text[:200]}")
    data = r.json()["data"][0]
    if data.get("b64_json"):
        import base64
        return Image.open(BytesIO(base64.b64decode(data["b64_json"]))).convert("RGB")
    return Image.open(BytesIO(requests.get(data["url"], timeout=60).content)).convert("RGB")


def _generate_openai_dalle3(prompt: str, api_key: str = "") -> Image.Image:
    key = api_key or settings.openai_api_key
    if not key:
        raise Exception("OpenAI DALL-E 3 requires OPENAI_API_KEY")
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": settings.openai_fallback_image_model, "prompt": prompt[:4000],
            "n": 1, "size": "1024x1792", "response_format": "url",
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise Exception(f"OpenAI DALL-E 3 {r.status_code}: {r.text[:200]}")
    return Image.open(BytesIO(requests.get(r.json()["data"][0]["url"], timeout=60).content)).convert("RGB")


_PROVIDER_FUNCS = {
    "openai_image": _generate_openai_image,
    "openai_dalle3": _generate_openai_dalle3,
}


def generate_background(prompt: str, config: dict) -> Image.Image:
    provider = get_active_provider(config)
    name = provider["name"]
    api_key = provider.get("api_key", "")
    next_provider = get_next_provider(config)

    print(f"[image] using provider: {name}")
    fn = _PROVIDER_FUNCS.get(name, _PROVIDER_FUNCS["openai_image"])

    try:
        return fn(prompt, api_key)
    except Exception as e:
        err = str(e)
        print(f"[image] provider {name} failed: {err}")
        if next_provider:
            raise ProviderFailedError(err, name, next_provider["name"], next_provider["label"])
        raise

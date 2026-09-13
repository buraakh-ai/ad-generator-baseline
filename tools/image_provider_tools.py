"""Per-provider full-poster image generation calls (OpenAI only — the
model draws the whole ad, including headline/CTA/icon text, directly; see
skills/image_compositing_skill.py for how the prompt describing that
poster gets built), plus the dispatcher that picks the active provider
(from image_config.json via core.image_models) and reports which provider
to fall forward to if it fails. Retry counts come from
settings.max_image_attempts instead of a hardcoded loop bound."""
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
    """gpt-image-2.5-sunburst / gpt-image-1 via the Images API — both draw
    the full poster (headline, bullets, CTA button, icons) directly rather
    than a plain photo, so `quality: "high"` matters here for legible
    typography; both models accept it.

    Size matters more than usual here too: skills/image_compositing_skill.py
    center-crops whatever comes back to a fixed 4:5 (TARGET_W/TARGET_H =
    1080x1350), and since the poster's own headline/CTA/bullets now run
    right up to the model's own canvas edges, a mismatched aspect ratio
    crops real content off — this is what "1024x1536" (2:3) did to gpt-image-
    1's output before this fix. gpt-image-2+ accepts arbitrary custom sizes,
    so we ask for 1024x1280 (exactly 4:5, no crop at all); gpt-image-1 only
    accepts a handful of fixed presets (no custom sizes), so it gets the
    closest preset instead and still takes some crop loss — a known
    limitation of that fallback tier, not of the primary model."""
    key = api_key or settings.openai_api_key
    if not key:
        raise Exception("OpenAI image generation requires OPENAI_API_KEY")
    model = model or settings.openai_image_model
    size = "1024x1280" if model.startswith("gpt-image-2") else "1024x1536"
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "prompt": prompt[:4000], "n": 1, "size": size, "quality": "high"},
        timeout=180,
    )
    if r.status_code != 200:
        raise Exception(f"OpenAI {model} {r.status_code}: {r.text[:200]}")
    data = r.json()["data"][0]
    if data.get("b64_json"):
        import base64
        return Image.open(BytesIO(base64.b64decode(data["b64_json"]))).convert("RGB")
    return Image.open(BytesIO(requests.get(data["url"], timeout=60).content)).convert("RGB")


def _generate_openai_dalle3(prompt: str, api_key: str = "") -> Image.Image:
    """Last-resort fallback. DALL-E 3 predates gpt-image's native text
    rendering and reliably garbles poster text/logos — this tier exists so
    the app still produces *an* image if both gpt-image tiers are down, not
    because it can replicate the poster style."""
    key = api_key or settings.openai_api_key
    if not key:
        raise Exception("OpenAI DALL-E 3 requires OPENAI_API_KEY")
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": settings.openai_last_resort_image_model, "prompt": prompt[:4000],
            "n": 1, "size": "1024x1792", "response_format": "url",
        },
        timeout=120,
    )
    if r.status_code != 200:
        raise Exception(f"OpenAI DALL-E 3 {r.status_code}: {r.text[:200]}")
    return Image.open(BytesIO(requests.get(r.json()["data"][0]["url"], timeout=60).content)).convert("RGB")


_PROVIDER_FUNCS = {
    "openai_image": _generate_openai_image,
    "openai_image_fallback": lambda prompt, api_key: _generate_openai_image(
        prompt, api_key, model=settings.openai_fallback_image_model
    ),
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

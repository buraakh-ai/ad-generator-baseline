"""Image agent — builds the background-image prompt (gpt-4o-mini-generated
scene description, see skills/image_compositing_skill.py), generates it
through the active image-provider chain (tools/image_provider_tools.py,
gpt-image-1 by default), and composites the final display/clean ad images
(skills/image_compositing_skill.py). Invoked as its own explicit step from
the backend (POST /generate-image), same as the original app — not part of
the automatic sequential text-campaign orchestration, so the user can
review copy before spending an image-generation call."""
from core.image_models import load_config
from skills.image_compositing_skill import build_image_prompt, composite_ad_image
from tools.image_provider_tools import ProviderFailedError, generate_background

__all__ = ["ProviderFailedError", "generate_ad_image"]


def generate_ad_image(company_name, instagram_copy, image_headline,
                       event_context, company_details, logo_url=None,
                       custom_prompt=None, static_dir="static"):
    """Returns (display_path, clean_path, prompt_used) — prompt_used is
    whatever was actually sent to the image provider (the AI-generated
    scene wrapped in the image_prompt.yaml template, or custom_prompt
    verbatim if one was given), so callers can show it back to the user."""
    config = load_config()

    print(f"[image_agent] logo URL received: {logo_url}")

    if custom_prompt:
        prompt = custom_prompt
        print(f"[image_agent] using custom prompt override: {prompt[:160]}...")
    else:
        prompt = build_image_prompt(
            company_name, instagram_copy, event_context, company_details, config,
            image_headline=image_headline,
        )
        print(f"[image_agent] prompt: {prompt[:160]}...")

    print("[image_agent] generating background...")
    base_image = generate_background(prompt, config)

    display_path, clean_path = composite_ad_image(
        base_image, company_name, image_headline, instagram_copy, logo_url, static_dir=static_dir
    )
    return display_path, clean_path, prompt

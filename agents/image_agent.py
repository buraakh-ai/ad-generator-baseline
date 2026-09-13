"""Image agent — builds the full poster-design prompt (gpt-4o-mini-written
brief describing headline/bullets/CTA/layout, see
skills/image_compositing_skill.py), generates the finished poster through
the active image-provider chain (tools/image_provider_tools.py,
gpt-image-2.5-sunburst by default — it draws the poster's own text/CTA/
icons directly), and lightly finishes the display/clean versions (real
logo + CEO-photo stamp, Instagram UI-preview chrome,
skills/image_compositing_skill.py). Invoked as its own explicit step from
the backend (POST /generate-image), same as the original app — not part of
the automatic sequential text-campaign orchestration, so the user can
review copy before spending an image-generation call.

Brand assets (settings.brand_logo_url / brand_ceo_photo_url / brand_ceo_name
/ brand_ceo_title) are this deployment's own real assets — same
single-business scope as the Facebook/Instagram/LinkedIn credentials in
.env, not per-campaign. When configured, brand_logo_url overrides whatever
logo_url the research step found, and a CEO headshot card is composited
into every image; the AI poster-prompt writer is told to leave the
corresponding corners clear rather than drawing its own logo/wordmark
there. Leave these blank to keep the original behavior (Clearbit-researched
logo, no CEO card).

The image's CTA is a real contact URL printed as small plain text rather
than a drawn "button" graphic — a generated image can't actually be
clickable, so a fake button promising a link that doesn't work is worse
than honest text. That URL is per-campaign, passed in as `contact_url`
(the frontend's Generate-tab field, falling back to the company's own
website if the user left it blank) — settings.brand_contact_url is only a
last-resort deployment-wide default for callers that don't pass one (e.g.
scripts/batch_run.py)."""
from core.config import settings
from core.image_models import load_config
from skills.image_compositing_skill import build_image_prompt, composite_ad_image, fetch_ceo_photo, fetch_logo
from tools.image_provider_tools import ProviderFailedError, generate_background

__all__ = ["ProviderFailedError", "generate_ad_image"]


def generate_ad_image(company_name, instagram_copy, image_headline,
                       event_context, company_details, logo_url=None,
                       custom_prompt=None, contact_url=None, static_dir="static"):
    """Returns (display_path, clean_path, prompt_used) — prompt_used is
    whatever was actually sent to the image provider (the AI-written poster
    brief, or custom_prompt verbatim if one was given), so callers can show
    it back to the user."""
    config = load_config()
    contact_url = (contact_url or "").strip() or settings.brand_contact_url

    # This deployment's own real logo, if configured, always wins over
    # whatever the research step guessed from Clearbit. has_real_branding
    # is based on whether the fetch actually succeeds — not just whether a
    # URL is configured — so a broken/unreachable image URL doesn't leave
    # the poster with a corner reserved for a logo/photo that never shows
    # up (composite_ad_image re-fetches these; a transient failure between
    # the two fetches is the one edge case this doesn't cover).
    logo_url = settings.brand_logo_url or logo_url
    logo_available = bool(fetch_logo(logo_url)) if logo_url else False
    ceo_available = bool(
        settings.brand_ceo_photo_url and settings.brand_ceo_name and fetch_ceo_photo(settings.brand_ceo_photo_url)
    )
    has_real_branding = logo_available or ceo_available

    print(f"[image_agent] logo URL: {logo_url} (available: {logo_available}), CEO photo available: {ceo_available}")

    if custom_prompt:
        prompt = custom_prompt
        print(f"[image_agent] using custom prompt override: {prompt[:160]}...")
    else:
        prompt = build_image_prompt(
            company_name, instagram_copy, event_context, company_details, config,
            image_headline=image_headline, has_real_branding=has_real_branding,
            contact_url=contact_url,
        )
        print(f"[image_agent] prompt: {prompt[:160]}...")

    print("[image_agent] generating poster...")
    base_image = generate_background(prompt, config)

    display_path, clean_path = composite_ad_image(
        base_image, company_name, instagram_copy, logo_url,
        ceo_photo_url=settings.brand_ceo_photo_url,
        ceo_name=settings.brand_ceo_name,
        ceo_title=settings.brand_ceo_title,
        static_dir=static_dir,
    )
    return display_path, clean_path, prompt

"""Central settings object. Every credential and tunable in the project is
read from the environment (populated from .env via python-dotenv) so no
secret ever lives in source code. See .env.example for the full list."""
import os

from dotenv import load_dotenv

load_dotenv()


def _split(name, default=""):
    raw = os.getenv(name, default)
    return [p.strip() for p in raw.split(",") if p.strip()]


def _int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    def __init__(self):
        # ---- OpenAI (the only LLM/image provider). Text is two-tier again:
        # "low" (gpt-4o-mini) for short, low-risk generations (the creative-
        # brief headline, the quality-review score); "high" (a genuinely
        # stronger model) for brand-sensitive/creative work — ad copy,
        # company research, event selection, and the image poster-prompt
        # writer. Images are a 3-tier fallback chain, best quality first:
        # gpt-image-2.5-sunburst -> gpt-image-1 -> dall-e-3 (see
        # tools/image_provider_tools.py) ----
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")
        self.openai_high_end_text_model = os.getenv("OPENAI_HIGH_END_TEXT_MODEL", "gpt-5.5")
        self.openai_image_model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst")
        self.openai_fallback_image_model = os.getenv("OPENAI_FALLBACK_IMAGE_MODEL", "gpt-image-1")
        self.openai_last_resort_image_model = os.getenv("OPENAI_LAST_RESORT_IMAGE_MODEL", "dall-e-3")

        # ---- AWS (S3 for generated images + Secrets Manager for social
        # tokens and the app-secrets overlay below) ----
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID", "")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        self.aws_region = os.getenv("AWS_REGION", "us-east-2")
        self.aws_bucket_name = os.getenv("AWS_BUCKET_NAME", "")
        self.business_id = os.getenv("BUSINESS_ID", "default-business")
        self.app_secrets_name = f"ad-generator/{self.business_id}/app-secrets"

        # ---- Brand assets (this deployment's own real logo/CEO photo —
        # same single-business scope as the Facebook/Instagram/LinkedIn
        # credentials above, not per-campaign). When set, these override the
        # Clearbit-researched logo_url and add a CEO headshot card to every
        # generated ad image (see skills/image_compositing_skill.py). Public
        # URLs only — e.g. a public-read S3 object, same convention
        # tools/s3_tool.py already uses for generated images. Leave blank to
        # skip (falls back to the researched logo_url, no CEO card). ----
        self.brand_logo_url = os.getenv("BRAND_LOGO_URL", "")
        self.brand_ceo_photo_url = os.getenv("BRAND_CEO_PHOTO_URL", "")
        self.brand_ceo_name = os.getenv("BRAND_CEO_NAME", "")
        self.brand_ceo_title = os.getenv("BRAND_CEO_TITLE", "")
        # A generated image can't actually be clickable on social media, so
        # rather than draw a fake "button" graphic, the poster prints this
        # URL as plain small text near the bottom when it's set (see
        # skills/image_compositing_skill.py's cta_note). Leave blank to keep
        # the old behavior (a drawn CTA button label, no real URL).
        self.brand_contact_url = os.getenv("BRAND_CONTACT_URL", "")

        # ---- Facebook ----
        self.facebook_page_id = os.getenv("FACEBOOK_PAGE_ID", "")
        self.facebook_page_token = os.getenv("FACEBOOK_PAGE_TOKEN", "")
        self.facebook_app_id = os.getenv("FACEBOOK_APP_ID", "")
        self.facebook_app_secret = os.getenv("FACEBOOK_APP_SECRET", "")
        self.facebook_secret_name = f"ad-generator/{self.business_id}/facebook-token"

        # ---- Instagram ----
        self.instagram_user_id = os.getenv("INSTAGRAM_USER_ID", "")
        self.instagram_access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.instagram_refresh_after_days = _int("INSTAGRAM_REFRESH_AFTER_DAYS", 50)
        self.instagram_secret_name = f"ad-generator/{self.business_id}/instagram-token"

        # ---- LinkedIn ----
        self.linkedin_access_token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
        self.linkedin_token_issued_at = os.getenv("LINKEDIN_TOKEN_ISSUED_AT", "")
        self.linkedin_client_id = os.getenv("LINKEDIN_CLIENT_ID", "")
        self.linkedin_client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "")
        self.linkedin_oauth_redirect_uri = os.getenv("LINKEDIN_OAUTH_REDIRECT_URI", "http://localhost:8000")
        self.linkedin_token_lifetime_days = _int("LINKEDIN_TOKEN_LIFETIME_DAYS", 60)
        self.linkedin_expiry_warning_days = _int("LINKEDIN_EXPIRY_WARNING_DAYS", 10)
        self.linkedin_api_version = os.getenv("LINKEDIN_API_VERSION", "202601")
        self.linkedin_secret_name = f"ad-generator/{self.business_id}/linkedin-token"

        # ---- Paid ad management (Meta Marketing API + LinkedIn Marketing
        # API — distinct from the organic-posting credentials above; both
        # need a separate, more selective API product/app-review approval
        # from their platform than plain posting does). Every campaign this
        # app creates is forced to PAUSED (Meta) / DRAFT (LinkedIn) — never
        # ACTIVE — regardless of any other input; activating one (spending
        # real budget) is a separate, explicit action. See
        # tools/facebook_ads_tool.py / tools/linkedin_ads_tool.py. ----
        self.facebook_ad_account_id = os.getenv("FACEBOOK_AD_ACCOUNT_ID", "")
        self.facebook_marketing_access_token = os.getenv("FACEBOOK_MARKETING_ACCESS_TOKEN", "") or self.facebook_page_token
        self.facebook_ad_currency = os.getenv("FACEBOOK_AD_CURRENCY", "USD")

        self.linkedin_ad_account_id = os.getenv("LINKEDIN_AD_ACCOUNT_ID", "")
        self.linkedin_marketing_access_token = os.getenv("LINKEDIN_MARKETING_ACCESS_TOKEN", "") or self.linkedin_access_token
        self.linkedin_ad_currency = os.getenv("LINKEDIN_AD_CURRENCY", "USD")

        # Shared secret required to actually activate a draft campaign (the
        # one call that spends real money) — checked server-side in
        # backend/main.py's /activate-*-ad-campaign endpoints, so it can't
        # be bypassed by calling the API directly. Left blank, activation
        # is blocked entirely (fail-closed) rather than silently allowed.
        self.campaign_execution_password = os.getenv("CAMPAIGN_EXECUTION_PASSWORD", "")

        # ---- Loop-safety: every retry/fallback loop in the project reads
        # its bound from here instead of hardcoding a number. ----
        self.max_llm_attempts = _int("MAX_LLM_ATTEMPTS", 3)
        self.max_image_attempts = _int("MAX_IMAGE_ATTEMPTS", 3)
        self.max_media_poll_attempts = _int("MAX_MEDIA_POLL_ATTEMPTS", 10)

        # ---- Backend / frontend wiring ----
        self.backend_host = os.getenv("BACKEND_HOST", "0.0.0.0")
        self.backend_port = _int("BACKEND_PORT", 8000)
        self.backend_base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
        # Origins allowed to call the backend directly from browser JS (the
        # Streamlit frontend itself calls over server-to-server HTTP, which
        # CORS doesn't apply to — this only matters if something browser-based
        # calls the API from a different origin). "*" is fine for a
        # credential-less API like this one; tighten via CORS_ALLOW_ORIGINS
        # (comma-separated) if you don't want that.
        self.cors_allow_origins = _split("CORS_ALLOW_ORIGINS") or ["*"]

        # ---- Misc ----
        self.debug = _bool("DEBUG", False)

    def refresh_from_aws_secrets(self):
        """Overlays the static app secrets (OPENAI_API_KEY, Facebook/LinkedIn
        app credentials) from AWS Secrets Manager (self.app_secrets_name),
        if that secret exists — call once at backend startup. Locally, or
        anywhere AWS Secrets Manager isn't reachable, get_secret() returns
        None and this is a no-op: whatever .env already set stands. This is
        the same "AWS Secrets Manager first, .env fallback" pattern the
        rotating Facebook/Instagram/LinkedIn *tokens* already use (see
        tools/facebook_tool.refresh_facebook_token() and friends) — those
        have their own dedicated secrets and are unaffected by this method.

        The secret, if you create it, is a single JSON object, e.g.:
            {"OPENAI_API_KEY": "...", "FACEBOOK_APP_ID": "...",
             "FACEBOOK_APP_SECRET": "...", "LINKEDIN_CLIENT_ID": "...",
             "LINKEDIN_CLIENT_SECRET": "..."}
        Only keys matching an existing attribute name (case-insensitively)
        are applied."""
        import json

        from tools.secrets_tool import get_secret  # local import: avoids a
        # circular import, since tools.secrets_tool imports settings itself

        raw = get_secret(self.app_secrets_name)
        if not raw:
            return
        applied = []
        for key, value in json.loads(raw).items():
            attr = key.lower()
            if value and hasattr(self, attr):
                setattr(self, attr, value)
                applied.append(key)
        if applied:
            print(f"[config] loaded from AWS Secrets Manager ({self.app_secrets_name}): {', '.join(applied)}")


settings = Settings()

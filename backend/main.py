"""FastAPI backend. Same endpoints/JSON contracts as the original Flask
app.py, now backed by the agents/skills/tools/prompts structure. This file
is the HTTP transport over agents/orchestrator.py and agents/image_agent.py
for the frontend (frontend/streamlit_app.py). (mcp_server/server.py exposes
the same agents as MCP tools, but it's scaffolding for a future release —
not started here, not part of this deployment; see its module docstring.)

One behavioral change from the original app: there's no more
`provider_switched` response for text generation. The old app made the
client re-submit /generate after one provider's keys were exhausted and it
switched to another mid-request. Text generation is OpenAI-only now
(core.model_router, gpt-4o-mini by default) — /generate either succeeds or
returns `exhausted: true` if OpenAI fails after all configured retries."""
import hmac
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents import facebook_agent, image_agent, instagram_agent, linkedin_agent, orchestrator
from backend.schemas import (ActivateFacebookAdRequest, ActivateLinkedInAdRequest, CreateFacebookAdRequest,
                              CreateLinkedInAdRequest, GenerateImageRequest, GenerateRequest, PostRequest,
                              RetryEventRequest, SwitchProviderRequest)
from core.config import settings
from core.image_models import get_providers, load_config
from core.model_router import AllProvidersExhaustedError, call_counter
from tools.facebook_ads_tool import FacebookAdsError
from tools.facebook_tool import refresh_facebook_token
from tools.image_provider_tools import ProviderFailedError
from tools.linkedin_ads_tool import LinkedInAdsError
from tools.linkedin_tool import check_linkedin_token_expiry

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATIC_DIR = os.path.join(_ROOT_DIR, "static")
os.makedirs(_STATIC_DIR, exist_ok=True)

app = FastAPI(title="Ad Generator API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# company_name/url -> {"company_data": {...}, "website_url": str}
company_cache: dict = {}


@app.on_event("startup")
def _startup():
    try:
        settings.refresh_from_aws_secrets()
    except Exception as e:
        print(f"[startup] AWS secrets refresh failed (non-fatal): {e}")
    try:
        refresh_facebook_token()
    except Exception as e:
        print(f"[startup] facebook token refresh failed (non-fatal): {e}")
    try:
        check_linkedin_token_expiry()
    except Exception as e:
        print(f"[startup] linkedin token check failed (non-fatal): {e}")


@app.get("/")
def index():
    return {
        "service": "ad-generator-backend",
        "status": "ok",
        "docs": "/docs",
        "note": "The UI lives in the separately-deployed Streamlit frontend (frontend/streamlit_app.py).",
    }


@app.get("/privacy-policy")
def privacy_policy():
    return FileResponse(os.path.join(_ROOT_DIR, "privacy_policy.html"))


def _resolve_local_image_path(image_url: str) -> str:
    if "static/" in image_url:
        return "static/" + image_url.split("static/")[-1].split("?")[0]
    return image_url.lstrip("/").split("?")[0]


def _check_execution_password(password: str) -> str:
    """Gate for the two endpoints that actually spend money. Returns an
    error string if the check fails, or "" if it passes. Fails closed: an
    unconfigured CAMPAIGN_EXECUTION_PASSWORD blocks activation entirely
    rather than allowing it through on an empty/missing password."""
    if not settings.campaign_execution_password:
        return "Campaign execution is locked: CAMPAIGN_EXECUTION_PASSWORD is not configured."
    if not password or not hmac.compare_digest(password, settings.campaign_execution_password):
        return "Incorrect execution password."
    return ""


@app.post("/generate")
def generate(req: GenerateRequest):
    try:
        cache_key = (req.company_url or req.company_name).lower().strip()

        result = orchestrator.run_campaign(
            company_name=req.company_name,
            product_description=req.product_description,
            ad_idea=req.ad_idea,
            event_context=req.event_context,
            company_url=req.company_url,
        )
        company_cache[cache_key] = {
            "company_data": result["company_data"],
            "website_url": result["website_url"],
        }

        ads = result["ads"]
        return {
            "success": True,
            "ads": ads,
            "detected_company_name": result["company_name"],
            "detected_event": result["detected_event"],
            "company_details": result["company_data"],
            "website_url": result["website_url"],
            "image_headline": ads.get("image_headline", ""),
            "quality_score": ads.get("quality_score", 0),
            "quality_reason": ads.get("quality_reason", ""),
        }

    except AllProvidersExhaustedError as e:
        return JSONResponse({"success": False, "exhausted": True, "error": str(e)})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/retry-event")
def retry_event(req: RetryEventRequest):
    try:
        cache_key = (req.company_url or req.company_name).lower().strip()
        if cache_key not in company_cache:
            return JSONResponse(
                {"success": False, "error": "No cached company data. Please generate from scratch first."},
                status_code=400,
            )

        cached = company_cache[cache_key]
        result = orchestrator.run_campaign(
            company_name=req.company_name,
            company_data=cached["company_data"],
            website_url=cached["website_url"],
        )

        ads = result["ads"]
        return {
            "success": True,
            "ads": ads,
            "detected_company_name": result["company_name"],
            "detected_event": result["detected_event"],
            "company_details": result["company_data"],
            "website_url": result["website_url"],
            "image_headline": ads.get("image_headline", ""),
            "quality_score": ads.get("quality_score", 0),
            "quality_reason": ads.get("quality_reason", ""),
        }

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/generate-image")
def generate_image(req: GenerateImageRequest):
    try:
        display_path, clean_path, prompt_used = image_agent.generate_ad_image(
            req.company_name, req.instagram_copy, req.image_headline,
            req.event_context, req.company_details, req.logo_url,
            custom_prompt=req.custom_prompt.strip() or None,
            contact_url=req.contact_url.strip() or None,
            static_dir=_STATIC_DIR,
        )

        config = load_config()
        provider = config.get("active_provider", "openai_image")

        return {
            "success": True,
            "image_url": "/static/" + os.path.basename(display_path),
            "clean_image_url": "/static/" + os.path.basename(clean_path),
            "provider": provider,
            "prompt": prompt_used,
        }

    except ProviderFailedError as e:
        return JSONResponse({
            "success": False,
            "provider_failed": True,
            "failed_provider": e.failed_provider,
            "next_provider_name": e.next_provider_name,
            "next_provider_label": e.next_provider_label,
            "error": str(e),
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/switch-image-provider")
def switch_image_provider(req: SwitchProviderRequest):
    try:
        from core.image_models import save_active_provider
        save_active_provider(req.provider)
        return {"success": True, "provider": req.provider}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/get-image-providers")
def get_image_providers():
    try:
        config = load_config()
        providers = get_providers(config)
        active = config.get("active_provider", "openai_image")
        return {"success": True, "providers": providers, "active": active}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/post-to-instagram")
def post_instagram(req: PostRequest):
    try:
        local_path = _resolve_local_image_path(req.image_url)
        print(f"[instagram] local path resolved: {local_path}")
        if not os.path.exists(local_path):
            return JSONResponse({"success": False, "error": f"Image file not found: {local_path}"}, status_code=400)
        post_id = instagram_agent.post(local_path, req.caption)
        return {"success": True, "post_id": post_id}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/post-to-facebook")
def post_facebook(req: PostRequest):
    try:
        local_path = _resolve_local_image_path(req.image_url)
        print(f"[facebook] local path resolved: {local_path}")
        if not os.path.exists(local_path):
            return JSONResponse({"success": False, "error": f"Image file not found: {local_path}"}, status_code=400)
        post_id = facebook_agent.post(local_path, req.caption)
        return {"success": True, "post_id": post_id}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/post-to-linkedin")
def post_linkedin(req: PostRequest):
    try:
        local_path = _resolve_local_image_path(req.image_url)
        print(f"[linkedin] local path resolved: {local_path}")
        if not os.path.exists(local_path):
            return JSONResponse({"success": False, "error": f"Image file not found: {local_path}"}, status_code=400)
        post_id = linkedin_agent.post(local_path, req.caption)
        return {"success": True, "post_id": post_id}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Paid ad management (Meta + LinkedIn Marketing APIs). Every campaign these
# create is forced to PAUSED (Meta) / DRAFT (LinkedIn) — activation is a
# separate endpoint the frontend only calls after explicit human
# confirmation. See tools/facebook_ads_tool.py / tools/linkedin_ads_tool.py.
# ---------------------------------------------------------------------------

@app.post("/create-facebook-ad-campaign")
def create_facebook_ad_campaign(req: CreateFacebookAdRequest):
    try:
        local_path = _resolve_local_image_path(req.image_url)
        if not os.path.exists(local_path):
            return JSONResponse({"success": False, "error": f"Image file not found: {local_path}"}, status_code=400)
        result = facebook_agent.create_ad_campaign(
            req.name, local_path, req.message, req.link, req.daily_budget_usd, req.countries,
            req.start_time, req.end_time,
        )
        return {"success": True, **result}
    except FacebookAdsError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/activate-facebook-ad-campaign")
def activate_facebook_ad_campaign(req: ActivateFacebookAdRequest):
    password_error = _check_execution_password(req.password)
    if password_error:
        return JSONResponse({"success": False, "error": password_error}, status_code=403)
    try:
        facebook_agent.activate_ad_campaign(req.campaign_id, req.adset_id, req.ad_id)
        return {"success": True}
    except FacebookAdsError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/create-linkedin-ad-campaign")
def create_linkedin_ad_campaign(req: CreateLinkedInAdRequest):
    try:
        result = linkedin_agent.create_ad_campaign(
            req.name, req.share_urn, req.daily_budget_usd, req.country_code, req.start_time_ms, req.end_time_ms,
        )
        return {"success": True, **result}
    except LinkedInAdsError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/activate-linkedin-ad-campaign")
def activate_linkedin_ad_campaign(req: ActivateLinkedInAdRequest):
    password_error = _check_execution_password(req.password)
    if password_error:
        return JSONResponse({"success": False, "error": password_error}, status_code=403)
    try:
        linkedin_agent.activate_ad_campaign(req.campaign_group_urn, req.campaign_urn, req.creative_urn)
        return {"success": True}
    except LinkedInAdsError as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/call-count")
def get_call_count():
    return {"count": call_counter["count"]}

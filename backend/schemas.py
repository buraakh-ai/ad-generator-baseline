"""Pydantic request/response models for the FastAPI backend. Field names
match the original Flask app's JSON contracts so the frontend/MCP layers
don't need to know anything changed under the hood."""
from typing import Optional

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    company_name: str = ""
    product_description: str = ""
    ad_idea: str = ""
    event_context: Optional[str] = None
    company_url: Optional[str] = None


class RetryEventRequest(BaseModel):
    company_name: str = ""
    company_url: str = ""


class GenerateImageRequest(BaseModel):
    company_name: str = ""
    instagram_copy: str = ""
    image_headline: str = ""
    event_context: str = ""
    company_details: dict = {}
    logo_url: Optional[str] = None
    custom_prompt: str = ""
    # Printed as small plain text near the bottom of the poster in place of
    # a CTA button (an image can't actually be clickable) — per-request,
    # overriding settings.brand_contact_url if both are set. Falls back to
    # that deployment-wide setting if left blank here.
    contact_url: str = ""


class SwitchProviderRequest(BaseModel):
    provider: str


class PostRequest(BaseModel):
    caption: str = ""
    image_url: str = ""


class CreateFacebookAdRequest(BaseModel):
    """Creates a draft (PAUSED) Meta ad campaign — see
    tools/facebook_ads_tool.py. image_url is a local /static path, same
    convention as PostRequest."""
    name: str = ""
    image_url: str = ""
    message: str = ""
    link: str = ""
    daily_budget_usd: float = 0.0
    countries: list[str] = ["US"]
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class ActivateFacebookAdRequest(BaseModel):
    campaign_id: str
    adset_id: str
    ad_id: str
    # Checked against settings.campaign_execution_password server-side —
    # this is the one call that spends real money.
    password: str = ""


class CreateLinkedInAdRequest(BaseModel):
    """Creates a draft (DRAFT status) LinkedIn ad campaign promoting an
    already-published post — see tools/linkedin_ads_tool.py."""
    name: str = ""
    share_urn: str = ""
    daily_budget_usd: float = 0.0
    country_code: str = "US"
    start_time_ms: int = 0
    end_time_ms: Optional[int] = None


class ActivateLinkedInAdRequest(BaseModel):
    campaign_group_urn: str
    campaign_urn: str
    creative_urn: str
    # Checked against settings.campaign_execution_password server-side —
    # this is the one call that spends real money.
    password: str = ""

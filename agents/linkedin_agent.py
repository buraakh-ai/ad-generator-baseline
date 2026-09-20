"""LinkedIn agent — writes a dedicated business-tone LinkedIn post (the
original app reused the Facebook caption for LinkedIn; this agent gets its
own prompt), can post it via tools/linkedin_tool.py (personal profile or a
company page), and can create/activate a paid ad campaign promoting an
already-posted update via tools/linkedin_ads_tool.py (a separate LinkedIn
Marketing API integration, distinct from organic posting — see that
module's docstring for why campaigns are always created DRAFT)."""
from agents._common import generate_platform_copy
from tools.linkedin_ads_tool import activate_campaign as _activate_ad_campaign
from tools.linkedin_ads_tool import create_draft_campaign as _create_draft_ad_campaign
from tools.linkedin_tool import post_to_linkedin as _post_to_linkedin
from tools.linkedin_tool import post_to_linkedin_company as _post_to_linkedin_company


def write_copy(**brief) -> str:
    return generate_platform_copy("ad_copy_linkedin", complexity="high", **brief)


def post(image_local_path: str, caption: str) -> str:
    return _post_to_linkedin(image_local_path, caption)


def post_as_company(image_local_path: str, caption: str, organization_id: str) -> str:
    return _post_to_linkedin_company(image_local_path, caption, organization_id)


def create_ad_campaign(name: str, share_urn: str, daily_budget_usd: float, country_code: str,
                        start_time_ms: int, end_time_ms: int = None) -> dict:
    """Creates a draft (DRAFT status) LinkedIn ad campaign promoting an
    already-published post (share_urn — the id post()/post_as_company()
    already returns). Returns the ids needed to activate it later —
    nothing here spends money."""
    return _create_draft_ad_campaign(name, share_urn, daily_budget_usd, country_code, start_time_ms, end_time_ms)


def activate_ad_campaign(campaign_group_urn: str, campaign_urn: str, creative_urn: str):
    """Flips a previously-created draft campaign to ACTIVE — this is the
    one call in the whole ads flow that spends real money. Only call it
    after explicit human confirmation."""
    _activate_ad_campaign(campaign_group_urn, campaign_urn, creative_urn)

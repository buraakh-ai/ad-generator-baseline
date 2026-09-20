"""Facebook agent — writes Facebook-specific ad copy and, once an image
exists, can post it to the connected Facebook Page via
tools/facebook_tool.py, or create/activate a paid ad campaign via
tools/facebook_ads_tool.py (a separate Meta Marketing API integration,
distinct from organic posting — see that module's docstring for why
campaigns are always created PAUSED)."""
from agents._common import generate_platform_copy
from tools.facebook_ads_tool import activate_campaign as _activate_ad_campaign
from tools.facebook_ads_tool import create_draft_campaign as _create_draft_ad_campaign
from tools.facebook_tool import post_to_facebook as _post_to_facebook


def write_copy(**brief) -> str:
    return generate_platform_copy("ad_copy_facebook", complexity="high", **brief)


def post(image_local_path: str, caption: str) -> str:
    return _post_to_facebook(image_local_path, caption)


def create_ad_campaign(name: str, image_local_path: str, message: str, link: str,
                        daily_budget_usd: float, countries: list,
                        start_time: str = None, end_time: str = None) -> dict:
    """Creates a draft (PAUSED) Meta ad campaign/ad set/ad. Returns the ids
    needed to activate it later — nothing here spends money."""
    return _create_draft_ad_campaign(name, image_local_path, message, link, daily_budget_usd, countries,
                                      start_time, end_time)


def activate_ad_campaign(campaign_id: str, adset_id: str, ad_id: str):
    """Flips a previously-created draft campaign to ACTIVE — this is the
    one call in the whole ads flow that spends real money. Only call it
    after explicit human confirmation."""
    _activate_ad_campaign(campaign_id, adset_id, ad_id)

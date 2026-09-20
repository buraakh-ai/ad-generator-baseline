"""Meta Marketing API — paid campaign creation (distinct from
tools/facebook_tool.py's organic Page posting; needs the `ads_management`
permission via Meta App Review, which the organic-posting page token
usually doesn't carry, hence the separate FACEBOOK_MARKETING_ACCESS_TOKEN
setting).

Every campaign/ad set/ad this module creates is hard-coded to
status="PAUSED" — Meta's API allows creating them ACTIVE, but this app
never does that. activate() is a separate, explicit call a human triggers
after reviewing the draft; nothing here ever spends money on its own.

Reference: https://developers.facebook.com/docs/marketing-api/reference/ad-campaign-group/
(Graph API v21.0, matching tools/facebook_tool.py's version)."""
import requests

from core.config import settings

_GRAPH_VERSION = "v21.0"
_BASE = f"https://graph.facebook.com/{_GRAPH_VERSION}"


class FacebookAdsError(Exception):
    pass


def _act(path: str) -> str:
    account_id = settings.facebook_ad_account_id
    numeric_id = account_id[4:] if account_id.startswith("act_") else account_id
    return f"{_BASE}/act_{numeric_id}{path}"


def _call(method: str, url: str, **kwargs) -> dict:
    kwargs.setdefault("timeout", 60)
    params = kwargs.pop("params", {}) or {}
    params["access_token"] = settings.facebook_marketing_access_token
    r = requests.request(method, url, params=params, **kwargs)
    data = r.json()
    if r.status_code != 200 or "error" in data:
        raise FacebookAdsError(f"{method} {url} failed: {data.get('error', data)}")
    return data


def upload_ad_image(image_local_path: str) -> str:
    """Uploads an image into the ad account's image library. Returns the
    image hash creatives reference (not the same as a public image URL)."""
    with open(image_local_path, "rb") as f:
        data = _call("POST", _act("/adimages"), files={"filename": f})
    images = data.get("images", {})
    if not images:
        raise FacebookAdsError(f"No image hash returned: {data}")
    return next(iter(images.values()))["hash"]


def create_campaign(name: str, objective: str = "OUTCOME_TRAFFIC") -> str:
    data = _call("POST", _act("/campaigns"), params={
        "name": name,
        "objective": objective,
        "status": "PAUSED",
        "special_ad_categories": "[]",
    })
    return data["id"]


def create_ad_set(campaign_id: str, name: str, daily_budget_usd: float, countries: list,
                   start_time: str = None, end_time: str = None,
                   optimization_goal: str = "LINK_CLICKS", billing_event: str = "IMPRESSIONS") -> str:
    """daily_budget_usd is plain dollars — converted to the minor currency
    unit (cents for USD) the API expects. countries is a list of ISO
    country codes, e.g. ["US"]."""
    import json

    params = {
        "name": name,
        "campaign_id": campaign_id,
        "daily_budget": str(int(round(daily_budget_usd * 100))),
        "billing_event": billing_event,
        "optimization_goal": optimization_goal,
        "targeting": json.dumps({"geo_locations": {"countries": countries}}),
        "status": "PAUSED",
    }
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time
    data = _call("POST", _act("/adsets"), params=params)
    return data["id"]


def create_ad_creative(name: str, page_id: str, image_hash: str, message: str, link: str) -> str:
    """link is the real destination URL — for a paid ad, Meta renders an
    actual clickable CTA button around the creative (unlike an organic
    post), so this is where the contact URL becomes genuinely clickable."""
    import json

    object_story_spec = {
        "page_id": page_id,
        "link_data": {
            "image_hash": image_hash,
            "message": message,
            "link": link,
            "call_to_action": {"type": "LEARN_MORE", "value": {"link": link}},
        },
    }
    data = _call("POST", _act("/adcreatives"), params={
        "name": name,
        "object_story_spec": json.dumps(object_story_spec),
    })
    return data["id"]


def create_ad(name: str, adset_id: str, creative_id: str) -> str:
    import json

    data = _call("POST", _act("/ads"), params={
        "name": name,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": "PAUSED",
    })
    return data["id"]


def create_draft_campaign(name: str, image_local_path: str, message: str, link: str,
                           daily_budget_usd: float, countries: list,
                           start_time: str = None, end_time: str = None) -> dict:
    """End-to-end draft creation: image -> campaign -> ad set -> creative ->
    ad, all PAUSED. Returns the ids for every level so activate_campaign()
    can flip them on later, and so the caller can show the user exactly
    what was created before they approve spending anything."""
    if not settings.facebook_ad_account_id:
        raise FacebookAdsError("FACEBOOK_AD_ACCOUNT_ID is not configured")
    if not settings.facebook_marketing_access_token:
        raise FacebookAdsError("No Facebook marketing access token configured "
                                "(FACEBOOK_MARKETING_ACCESS_TOKEN or FACEBOOK_PAGE_TOKEN)")

    print("[facebook_ads] uploading image...")
    image_hash = upload_ad_image(image_local_path)

    print(f"[facebook_ads] creating campaign '{name}' (PAUSED)...")
    campaign_id = create_campaign(name)

    print("[facebook_ads] creating ad set (PAUSED)...")
    adset_id = create_ad_set(campaign_id, f"{name} - ad set", daily_budget_usd, countries, start_time, end_time)

    print("[facebook_ads] creating ad creative...")
    creative_id = create_ad_creative(f"{name} - creative", settings.facebook_page_id, image_hash, message, link)

    print("[facebook_ads] creating ad (PAUSED)...")
    ad_id = create_ad(f"{name} - ad", adset_id, creative_id)

    print(f"[facebook_ads] draft campaign ready — campaign={campaign_id} adset={adset_id} ad={ad_id}")
    return {"campaign_id": campaign_id, "adset_id": adset_id, "creative_id": creative_id, "ad_id": ad_id}


def activate_campaign(campaign_id: str, adset_id: str, ad_id: str):
    """Flips campaign, ad set, and ad all to ACTIVE — Meta requires every
    level to be ACTIVE for an ad to actually serve, so all three are set
    here in one explicit call. This is the only function in this module
    that can cause real spend; call it only after explicit human
    confirmation."""
    print(f"[facebook_ads] ACTIVATING campaign={campaign_id} adset={adset_id} ad={ad_id} — this will start spending")
    _call("POST", f"{_BASE}/{campaign_id}", params={"status": "ACTIVE"})
    _call("POST", f"{_BASE}/{adset_id}", params={"status": "ACTIVE"})
    _call("POST", f"{_BASE}/{ad_id}", params={"status": "ACTIVE"})
    print("[facebook_ads] campaign activated")

"""LinkedIn Marketing API — paid campaign creation (distinct from
tools/linkedin_tool.py's organic posting; needs the rw_ads scope via
LinkedIn's Marketing Developer Platform product, which the
organic-posting token usually doesn't carry — hence the separate
LINKEDIN_MARKETING_ACCESS_TOKEN setting).

The ad creative references an EXISTING organic LinkedIn post/share (the
same one tools/linkedin_tool.post_to_linkedin[_company]() already
produces) rather than building new Direct Sponsored Content from scratch —
simpler, and reuses content this app can already post.

Every campaign group/campaign/creative this module creates is hard-coded
to status/intendedStatus="DRAFT" — never ACTIVE. activate_campaign() is a
separate, explicit call a human triggers after reviewing the draft;
nothing here spends money on its own.

Reference: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/ads/
(versioned REST API — same LinkedIn-Version/X-Restli-Protocol-Version
header convention as tools/linkedin_tool.py)."""
import urllib.parse

import requests

from core.config import settings

_BASE = "https://api.linkedin.com/rest"

# A handful of common countries -> LinkedIn geo URNs for whole-country
# targeting (LinkedIn has no public lookup-by-ISO-code endpoint; these are
# its well-known stable values). Add more here as needed.
COUNTRY_GEO_URNS = {
    "US": "urn:li:geo:103644278",
    "GB": "urn:li:geo:101165590",
    "CA": "urn:li:geo:101174742",
    "IN": "urn:li:geo:102713980",
    "AU": "urn:li:geo:101452733",
}


class LinkedInAdsError(Exception):
    pass


def _headers(extra=None):
    headers = {
        "Authorization": f"Bearer {settings.linkedin_marketing_access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": settings.linkedin_api_version,
    }
    if extra:
        headers.update(extra)
    return headers


def _request(method, url, extra_headers=None, **kwargs):
    kwargs.setdefault("timeout", 60)
    r = requests.request(method, url, headers=_headers(extra_headers), **kwargs)
    if r.status_code not in (200, 201, 204):
        raise LinkedInAdsError(f"{method} {url} failed: {r.status_code} {r.text[:400]}")
    return r


def _created_urn(response, fallback_field="id"):
    """LinkedIn's versioned REST API returns a new entity's URN in the
    x-restli-id response header (URL-encoded), not the JSON body — same
    convention tools/linkedin_tool.py's _create_post() already relies on.
    Falls back to a JSON body field defensively in case a given endpoint
    differs."""
    header_id = response.headers.get("x-restli-id")
    if header_id:
        return urllib.parse.unquote(header_id)
    try:
        data = response.json()
    except ValueError:
        data = {}
    return data.get(fallback_field) or data.get("entity") or "unknown"


def _account_urn() -> str:
    return f"urn:li:sponsoredAccount:{settings.linkedin_ad_account_id}"


def create_campaign_group(name: str, start_time_ms: int, total_budget_usd: float = None) -> str:
    payload = {
        "account": _account_urn(),
        "name": name,
        "runSchedule": {"start": start_time_ms},
        "status": "DRAFT",
    }
    if total_budget_usd:
        payload["totalBudget"] = {"amount": str(total_budget_usd), "currencyCode": settings.linkedin_ad_currency}
    r = _request("POST", f"{_BASE}/adAccounts/{settings.linkedin_ad_account_id}/adCampaignGroups", json=payload)
    return _created_urn(r)


def create_campaign(name: str, campaign_group_urn: str, daily_budget_usd: float, country_code: str,
                     start_time_ms: int, end_time_ms: int = None,
                     objective_type: str = "WEBSITE_VISIT", unit_cost_usd: float = 2.0) -> str:
    """country_code must be a key in COUNTRY_GEO_URNS. unit_cost_usd is the
    manual max bid per click — LinkedIn requires SOME value here even for
    simple setups; it's editable in Campaign Manager after creation."""
    geo_urn = COUNTRY_GEO_URNS.get(country_code.upper())
    if not geo_urn:
        raise LinkedInAdsError(
            f"Unsupported country code {country_code!r} — add it to COUNTRY_GEO_URNS "
            f"(supported: {', '.join(COUNTRY_GEO_URNS)})"
        )
    payload = {
        "account": _account_urn(),
        "campaignGroup": campaign_group_urn,
        "name": name,
        "type": "SPONSORED_UPDATES",
        "objectiveType": objective_type,
        "costType": "CPC",
        "unitCost": {"amount": str(unit_cost_usd), "currencyCode": settings.linkedin_ad_currency},
        "dailyBudget": {"amount": str(daily_budget_usd), "currencyCode": settings.linkedin_ad_currency},
        "locale": {"country": country_code.upper(), "language": "en"},
        "offsiteDeliveryEnabled": False,
        "audienceExpansionEnabled": False,
        "runSchedule": {"start": start_time_ms, **({"end": end_time_ms} if end_time_ms else {})},
        "targetingCriteria": {
            "include": {"and": [{"or": {"urn:li:adTargetingFacet:locations": [geo_urn]}}]},
        },
        # Required by LinkedIn for EU-region ad compliance; this app never
        # generates political advertising.
        "politicalIntent": "NOT_POLITICAL",
        "status": "DRAFT",
    }
    r = _request("POST", f"{_BASE}/adAccounts/{settings.linkedin_ad_account_id}/adCampaigns", json=payload)
    return _created_urn(r)


def create_creative(campaign_urn: str, share_urn: str) -> str:
    """share_urn is an existing organic post's URN (urn:li:share:... or
    urn:li:ugcPost:...) — e.g. the post_id tools/linkedin_tool.py's
    post_to_linkedin()/post_to_linkedin_company() already returns."""
    payload = {
        "campaign": campaign_urn,
        "content": {"reference": share_urn},
        "intendedStatus": "DRAFT",
    }
    r = _request("POST", f"{_BASE}/adAccounts/{settings.linkedin_ad_account_id}/creatives", json=payload)
    return _created_urn(r)


def create_draft_campaign(name: str, share_urn: str, daily_budget_usd: float, country_code: str,
                           start_time_ms: int, end_time_ms: int = None) -> dict:
    """End-to-end draft creation: campaign group -> campaign -> creative,
    all DRAFT. Returns every id so activate_campaign() can flip them on
    later, and so the caller can show the user exactly what was created
    before they approve spending anything."""
    if not settings.linkedin_ad_account_id:
        raise LinkedInAdsError("LINKEDIN_AD_ACCOUNT_ID is not configured")
    if not settings.linkedin_marketing_access_token:
        raise LinkedInAdsError("No LinkedIn marketing access token configured "
                                "(LINKEDIN_MARKETING_ACCESS_TOKEN or LINKEDIN_ACCESS_TOKEN)")

    print(f"[linkedin_ads] creating campaign group '{name}' (DRAFT)...")
    campaign_group_urn = create_campaign_group(name, start_time_ms)

    print("[linkedin_ads] creating campaign (DRAFT)...")
    campaign_urn = create_campaign(
        f"{name} - campaign", campaign_group_urn, daily_budget_usd, country_code, start_time_ms, end_time_ms,
    )

    print("[linkedin_ads] creating creative referencing existing post (DRAFT)...")
    creative_urn = create_creative(campaign_urn, share_urn)

    print(f"[linkedin_ads] draft campaign ready — group={campaign_group_urn} campaign={campaign_urn} creative={creative_urn}")
    return {"campaign_group_urn": campaign_group_urn, "campaign_urn": campaign_urn, "creative_urn": creative_urn}


def _set_status(resource_path: str, status_field: str, status_value: str = "ACTIVE"):
    _request(
        "POST", resource_path,
        extra_headers={"X-RestLi-Method": "PARTIAL_UPDATE"},
        json={"patch": {"$set": {status_field: status_value}}},
    )


def activate_campaign(campaign_group_urn: str, campaign_urn: str, creative_urn: str):
    """Flips campaign group, campaign, and creative all to ACTIVE —
    LinkedIn won't serve a campaign whose group is still DRAFT even if the
    campaign itself is ACTIVE, so all three are set here in one explicit
    call. This is the only function in this module that can cause real
    spend; call it only after explicit human confirmation."""
    account = settings.linkedin_ad_account_id
    print(f"[linkedin_ads] ACTIVATING group={campaign_group_urn} campaign={campaign_urn} "
          f"creative={creative_urn} — this will start spending")
    group_id = urllib.parse.quote(campaign_group_urn, safe="")
    campaign_id = urllib.parse.quote(campaign_urn, safe="")
    creative_id = urllib.parse.quote(creative_urn, safe="")
    _set_status(f"{_BASE}/adAccounts/{account}/adCampaignGroups/{group_id}", "status")
    _set_status(f"{_BASE}/adAccounts/{account}/adCampaigns/{campaign_id}", "status")
    _set_status(f"{_BASE}/adAccounts/{account}/creatives/{creative_id}", "intendedStatus")
    print("[linkedin_ads] campaign activated")

"""LinkedIn posting via the versioned REST API. LinkedIn access tokens
can't be silently refreshed — they must be re-issued via
scripts/get_linkedin_token.py, which pushes the new token to AWS Secrets
Manager (or LINKEDIN_ACCESS_TOKEN in .env as the fallback)."""
import json
from datetime import datetime, timedelta

import requests

from core.config import settings
from tools.s3_tool import upload_to_s3
from tools.secrets_tool import get_secret

_state = {
    "access_token": settings.linkedin_access_token,
    "issued_at": settings.linkedin_token_issued_at or datetime.now().isoformat(),
}


def load_linkedin_credentials():
    """Fetches the current access token + issue date from AWS Secrets
    Manager, falling back to .env values if the secret doesn't exist yet or
    AWS can't be reached. Called before anything that needs the token."""
    raw = get_secret(settings.linkedin_secret_name)
    if raw:
        data = json.loads(raw)
        _state["access_token"] = data["access_token"]
        _state["issued_at"] = data["issued_at"]
        print(f"[linkedin] loaded access token from AWS Secrets Manager ({settings.linkedin_secret_name})")
    return _state["access_token"], _state["issued_at"]


def check_linkedin_token_expiry() -> int:
    """Tokens can't be refreshed — just report the expiry date and warn
    once it's within LINKEDIN_EXPIRY_WARNING_DAYS of expiring."""
    load_linkedin_credentials()
    issued_at = datetime.fromisoformat(_state["issued_at"])
    expires_at = issued_at + timedelta(days=settings.linkedin_token_lifetime_days)
    days_left = (expires_at - datetime.now()).days
    print(f"[linkedin] access token expires on {expires_at.strftime('%Y-%m-%d')} ({days_left} days left)")
    if days_left <= settings.linkedin_expiry_warning_days:
        print(f"[linkedin] WARNING: token expires in {days_left} days and cannot be auto-refreshed — re-run scripts/get_linkedin_token.py")
    return days_left


def get_person_urn() -> str:
    headers = {"Authorization": f"Bearer {_state['access_token']}"}
    r = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=30)
    if r.status_code != 200:
        raise Exception(f"Failed to fetch LinkedIn member info: {r.status_code} {r.text[:200]}")
    return f"urn:li:person:{r.json()['sub']}"


def _register_and_upload_image(image_local_path: str, owner_urn: str) -> str:
    headers = {
        "Authorization": f"Bearer {_state['access_token']}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": settings.linkedin_api_version,
    }
    init_payload = {"initializeUploadRequest": {"owner": owner_urn}}
    r = requests.post(
        "https://api.linkedin.com/rest/images?action=initializeUpload",
        headers=headers, json=init_payload, timeout=30,
    )
    result = r.json()
    if r.status_code != 200:
        raise Exception(f"LinkedIn image upload initialization failed: {result}")

    upload_url = result["value"]["uploadUrl"]
    image_urn = result["value"]["image"]
    print(f"[linkedin] image upload initialized — asset: {image_urn}")

    with open(image_local_path, "rb") as f:
        image_data = f.read()
    r = requests.put(
        upload_url, headers={"Authorization": f"Bearer {_state['access_token']}"},
        data=image_data, timeout=60,
    )
    if r.status_code not in (200, 201):
        raise Exception(f"LinkedIn image upload failed: {r.status_code} {r.text[:200]}")
    print("[linkedin] image uploaded successfully")
    return image_urn


def _create_post(author_urn: str, caption: str, image_urn: str) -> str:
    headers = {
        "Authorization": f"Bearer {_state['access_token']}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": settings.linkedin_api_version,
    }
    post_payload = {
        "author": author_urn,
        "commentary": caption,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "content": {"media": {"altText": "Ad", "id": image_urn}},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    r = requests.post("https://api.linkedin.com/rest/posts", headers=headers, json=post_payload, timeout=60)
    if r.status_code not in (200, 201):
        raise Exception(f"Failed to post to LinkedIn: {r.status_code} {r.text[:300]}")
    return r.headers.get("x-restli-id", "unknown")


def post_to_linkedin(image_local_path: str, caption: str) -> str:
    print("[linkedin] starting post process...")
    check_linkedin_token_expiry()

    person_urn = get_person_urn()
    print(f"[linkedin] person URN: {person_urn}")

    upload_to_s3(image_local_path, prefix="li_ad")
    image_urn = _register_and_upload_image(image_local_path, person_urn)

    print("[linkedin] creating post...")
    post_id = _create_post(person_urn, caption, image_urn)
    print(f"[linkedin] posted successfully! post ID: {post_id}")
    return post_id


def post_to_linkedin_company(image_local_path: str, caption: str, organization_id: str) -> str:
    """Same flow as post_to_linkedin, but posts as a LinkedIn Organization
    page. organization_id must be formatted as urn:li:organization:NUMERIC_ID,
    and the token must carry the w_organization_social scope with admin
    access on that page."""
    print("[linkedin] starting company post process...")
    check_linkedin_token_expiry()
    print(f"[linkedin] organization URN: {organization_id}")

    upload_to_s3(image_local_path, prefix="li_ad")
    image_urn = _register_and_upload_image(image_local_path, organization_id)

    print("[linkedin] creating company post...")
    post_id = _create_post(organization_id, caption, image_urn)
    print(f"[linkedin] posted to company page successfully! post ID: {post_id}")
    return post_id

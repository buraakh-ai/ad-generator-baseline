"""Facebook Page posting. Token is read from AWS Secrets Manager if
available, falling back to FACEBOOK_PAGE_TOKEN from .env."""
import json

import requests

from core.config import settings
from tools.s3_tool import upload_to_s3
from tools.secrets_tool import get_secret, put_secret

_state = {"page_token": settings.facebook_page_token}


def refresh_facebook_token():
    """Loads the current page token from AWS Secrets Manager (if reachable),
    then exchanges it for a long-lived one if FACEBOOK_APP_ID/SECRET are
    set. Call once on app startup."""
    raw = get_secret(settings.facebook_secret_name)
    if raw:
        _state["page_token"] = json.loads(raw)["access_token"]
        print(f"[facebook] loaded page token from AWS Secrets Manager ({settings.facebook_secret_name})")

    if not settings.facebook_app_id or not settings.facebook_app_secret:
        print("[facebook] skipping token exchange — FACEBOOK_APP_ID/FACEBOOK_APP_SECRET not set")
        return

    print("[facebook] refreshing page access token...")
    r = requests.get(
        "https://graph.facebook.com/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.facebook_app_id,
            "client_secret": settings.facebook_app_secret,
            "fb_exchange_token": _state["page_token"],
        },
        timeout=30,
    )
    result = r.json()
    if "access_token" not in result:
        print(f"[facebook] token refresh failed, continuing with existing token: {result}")
        return

    _state["page_token"] = result["access_token"]
    put_secret(settings.facebook_secret_name, json.dumps({"access_token": _state["page_token"]}))
    print(f"[facebook] page access token refreshed and saved ({settings.facebook_secret_name})")


def post_to_facebook(image_local_path: str, caption: str) -> str:
    image_url = upload_to_s3(image_local_path, prefix="fb_ad")
    print(f"[facebook] posting image: {image_url}")

    post_url = f"https://graph.facebook.com/v21.0/{settings.facebook_page_id}/photos"
    post_payload = {"url": image_url, "message": caption, "access_token": _state["page_token"]}

    print("[facebook] creating photo post...")
    r = requests.post(post_url, data=post_payload, timeout=60)
    result = r.json()
    print(f"[facebook] response: {result}")

    if "id" not in result:
        raise Exception(f"Failed to post to Facebook: {result}")

    post_id = result["id"]
    print(f"[facebook] posted successfully! post ID: {post_id}")
    return post_id

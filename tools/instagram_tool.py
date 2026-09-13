"""Instagram posting via the Graph API. Token is read from AWS Secrets
Manager if available, falling back to INSTAGRAM_ACCESS_TOKEN from .env.
Media-processing poll is bounded by settings.max_media_poll_attempts
instead of a hardcoded loop."""
import json
import time
from datetime import datetime

import requests

from core.config import settings
from tools.s3_tool import upload_to_s3
from tools.secrets_tool import get_secret, put_secret

_state = {"access_token": settings.instagram_access_token}


def _load_token_state():
    raw = get_secret(settings.instagram_secret_name)
    if raw:
        return json.loads(raw)
    return {"access_token": settings.instagram_access_token, "issued_at": datetime.now().isoformat()}


def refresh_instagram_token_if_needed():
    state = _load_token_state()
    issued_at = datetime.fromisoformat(state["issued_at"])
    age_days = (datetime.now() - issued_at).days
    _state["access_token"] = state["access_token"]

    if age_days < settings.instagram_refresh_after_days:
        return

    print(f"[instagram] token is {age_days} days old — refreshing...")
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": _state["access_token"]},
        timeout=30,
    )
    result = r.json()
    if "access_token" not in result:
        print(f"[instagram] token refresh failed, continuing with existing token: {result}")
        return

    _state["access_token"] = result["access_token"]
    put_secret(settings.instagram_secret_name, json.dumps({
        "access_token": _state["access_token"], "issued_at": datetime.now().isoformat(),
    }))
    print("[instagram] token refreshed successfully (valid ~60 more days)")


def _check_media_status(container_id: str) -> bool:
    status_url = f"https://graph.instagram.com/v21.0/{container_id}"
    for attempt in range(settings.max_media_poll_attempts):
        r = requests.get(status_url, params={
            "fields": "status_code,status", "access_token": _state["access_token"],
        }, timeout=30)
        result = r.json()
        status = result.get("status_code", "")
        print(f"[instagram] media status check {attempt + 1}/{settings.max_media_poll_attempts}: {status}")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            raise Exception(f"Media processing failed: {result}")
        time.sleep(3)
    return False


def post_to_instagram(image_local_path: str, caption: str) -> str:
    refresh_instagram_token_if_needed()

    image_url = upload_to_s3(image_local_path, prefix="ig_ad")
    print(f"[instagram] posting image: {image_url}")

    container_url = f"https://graph.instagram.com/v21.0/{settings.instagram_user_id}/media"
    container_payload = {"image_url": image_url, "caption": caption, "access_token": _state["access_token"]}
    print("[instagram] creating media container...")
    r = requests.post(container_url, data=container_payload, timeout=60)
    result = r.json()
    if "id" not in result:
        raise Exception(f"Failed to create container: {result}")

    container_id = result["id"]
    print(f"[instagram] container created: {container_id}")

    print("[instagram] waiting for media to be ready...")
    ready = _check_media_status(container_id)
    if not ready:
        print("[instagram] status check inconclusive — waiting 10 extra seconds...")
        time.sleep(10)

    publish_url = f"https://graph.instagram.com/v21.0/{settings.instagram_user_id}/media_publish"
    publish_payload = {"creation_id": container_id, "access_token": _state["access_token"]}
    print("[instagram] publishing post...")
    r = requests.post(publish_url, data=publish_payload, timeout=60)
    result = r.json()
    if "id" not in result:
        raise Exception(f"Failed to publish: {result}")

    print(f"[instagram] posted successfully! post ID: {result['id']}")
    return result["id"]

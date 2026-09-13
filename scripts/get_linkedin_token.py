"""One-off interactive script to (re)authenticate with LinkedIn and push
the resulting access token to AWS Secrets Manager (falling back to just
printing it if AWS can't be reached). LinkedIn tokens can't be refreshed
programmatically — re-run this whenever tools/linkedin_tool.py warns that
the current token is close to expiring.

Run with:  python -m scripts.get_linkedin_token
Requires LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET in .env.
"""
import json
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from core.config import settings
from tools.secrets_tool import aws_client

SCOPE = "openid profile w_member_social"

auth_url = (
    "https://www.linkedin.com/oauth/v2/authorization"
    "?response_type=code"
    f"&client_id={settings.linkedin_client_id}"
    f"&redirect_uri={urllib.parse.quote(settings.linkedin_oauth_redirect_uri)}"
    f"&scope={SCOPE}"
)

code_holder = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            code_holder["code"] = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorization successful! You can close this tab.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Error: no code found.")

    def log_message(self, format, *args):
        pass


def main():
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        print("LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET must be set in .env before running this.")
        return

    import webbrowser
    print("Opening LinkedIn authorization page...")
    webbrowser.open(auth_url)
    print("Waiting for authorization...")

    host, port = urllib.parse.urlparse(settings.linkedin_oauth_redirect_uri).netloc.split(":")
    server = HTTPServer((host, int(port)), Handler)
    server.handle_request()

    if "code" not in code_holder:
        print("Failed to get code.")
        return

    code = code_holder["code"]
    print("Got code — exchanging for token...")

    r = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.linkedin_oauth_redirect_uri,
            "client_id": settings.linkedin_client_id,
            "client_secret": settings.linkedin_client_secret,
        },
    )
    result = r.json()
    print(f"Response: {result}")

    if "access_token" not in result:
        print(f"Failed: {result}")
        return

    print("SUCCESS!")
    print(f"Access Token: {result['access_token']}")
    print(f"Expires in: {result.get('expires_in', 'unknown')} seconds")

    secret_value = json.dumps({
        "access_token": result["access_token"],
        "issued_at": datetime.now().date().isoformat(),
    })
    client = aws_client("secretsmanager")
    try:
        client.put_secret_value(SecretId=settings.linkedin_secret_name, SecretString=secret_value)
        print(f"Pushed new token to AWS Secrets Manager ({settings.linkedin_secret_name})")
    except client.exceptions.ResourceNotFoundException:
        client.create_secret(Name=settings.linkedin_secret_name, SecretString=secret_value)
        print(f"Created secret in AWS Secrets Manager ({settings.linkedin_secret_name})")
    except Exception as e:
        print(f"Could not push token to AWS Secrets Manager: {e}")
        print("Set LINKEDIN_ACCESS_TOKEN / LINKEDIN_TOKEN_ISSUED_AT in .env manually as a fallback.")


if __name__ == "__main__":
    main()

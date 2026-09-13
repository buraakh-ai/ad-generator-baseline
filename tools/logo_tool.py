"""Company-logo lookup via Clearbit's free logo API, keyed off a domain."""
import requests


def find_company_logo(company_name: str, website_url: str = None) -> str:
    if website_url:
        domain = website_url.replace("https://", "").replace("http://", "").split("/")[0]
        return f"https://logo.clearbit.com/{domain}"
    domain = company_name.lower().replace(" ", "") + ".com"
    return f"https://logo.clearbit.com/{domain}"


def find_company_logo_by_domain(domain: str) -> str:
    """Given a guessed domain, verify Clearbit has a logo before returning
    it; falls back to Google's favicon service otherwise."""
    domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").strip("/")
    logo_url = f"https://logo.clearbit.com/{domain}"
    try:
        check = requests.head(logo_url, timeout=5)
        if check.status_code == 200:
            return logo_url
    except Exception:
        pass
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

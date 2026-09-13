"""Website scraping — used by the research agent to ground company
analysis in real page content instead of the model's own guesses."""
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def scrape_website_text(url: str, max_chars: int = 5000) -> str:
    """Plain-text scrape: strips script/style/nav/footer/header, returns
    the remaining visible text, truncated to max_chars."""
    try:
        print(f"[scrape] {url}...")
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = " ".join(soup.get_text().split())
        return text[:max_chars]
    except Exception as e:
        print(f"[scrape] {e}")
        return ""


def scrape_company(url: str) -> dict:
    """Structured scrape: company name, description, tagline, logo, and raw
    text, pulled from meta tags / headings / images."""
    result = {
        "company_name": "", "description": "", "logo_url": "",
        "tagline": "", "raw_text": "",
    }
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        og_site = soup.find("meta", property="og:site_name")
        if og_site:
            result["company_name"] = og_site.get("content", "")
        elif soup.title:
            result["company_name"] = soup.title.text.strip().split("|")[0].split("-")[0].strip()

        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if og_desc:
            result["description"] = og_desc.get("content", "")
        elif meta_desc:
            result["description"] = meta_desc.get("content", "")

        hero_tags = soup.find_all(["h1", "h2"], limit=3)
        taglines = [h.get_text(strip=True) for h in hero_tags if h.get_text(strip=True)]
        if taglines:
            result["tagline"] = " | ".join(taglines[:2])

        og_image = soup.find("meta", property="og:image")
        if og_image:
            result["logo_url"] = og_image.get("content", "")
        else:
            for img in soup.find_all("img"):
                src = img.get("src", "")
                alt = img.get("alt", "").lower()
                if "logo" in src.lower() or "logo" in alt:
                    result["logo_url"] = urljoin(url, src)
                    break

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        result["raw_text"] = " ".join(text.split())[:3000]

    except Exception as e:
        result["error"] = str(e)

    return result

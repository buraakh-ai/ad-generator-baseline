"""Composes tools/web_scraper_tool + tools/logo_tool + the LLM router into
one capability: turn a company name (and optionally a URL) into a
structured brand profile. Used by agents/research_agent.py."""
import json

from core.agno_models import build_agno_agent
from core.model_router import generate_text
from core.prompt_loader import render
from tools.logo_tool import find_company_logo
from tools.web_scraper_tool import scrape_website_text


def _strip_json_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _call(user_prompt: str, system_prompt: str = "") -> str:
    try:
        agent = build_agno_agent(complexity="high", instructions=system_prompt)
        result = agent.run(user_prompt)
        return getattr(result, "content", None) or str(result)
    except Exception as e:
        print(f"[research] Agno path unavailable ({e}) — using model_router fallback")
        return generate_text(user_prompt, system_prompt, complexity="high")


def find_website(company_name: str):
    user_prompt = f"What is the official website URL of {company_name}? Reply with ONLY the URL, nothing else."
    try:
        url = _call(user_prompt).strip().strip('"').strip("'")
        if url.startswith("http"):
            return url
    except Exception as e:
        print(f"[research] website lookup failed: {e}")
    return None


def analyze_company(company_name: str, website_content: str = "", website_url: str = "") -> dict:
    logo_url = find_company_logo(company_name, website_url)
    system_prompt, user_prompt = render(
        "company_analysis",
        company_name=company_name,
        website_url=website_url,
        website_content=website_content[:3000] if website_content else "Not available",
        logo_url=logo_url,
    )
    try:
        raw = _strip_json_fence(_call(user_prompt, system_prompt))
        return json.loads(raw)
    except Exception as e:
        print(f"[research] analysis failed: {e}")
        return {
            "what_they_do": f"{company_name} provides products and services",
            "services": "General services",
            "target_audience": "General audience",
            "brand_tone": "professional",
            "key_values": "Quality, Service, Excellence",
            "tagline": f"{company_name} — built for what's next.",
            "logo_url": logo_url,
        }


def research_company(company_name: str, company_url: str = None) -> dict:
    """Returns {"company_data": {...}, "website_url": str}."""
    website_content = ""
    website_url = company_url or ""

    if company_url:
        website_content = scrape_website_text(company_url)
    else:
        print(f"[research] no URL provided — finding website for {company_name}...")
        found = find_website(company_name)
        if found:
            print(f"[research] found website: {found}")
            website_url = found
            website_content = scrape_website_text(found)
        else:
            print("[research] could not find website — falling back to logo search only")

    company_data = analyze_company(company_name, website_content, website_url)
    return {"company_data": company_data, "website_url": website_url}

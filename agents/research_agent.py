"""Research agent — turns a company name (+ optional URL) into a
structured brand profile. Runs first in the sequential campaign
orchestration (agents/orchestrator.py). The actual Agno Agent + tool use
(scraping, logo lookup) lives in skills/company_research_skill.py, which
this file exposes as this agent's public entry point."""
from skills.company_research_skill import research_company


def run(company_name: str, company_url: str = None) -> dict:
    """Returns {"company_data": {...brand profile...}, "website_url": str}."""
    return research_company(company_name, company_url)

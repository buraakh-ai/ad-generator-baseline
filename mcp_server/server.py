"""MCP server exposing the ad-generator's core capabilities as MCP tools.

NOT PART OF THE CURRENTLY DEPLOYED SOLUTION. This is scaffolding for a
future release — it isn't started by docker-compose.yml, isn't copied into
Dockerfile.backend's image, and its one dependency (the `mcp` package) is
deliberately kept out of backend/requirements.txt so installing the current
solution doesn't pull it in. Do not wire this into backend/main.py or
docker-compose.yml until that future release is actually being built.

When that time comes: it calls straight into agents/orchestrator.py,
agents/image_agent.py, and the platform agents' post() functions — the same
functions the FastAPI backend uses, so there's no duplicated business logic
between the HTTP API and the MCP surface.

To try it now anyway:
    pip install -r backend/requirements.txt -r mcp_server/requirements.txt
    python -m mcp_server.server
(stdio transport — add this as an MCP server in any MCP-compatible client)
"""
import os

from mcp.server.mcpserver import MCPServer

from agents import facebook_agent, image_agent, instagram_agent, linkedin_agent, orchestrator

mcp = MCPServer("ad-generator")

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATIC_DIR = os.path.join(_ROOT_DIR, "static")


@mcp.tool()
def generate_ads(company_name: str, product_description: str = "", ad_idea: str = "",
                  event_context: str = None, company_url: str = None) -> dict:
    """Research a company, pick an India/US festival-aware or trending
    event, and write platform ad copy (TikTok, Instagram, X, Facebook,
    LinkedIn) tied to it."""
    return orchestrator.run_campaign(
        company_name=company_name, product_description=product_description,
        ad_idea=ad_idea, event_context=event_context, company_url=company_url,
    )


@mcp.tool()
def generate_image(company_name: str, instagram_copy: str, image_headline: str,
                    event_context: str, company_details: dict, logo_url: str = None,
                    custom_prompt: str = None) -> dict:
    """Generate the ad's background image and composite the final
    display/clean versions. Returns local file paths under static/."""
    display_path, clean_path = image_agent.generate_ad_image(
        company_name, instagram_copy, image_headline, event_context,
        company_details, logo_url, custom_prompt=custom_prompt, static_dir=_STATIC_DIR,
    )
    return {"display_path": display_path, "clean_path": clean_path}


@mcp.tool()
def post_to_instagram(image_local_path: str, caption: str) -> str:
    """Post an already-generated ad image to the connected Instagram account."""
    return instagram_agent.post(image_local_path, caption)


@mcp.tool()
def post_to_facebook(image_local_path: str, caption: str) -> str:
    """Post an already-generated ad image to the connected Facebook Page."""
    return facebook_agent.post(image_local_path, caption)


@mcp.tool()
def post_to_linkedin(image_local_path: str, caption: str) -> str:
    """Post an already-generated ad image to the connected LinkedIn profile."""
    return linkedin_agent.post(image_local_path, caption)


if __name__ == "__main__":
    mcp.run()

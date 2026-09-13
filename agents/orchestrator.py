"""Runs the ad-campaign agents in a fixed sequence:

  research_agent -> event_agent -> creative brief -> per-platform copy
  agents (tiktok, instagram, twitter, facebook, linkedin) -> quality review

This is the "orchestration is sequential" piece of the brief — each step's
output feeds the next, run in plain Python order rather than a free-form
agentic loop, so a campaign run is deterministic and repeatable. Image
generation and social posting are deliberately NOT part of this sequence —
they're separate, explicit actions triggered from the backend after the
user has reviewed the generated copy (see agents/image_agent.py and the
platform agents' post() functions), matching the original app's UX.
"""
import json

from agents import event_agent, facebook_agent, instagram_agent, linkedin_agent, research_agent, tiktok_agent, twitter_agent
from agents._common import strip_json_fence
from core.model_router import generate_text
from core.prompt_loader import render


def _creative_brief(company_name, company_data, event_context, ad_idea):
    _, user_prompt = render(
        "creative_brief",
        company_name=company_name,
        what_they_do=company_data.get("what_they_do", ""),
        brand_tone=company_data.get("brand_tone", "professional"),
        event_context=event_context,
        ad_idea=ad_idea,
    )
    try:
        raw = generate_text(user_prompt, "", complexity="low")
        return json.loads(strip_json_fence(raw)).get("image_headline", "")
    except Exception as e:
        print(f"[orchestrator] creative brief failed: {e}")
        return f"{company_name} — built for what's next."


def _quality_review(company_name, company_data, ads):
    _, user_prompt = render(
        "quality_review",
        company_name=company_name,
        brand_tone=company_data.get("brand_tone", "professional"),
        tiktok=ads.get("tiktok", ""), instagram=ads.get("instagram", ""),
        twitter=ads.get("twitter", ""), facebook=ads.get("facebook", ""),
        linkedin=ads.get("linkedin", ""),
    )
    try:
        raw = generate_text(user_prompt, "", complexity="low")
        data = json.loads(strip_json_fence(raw))
        return data.get("quality_score", 0), data.get("quality_reason", "")
    except Exception as e:
        print(f"[orchestrator] quality review failed: {e}")
        return 0, "Could not compute a quality score."


def run_campaign(company_name: str, product_description: str = "", ad_idea: str = "",
                  event_context: str = None, company_url: str = None,
                  company_data: dict = None, website_url: str = None) -> dict:
    """If company_data is already known (cached from a previous run for
    this company), pass it in to skip the research step — used by the
    backend's /retry-event flow."""
    if company_data is None:
        research = research_agent.run(company_name, company_url)
        company_data = research["company_data"]
        website_url = research["website_url"]

    detected_event = event_agent.run(company_name, company_data, event_override=event_context)

    image_headline = _creative_brief(company_name, company_data, detected_event, ad_idea)

    brief = dict(
        company_name=company_name,
        what_they_do=company_data.get("what_they_do", ""),
        services=company_data.get("services", ""),
        target_audience=company_data.get("target_audience", ""),
        brand_tone=company_data.get("brand_tone", "professional"),
        key_values=company_data.get("key_values", ""),
        tagline=company_data.get("tagline", ""),
        product_description=product_description,
        ad_idea=ad_idea,
        event_context=detected_event,
    )

    ads = {
        "tiktok": tiktok_agent.write_copy(**brief),
        "instagram": instagram_agent.write_copy(**brief),
        "twitter": twitter_agent.write_copy(**brief),
        "facebook": facebook_agent.write_copy(**brief),
        "linkedin": linkedin_agent.write_copy(**brief),
        "image_headline": image_headline,
    }

    quality_score, quality_reason = _quality_review(company_name, company_data, ads)
    ads["quality_score"] = quality_score
    ads["quality_reason"] = quality_reason

    return {
        "ads": ads,
        "company_name": company_name,
        "detected_event": detected_event,
        "company_data": company_data,
        "website_url": website_url,
    }

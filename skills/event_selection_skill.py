"""Event selection: checks India/US festivals and national holidays first
(tools/festival_tool) — a hit there always takes precedence over ordinary
trending news, per the brief. Only falls back to RSS headlines + AI ranking
(tools/rss_tool) when no festival/holiday applies to today or tomorrow.
Used by agents/event_agent.py."""
from core.agno_models import build_agno_agent
from core.model_router import generate_text
from core.prompt_loader import render
from tools.festival_tool import get_upcoming_festival
from tools.rss_tool import get_all_headlines

# Returned when no festival/holiday/headline gave us anything concrete to
# tie the campaign to. Exported so callers (e.g.
# skills/image_compositing_skill.py's AI scene generator) can recognize
# this exact "no real event" case and not try to visualize it literally.
GENERIC_EVENT_FALLBACK = "current global events and cultural moments"


def _call(user_prompt: str, system_prompt: str = "") -> str:
    try:
        agent = build_agno_agent(complexity="high", instructions=system_prompt)
        result = agent.run(user_prompt)
        return getattr(result, "content", None) or str(result)
    except Exception as e:
        print(f"[event] Agno path unavailable ({e}) — using model_router fallback")
        return generate_text(user_prompt, system_prompt, complexity="high")


def _festival_event_context(festival: dict) -> str:
    when = "today" if festival["when"] == "today" else "tomorrow"
    return (
        f"[FESTIVAL] {festival['name']} is being celebrated {when} in {festival['country']} "
        f"— a major cultural moment worth tying the campaign to."
    )


def pick_best_event(company_name: str, company_data: dict) -> str:
    festival = get_upcoming_festival()
    if festival:
        print(f"[event] festival match: {festival['name']} ({festival['when']}, {festival['country']})")
        return _festival_event_context(festival)

    headlines = get_all_headlines()
    if not headlines:
        print("[event] no headlines fetched — using generic fallback")
        return GENERIC_EVENT_FALLBACK

    headlines_block = "\n".join(f"[{h['category'].upper()}] {h['title']}" for h in headlines)
    system_prompt, user_prompt = render(
        "event_selection",
        company_name=company_name,
        what_they_do=company_data.get("what_they_do", ""),
        services=company_data.get("services", ""),
        brand_tone=company_data.get("brand_tone", ""),
        target_audience=company_data.get("target_audience", ""),
        key_values=company_data.get("key_values", ""),
        tagline=company_data.get("tagline", ""),
        headlines_block=headlines_block,
    )
    result = _call(user_prompt, system_prompt).strip()

    if result.startswith("[RELEVANT]"):
        print("[event] context-matched event found")
        return result.replace("[RELEVANT]", "").strip()
    elif result.startswith("[TRENDING]"):
        print("[event] no relevant match — using trending fallback")
        return result.replace("[TRENDING]", "").strip()
    return result

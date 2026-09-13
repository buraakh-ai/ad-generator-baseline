"""Event agent — picks the event context the campaign ties itself to.
Checks India/US festivals and national holidays first (always takes
precedence), falling back to AI-ranked trending news only when neither
today nor tomorrow is a tracked cultural moment. Runs second in the
sequential orchestration, after the research agent. The actual Agno Agent
+ tool use lives in skills/event_selection_skill.py."""
from skills.event_selection_skill import pick_best_event


def run(company_name: str, company_data: dict, event_override: str = None) -> str:
    """If event_override is provided (user typed their own event), it's
    used as-is — skipping festival/trending detection entirely."""
    if event_override:
        return event_override
    return pick_best_event(company_name, company_data)

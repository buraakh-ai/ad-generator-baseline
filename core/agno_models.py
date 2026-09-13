"""Bridges our OpenAI provider (two text tiers — see core/model_router.py)
to Agno's own Model class so each agents/*.py file runs as a real
`agno.agent.Agent`. If `agno` isn't installed, or the installed version's
Model class signature has drifted, building here raises — every agent
function catches that and falls back to core.model_router.generate_text(),
which calls OpenAI directly over HTTP instead of through Agno. That keeps
the app functional even if the Agno API differs from what's written below,
or if Agno's OpenAIChat wrapper doesn't yet know a newer model needs
`max_completion_tokens` instead of `max_tokens`."""
from core.config import settings


def _agno_model_for(complexity: str):
    if not settings.openai_api_key:
        raise Exception("No OPENAI_API_KEY configured")

    from agno.models.openai import OpenAIChat
    model_id = settings.openai_high_end_text_model if complexity == "high" else settings.openai_text_model
    return OpenAIChat(id=model_id, api_key=settings.openai_api_key)


def build_agno_agent(complexity: str, instructions: str = "", tools=None, markdown: bool = False):
    """Raises on any failure — callers must catch and fall back to the
    model_router."""
    from agno.agent import Agent

    model = _agno_model_for(complexity)
    return Agent(model=model, instructions=instructions, tools=tools or [], markdown=markdown)

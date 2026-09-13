"""Bridges our single OpenAI provider to Agno's own Model class so each
agents/*.py file runs as a real `agno.agent.Agent`. If `agno` isn't
installed, or the installed version's Model class signature has drifted,
building here raises — every agent function catches that and falls back to
core.model_router.generate_text(), which calls OpenAI directly over HTTP
instead of through Agno. That keeps the app functional even if the Agno API
differs from what's written below."""
from core.config import settings


def _agno_model_for(complexity: str):
    if not settings.openai_api_key:
        raise Exception("No OPENAI_API_KEY configured")

    from agno.models.openai import OpenAIChat
    return OpenAIChat(id=settings.openai_text_model, api_key=settings.openai_api_key)


def build_agno_agent(complexity: str, instructions: str = "", tools=None, markdown: bool = False):
    """Raises on any failure — callers must catch and fall back to the
    model_router."""
    from agno.agent import Agent

    model = _agno_model_for(complexity)
    return Agent(model=model, instructions=instructions, tools=tools or [], markdown=markdown)

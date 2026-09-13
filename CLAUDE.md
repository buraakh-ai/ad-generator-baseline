# CLAUDE.md

Repo map and conventions for future Claude Code sessions working on this project.

## What this is

A multi-agent ad-generation app: given a company (name and/or URL), it researches the brand, picks an event to tie the campaign to (India/US festival or national holiday first, trending news otherwise), writes platform ad copy, generates a background image, and can post to Instagram/Facebook/LinkedIn. FastAPI backend + Streamlit frontend, deployed separately. That's the whole current solution — see the MCP section below before touching `mcp_server/`.

## Layering — respect this when adding code

```
core/    <- tools/  <- skills/  <- agents/  <- backend/ | frontend/
```

- **`core/`**: `config.py` (all env vars — add new ones here, never `os.getenv` scattered elsewhere; also owns `refresh_from_aws_secrets()`, the AWS Secrets Manager overlay for static app secrets, called once at backend startup), `prompt_loader.py` (yaml -> filled string), `model_router.py` (OpenAI-only text generation), `agno_models.py` (bridges to a real `agno.agent.Agent`, also OpenAI-only), `image_models.py` (image provider config, from `image_config.json`).
- **`tools/`**: one atomic capability per file — a single API call or a tight cluster of them (scraping, RSS, festival lookup, S3, AWS secrets, one social platform's posting API, image-provider calls). No LLM calls here.
- **`skills/`**: composed capability built from tools + the LLM router — "research a company" (scrape + AI-analyze), "pick an event" (festival check + trending fallback), "composite an ad image" (prompt build + PIL compositing). These are where an Agno Agent actually gets constructed and `.run()` (via `core/agno_models.build_agno_agent`, falling back to `core/model_router.generate_text` on any failure).
- **`agents/`**: the public, per-agent entry points `agents/orchestrator.py` calls in sequence. `research_agent.py` / `event_agent.py` are thin wrappers over their skill. The five platform agents (`tiktok_agent.py`, `instagram_agent.py`, `twitter_agent.py`, `facebook_agent.py`, `linkedin_agent.py`) each call the shared `agents/_common.generate_platform_copy()` helper with their own `prompts/ad_copy_<platform>.yaml`; three of them (`instagram_agent.py`, `facebook_agent.py`, `linkedin_agent.py`) also expose `post()`. `image_agent.py` wraps the image skill + provider tools.
- **`prompts/`**: every LLM prompt as `{system, user}` yaml, loaded via `core/prompt_loader.render(name, **kwargs)` (str.format-style `{placeholders}`, missing keys render as empty string rather than raising). `prompts/image_prompt.yaml` is the one exception — it's a `{core}` key consumed directly by `skills/image_compositing_skill.py`, not through `render()`.

## Adding a new platform agent

1. Add `prompts/ad_copy_<platform>.yaml` with `system`/`user` keys (copy an existing one, adjust the caption spec).
2. Add `agents/<platform>_agent.py` with a `write_copy(**brief) -> str` that calls `agents._common.generate_platform_copy("ad_copy_<platform>", complexity="high", **brief)`. Add a `post()` too if there's a posting API — put the actual API call in a new `tools/<platform>_tool.py` first.
3. Wire it into `agents/orchestrator.py`'s `ads = {...}` dict and the `platforms` list in `frontend/streamlit_app.py`.

## Adding/editing a prompt

Just edit the relevant `prompts/*.yaml` — no code change needed unless you're adding a new `{placeholder}`, in which case update the `render(...)` call site to pass it.

## LLM router — OpenAI only

`core/model_router.generate_text(prompt, system_prompt, complexity="low"|"high")` calls a single OpenAI model (`settings.openai_text_model`, `gpt-4o-mini` by default) regardless of `complexity` — that argument is kept only for call-site compatibility (every skill/agent already passes it) in case per-tier models come back later. Images go through `core/image_models.py` + `tools/image_provider_tools.py`, also OpenAI-only (`gpt-image-1`, falling back to `dall-e-3`). See `core/model_router.py`'s module docstring and `README.md`'s "LLM router"/"Image models"/"Secrets" sections for the full picture, including how `OPENAI_API_KEY` and the Facebook/LinkedIn app secrets get overlaid from AWS Secrets Manager in a deployed environment via `core.config.Settings.refresh_from_aws_secrets()`.

## Festival precedence

`skills/event_selection_skill.pick_best_event()` always calls `tools/festival_tool.get_upcoming_festival()` first. Only when that returns `None` (no tracked India/US festival or holiday today or tomorrow) does it fall through to RSS headlines + AI ranking. If you're debugging "why didn't it use the trending story I expected", check this precedence first — it's working as designed if there's a festival match.

## MCP server — future release, not wired in

`mcp_server/` is scaffolding for a later release. It is deliberately **not** part of the current solution: not started by `docker-compose.yml`, not copied into `Dockerfile.backend`, not imported by `backend/main.py`, and its `mcp` dependency lives in its own `mcp_server/requirements.txt` rather than `backend/requirements.txt` so a normal setup never installs it. Don't wire it into the backend/compose/CI on your own judgment — that's a decision for whoever ships that future release. If you're asked to work on it, read `mcp_server/server.py`'s module docstring first.

## Known soft spots

- `prompts/festivals_static.yaml` has hand-entered lunar-calendar festival dates (Diwali, Dussehra, Eid) for 2026-2027 only — extend it (or verify the `holidays` package's categorized-India support has improved) before those years pass.
- No automated tests exist yet. If you add one, put backend tests under `backend/tests/`, everything else mirrors the module it covers (e.g. `tools/tests/test_festival_tool.py`).
- `agents/orchestrator.py` and the platform copy agents haven't been exercised against real LLM calls yet (only import/boot-tested) — first real `/generate` run is worth watching closely for prompt/parsing issues.

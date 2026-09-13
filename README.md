# Ad Generator

Researches a company, ties an ad campaign to whatever's culturally relevant right now (an India/US festival or national holiday takes precedence; trending news otherwise), writes platform-specific ad copy, generates a background image, and can post the result straight to Instagram, Facebook, or LinkedIn.

## Architecture

```
agents/     one Agno Agent-backed module per agent, run in a fixed sequence by agents/orchestrator.py:
            research -> event -> creative brief -> per-platform copy (tiktok/instagram/twitter/facebook/linkedin) -> quality review
            image generation (image_agent.py) and social posting (each platform agent's post()) are separate,
            explicit actions triggered after the user reviews the generated copy — not part of the automatic sequence.
tools/      atomic, single-purpose functions: scraping, RSS headlines, festival/holiday lookup, image-provider calls,
            S3 upload, AWS Secrets Manager, and the Instagram/Facebook/LinkedIn posting APIs.
skills/     composed capabilities built from tools + the LLM router: company research, event selection, image compositing.
prompts/    every LLM prompt as an editable YAML file (core/prompt_loader.py loads + fills them in) — edit copy/tone
            without touching Python.
core/       settings (env-var driven), the prompt loader, the complexity-tiered LLM router, the Agno-agent bridge,
            and image-provider config.
backend/    FastAPI app — same endpoints as the original Flask app. This + frontend/ is the actual deployed solution.
frontend/   Streamlit CRM-style shell (streamlit_app.py) — a left sidebar module menu (st.navigation), each module
            its own page under app_pages/ talking to its own backend over HTTP. Today: app_pages/ad_generator.py
            (this backend). See "Frontend: multi-module shell" below for the pattern and how to add a module.
scripts/    one-off ops scripts (LinkedIn OAuth re-auth).
mcp_server/ FUTURE RELEASE ONLY — not part of the current solution (see below). Would expose generate_ads /
            generate_image / post_to_* as MCP tools, calling the same agents the backend uses.
```

## LLM router (`core/model_router.py`)

OpenAI-only, two tiers again. `generate_text(prompt, system_prompt, complexity="low"|"high")`:

- **`"low"`** → `OPENAI_TEXT_MODEL` (`gpt-4o-mini` by default) — short, low-risk generations: the creative-brief headline, the quality-review score.
- **`"high"`** → `OPENAI_HIGH_END_TEXT_MODEL` (`gpt-5.5` by default) — brand-sensitive/creative work: ad copy, company research, event selection, and the image poster-prompt writer (`skills/image_compositing_skill.py`).

Newer OpenAI models (GPT-5.x and later) reject the legacy `max_tokens` chat-completions parameter and require `max_completion_tokens` instead — `gpt-4o-mini` accepts either, so `core/model_router.py` just uses `max_completion_tokens` uniformly rather than branching per model.

Every call retries up to `MAX_LLM_ATTEMPTS` times (set in `.env`) before raising `AllProvidersExhaustedError`. Each `agents/*.py` file tries to run its step as a genuine `agno.agent.Agent` first (see `core/agno_models.py`, also OpenAI-only, same two-tier model selection), falling back to the router calling OpenAI directly over HTTP if Agno isn't installed, its API doesn't match your installed version, or its `OpenAIChat` wrapper doesn't yet send `max_completion_tokens` for a newer model — the app keeps working either way.

(Gemini/Groq/Together/HuggingFace text providers and their `.env` keys have been removed — this app is OpenAI-only for text and images now.)

> There's no OpenAI text model literally named "GPT 5.2" anymore either — it existed briefly but is now deprecated/superseded (as of writing, the current lineup is gpt-5.4 / gpt-5.4-pro / gpt-5.4-mini / gpt-5.5 / gpt-5.5-pro). `OPENAI_HIGH_END_TEXT_MODEL` is a plain `.env` value — bump it whenever a newer model ships, no code change needed.

## Image models

The image model now draws the **entire finished poster** — headline, supporting copy, benefit bullets, CTA button, icons, layout — directly, rather than a plain background photo that gets a simple text overlay afterward. `skills/image_compositing_skill.py`'s `_build_ai_poster_prompt()` asks the high-tier text model to write that detailed poster brief (`prompts/image_poster_prompt.yaml`), and the image model renders it in one shot.

Provider list/order lives in `image_config.json` (still hand-editable), a 3-tier fallback chain, best quality first:

1. `openai_image` → **`gpt-image-2.5-sunburst`** — OpenAI's current best/most capable image model, draws the poster's own text directly.
2. `openai_image_fallback` → **`gpt-image-1`** — still strong, still draws text directly; only fixed preset image sizes though (no custom aspect ratio), so its output takes a bit more edge-crop than the primary tier.
3. `openai_dalle3` → **`dall-e-3`** — last resort only. It predates native text rendering and reliably garbles poster text/logos; this tier exists so the app still produces *an* image if both gpt-image tiers are down, not because it can replicate the poster style.

All three read `OPENAI_API_KEY` from `.env`; model ids come from `OPENAI_IMAGE_MODEL` / `OPENAI_FALLBACK_IMAGE_MODEL` / `OPENAI_LAST_RESORT_IMAGE_MODEL`.

Since the poster's own headline/CTA/bullets now run right up to the model's own canvas edges, requesting an aspect ratio that doesn't match the app's compositing target (`1080x1350`, 4:5) would crop real content off — `tools/image_provider_tools.py` requests `1024x1280` (exactly 4:5) for the two gpt-image tiers, which support custom sizes; gpt-image-1 and dall-e-3 are restricted to a handful of fixed presets so they don't get an exact match.

> There's no OpenAI image model named "GPT 5.2" — that name belongs to a text/reasoning model line, not an image model. `gpt-image-2.5-sunburst` is the correct current OpenAI image model for best quality; if a newer one ships later, just change `OPENAI_IMAGE_MODEL` in `.env` — no code change needed.

### Brand assets (real logo + CEO/team photo + contact URL)

`BRAND_LOGO_URL` / `BRAND_CEO_PHOTO_URL` / `BRAND_CEO_NAME` / `BRAND_CEO_TITLE` / `BRAND_CONTACT_URL` in `.env` are this deployment's own real assets — same single-business scope as the Facebook/Instagram/LinkedIn credentials, not per-campaign. Public URLs only (e.g. a public-read S3 object, same convention `tools/s3_tool.py` already uses for generated images: `https://<bucket>.s3.<region>.amazonaws.com/<key>`).

When set, `BRAND_LOGO_URL` overrides whatever logo the research step guessed from Clearbit, and a CEO headshot card (real photo + name/title) gets composited into every generated image — both via plain PIL compositing (`skills/image_compositing_skill.py`), never AI-drawn, so it's always the actual real photo, not a fabricated likeness. The AI poster-prompt writer is told to leave the top-right/top-left corners clear rather than drawing its own logo/wordmark there — but only when the configured URL actually resolves at generation time, not just when it's configured, so a broken image URL doesn't leave the poster with an empty reserved corner.

**A generated image can't actually be clickable** — there's no such thing as a link embedded in a JPEG/PNG posted to social media. So rather than draw a "Book Now"-style button that looks tappable but does nothing, `BRAND_CONTACT_URL` (when set) tells the poster writer to print that exact URL as small plain text near the bottom instead. Leave it blank to keep the old behavior (a drawn CTA button label, no real URL).

Leave all of these blank to keep the original behavior (Clearbit-researched logo, no CEO card, drawn CTA button with no real URL).

> Clearbit's free logo API (`logo.clearbit.com`) may no longer be reachable at all — HubSpot acquired Clearbit and has been sunsetting free endpoints. If `tools/logo_tool.py`'s auto-lookup stops finding logos, `BRAND_LOGO_URL` is the fix, not a bug in this app.

## Festival/holiday-aware event selection

`tools/festival_tool.py` checks whether *today or tomorrow* is a major India or US festival/national holiday (Diwali, Dussehra, Holi, Eid al-Fitr, Eid al-Adha, Republic Day, Independence Day; Thanksgiving, Christmas, July 4th, Labor Day, Presidents Day, ...) using the `holidays` package, with `prompts/festivals_static.yaml` as a fallback table. A match always wins over trending sports/finance/policy news — see `skills/event_selection_skill.py`.

**Caveat:** Eid al-Fitr and Eid al-Adha follow the lunar Hijri calendar, so their Gregorian dates shift every year. Both the `holidays` package and `festivals_static.yaml` need periodic review to stay accurate — don't trust either blindly more than a couple of years out.

## Setup

Using [uv](https://docs.astral.sh/uv/) (recommended — this is how the project was actually built and smoke-tested):

```bash
uv python install 3.12
uv venv --python 3.12
cp .env.example .env   # fill in your keys — see .env.example for what each one does
uv pip install -r backend/requirements.txt -r frontend/requirements.txt

# backend
.venv/Scripts/python.exe -m uvicorn backend.main:app --reload   # .venv/bin/python on macOS/Linux

# frontend (separate terminal/host)
.venv/Scripts/python.exe -m streamlit run frontend/streamlit_app.py
```

Or with plain `pip`, once you have Python 3.12 on PATH: swap `uv pip install` for `pip install` and drop the `uv python install`/`uv venv` steps.

The MCP server (`mcp_server/`) is **not** part of this setup — see "MCP server" below.

**Windows + Smart App Control:** if `.venv\Scripts\python.exe` (or bare `python.exe`) fails with *"An Application Control policy has blocked this file"*, that's Windows 11's Smart App Control blocking the small venv launcher stub (or a Microsoft Store `python.exe` alias) — not a bug here. It can retroactively flag previously-working unsigned executables. Use `.\run.ps1` instead of `.venv\Scripts\python.exe` for every command below (`.\run.ps1 -m uvicorn ...`, `.\run.ps1 -m streamlit run ...`) — it calls the actual Python interpreter underneath directly, which isn't blocked. See `run.ps1`'s header comment for details.

## Docker

```bash
docker compose up --build
```

Backend on `:8000`, frontend on `:8501`. Both read `.env`; the frontend is pointed at the backend container via `BACKEND_BASE_URL=http://backend:8000` in `docker-compose.yml`.

## Deploying to AWS (two independent containers)

Backend and frontend deploy as two separate [AWS App Runner](https://aws.amazon.com/apprunner/) services — each gets its own public HTTPS endpoint, no VPC/ALB/subnet setup required. The frontend is reachable from your browser at its own URL; the backend is independently callable as a plain HTTP API at its own URL (e.g. `curl https://<backend-url>/`), which is also what the frontend calls under the hood via `BACKEND_BASE_URL`.

Prerequisites: Docker running locally, and an authenticated AWS session (`aws sts get-caller-identity` succeeds — re-run `aws sso login` or set IAM keys first if it doesn't).

```bash
# from repo root, using the backend venv (it already has boto3)
.venv/Scripts/python.exe -m scripts.deploy_apprunner --region us-east-2
```

This builds + pushes both images to ECR, creates the IAM role App Runner needs to pull them, and creates (or updates, on re-run) both App Runner services, printing each one's public URL when done. See `scripts/deploy_apprunner.py`'s module docstring for exactly what it does and in what order.

**Why the backend is pinned to a single instance:** `/generate-image` writes the ad image to local disk, and a later `/post-to-instagram|facebook|linkedin` call reads that same local file before re-uploading it to S3 (`tools/instagram_tool.py` etc.). If the backend ever ran on more than one instance, a later request could land on an instance that never saw that file. The deploy script pins the backend to exactly one App Runner instance to keep that flow correct — outgrowing that means wiring `/generate-image` to upload straight to S3 (`tools/s3_tool.py` already has the upload call, it just isn't in that code path yet) instead of relying on local disk.

Every env var in your `.env` is passed to the backend service as-is; the frontend service only gets `BACKEND_BASE_URL`, pointed at the backend's App Runner URL. CORS is open by default (`CORS_ALLOW_ORIGINS` in `.env`) since this API takes no credentials — tighten it if you don't want that.

## Frontend: multi-module shell

`frontend/streamlit_app.py` is a thin shell: it sets the shared theme (`.streamlit/config.toml`), draws the sidebar brand header, and defines the module list via `st.navigation`/`st.Page` — one entry per module, each pointing at its own file under `frontend/app_pages/`. Today there's one real module (`ad_generator.py`) and one placeholder (`lead_generator.py`, shown so the nav reflects where this is headed — it just says "coming soon").

Each module resolves its **own** backend URL via `frontend/utils/api.py`'s `resolve_backend_url("<MODULE>_BACKEND_URL")` — this project's stated direction is one backend per module, each its own AWS ECS service, so the frontend is built to point different modules at different backend containers rather than assuming a single shared backend. `AD_GENERATOR_BACKEND_URL` falls back to the original `BACKEND_BASE_URL` if unset, so existing `.env` files don't need to change.

**To add a new module** (e.g. once a Lead generator backend exists):
1. Add `<MODULE>_BACKEND_URL` to `.env`/`.env.example`.
2. Replace `frontend/app_pages/lead_generator.py`'s placeholder body with the real module UI, calling `resolve_backend_url("LEAD_GENERATOR_BACKEND_URL")` + `make_api(...)` from `frontend/utils/api.py` (same pattern `ad_generator.py` uses) — or add a new `frontend/app_pages/<module>.py` + a new `st.Page(...)` entry in `streamlit_app.py`'s navigation list for a module beyond those two.
3. No changes needed to the shell itself unless the module needs its own top-level nav section.

## Two run modes

**UI mode** (the Ad generator module, `frontend/app_pages/ad_generator.py`): a human reviews the generated copy and image for each platform, can download any of them (a "Download" button sits under each platform's caption and under the image), and explicitly clicks "Post to Instagram/Facebook/LinkedIn" per platform — nothing posts without that click.

**Batch mode** (`scripts/batch_run.py`): unattended end-to-end runs for one or more companies — research, event selection, copy, image, and posting to Instagram/Facebook/LinkedIn — with no human in the loop. Meant to be triggered by an external scheduler (cron, Task Scheduler, a CI job) rather than run interactively.

```bash
# companies.json: a JSON list of {"company_name", "company_url", "product_description", "ad_idea", "event_context"}
.venv/Scripts/python.exe -m scripts.batch_run --companies companies.json --results-out results.json

# generate copy + image only, skip posting
.venv/Scripts/python.exe -m scripts.batch_run --companies companies.json --no-post
```

It calls the agents directly (no running backend required), logs a per-company/per-platform summary to stdout, and exits non-zero if any company's copy/image generation failed (a single dead social token doesn't fail the whole run — posting failures are logged per-platform instead). Only Instagram, Facebook, and LinkedIn have posting APIs wired up; TikTok/X copy is generated but not auto-posted.

## Secrets

Everything that used to be hardcoded in source (OpenAI key, AWS credentials, Facebook/Instagram/LinkedIn tokens) now lives in `.env`, which is gitignored. **Rotate every one of those credentials before this repo is ever pushed to a remote** — they were in plaintext in source for a period and should be treated as compromised.

Locally, everything is read from `.env`. In a deployed environment, two separate AWS Secrets Manager mechanisms take over automatically — nothing but creating the secrets is required:

- **Rotating social tokens** (already wired up, unchanged by this section): `tools/facebook_tool.py`, `tools/instagram_tool.py`, and `tools/linkedin_tool.py` each check their own secret (`ad-generator/<BUSINESS_ID>/facebook-token`, `.../instagram-token`, `.../linkedin-token`) at startup/refresh time and fall back to the `.env` value if AWS Secrets Manager isn't reachable or the secret doesn't exist yet.
- **Static app secrets** (`core.config.Settings.refresh_from_aws_secrets`, called once at backend startup): overlays `OPENAI_API_KEY`, `FACEBOOK_APP_ID`/`FACEBOOK_APP_SECRET`, and `LINKEDIN_CLIENT_ID`/`LINKEDIN_CLIENT_SECRET` from one JSON secret at `ad-generator/<BUSINESS_ID>/app-secrets`, e.g.:
  ```json
  {"OPENAI_API_KEY": "...", "FACEBOOK_APP_ID": "...", "FACEBOOK_APP_SECRET": "...",
   "LINKEDIN_CLIENT_ID": "...", "LINKEDIN_CLIENT_SECRET": "..."}
  ```
  Same fallback behavior: if that secret doesn't exist (e.g. running locally), whatever `.env` set stands unchanged.

**`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` should *not* go in Secrets Manager** — leave them blank in a deployed environment and grant the backend's IAM instance/task role S3 + Secrets Manager permissions instead; `tools/secrets_tool.aws_client()` only passes explicit keys to boto3 when both are set, so a blank pair falls through to that role automatically. Keep them in `.env` for local dev, where there's no instance role to fall back to.

Not secrets — plain config, fine as regular env vars either way: `AWS_REGION`, `AWS_BUCKET_NAME`, `BUSINESS_ID`, `FACEBOOK_PAGE_ID`, `INSTAGRAM_USER_ID`, `BACKEND_BASE_URL`, `CORS_ALLOW_ORIGINS`, the `OPENAI_*_MODEL` ids, and the `MAX_*` loop bounds below.

## Loop safety

Every retry loop in the project reads its bound from `.env` instead of a hardcoded number: `MAX_LLM_ATTEMPTS`, `MAX_IMAGE_ATTEMPTS`, `MAX_MEDIA_POLL_ATTEMPTS`.

## MCP server — future release only

`mcp_server/` exists in this repo as scaffolding but is **not part of the current solution**: it isn't started by `docker-compose.yml`, isn't copied into `Dockerfile.backend`'s image, and its one dependency (`mcp`) is deliberately kept out of `backend/requirements.txt` so the setup above never installs it. Nothing in `backend/main.py` imports it. Leave it alone until a future release actually wires it in — see `mcp_server/server.py`'s module docstring before changing that.

To try it anyway, in isolation:
```bash
uv pip install -r backend/requirements.txt -r mcp_server/requirements.txt
.venv/Scripts/python.exe -m mcp_server.server
```

## Verified working

Built and smoke-tested with `uv` (Python 3.12, `uv venv` + `uv pip install`): every module byte-compiles and imports cleanly, `core/agno_models.py`'s `agno.models.google.Gemini` / `agno.models.groq.Groq` / `agno.models.openai.OpenAIChat` class names are correct for Agno 3.0.2 (needs the `openai`/`groq` SDKs too — already in `backend/requirements.txt`), and both `uvicorn backend.main:app` and `streamlit run frontend/streamlit_app.py` boot and serve real requests — the backend's startup event even round-tripped real calls to AWS Secrets Manager for the migrated Facebook/LinkedIn tokens. Not yet exercised: a full `/generate` run (real LLM spend) and an actual social-media post.

## Known gaps / next steps

- TikTok and X/Twitter have no posting API integrated (as in the original app) — copy only, for manual posting.
- `prompts/festivals_static.yaml`'s lunar-calendar dates only cover 2026-2027 — extend before those years pass.

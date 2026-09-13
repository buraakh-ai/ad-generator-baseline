"""Batch mode: run the full campaign pipeline — research, event selection,
platform copy, image generation, and posting — for one or more companies
with no human in the loop. Meant to be invoked by an external scheduler
(cron, a CI job, Task Scheduler) rather than a person watching a UI; that's
the "UI mode" flow in frontend/streamlit_app.py instead.

Calls agents/orchestrator.py, agents/image_agent.py, and the platform
agents' post() functions directly (no dependency on backend/main.py being
up), so it can run standalone in a container or scheduled job.

Only instagram_agent, facebook_agent, and linkedin_agent expose post() —
tiktok and twitter copy is generated but not auto-posted (no posting API
wired up for those platforms yet; see CLAUDE.md).

Input is a JSON file: a list of company objects, e.g.:

    [
      {"company_name": "Nike", "company_url": "https://www.nike.com"},
      {"company_name": "Acme Co", "ad_idea": "back to school sale"}
    ]

Each object accepts the same fields as backend.schemas.GenerateRequest
(company_name, company_url, product_description, ad_idea, event_context).

Run with:
    python -m scripts.batch_run --companies companies.json
    python -m scripts.batch_run --companies companies.json --no-post   # generate only, skip posting
    python -m scripts.batch_run --companies companies.json --results-out results.json

Exits non-zero if any company failed campaign generation or image
generation (posting failures are logged per-platform but don't fail the
run, since one dead social token shouldn't block the rest of the batch).
"""
import argparse
import json
import os
import sys
from datetime import datetime

from agents import facebook_agent, image_agent, instagram_agent, linkedin_agent, orchestrator

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATIC_DIR = os.path.join(_ROOT_DIR, "static")

_POSTERS = {
    "instagram": instagram_agent.post,
    "facebook": facebook_agent.post,
    "linkedin": linkedin_agent.post,
}


def _run_one(company: dict, do_post: bool) -> dict:
    company_name = company.get("company_name", "")
    result = {"company_name": company_name, "success": False}

    try:
        campaign = orchestrator.run_campaign(
            company_name=company_name,
            product_description=company.get("product_description", ""),
            ad_idea=company.get("ad_idea", ""),
            event_context=company.get("event_context"),
            company_url=company.get("company_url"),
        )
    except Exception as e:
        result["error"] = f"campaign generation failed: {e}"
        return result

    ads = campaign["ads"]
    company_data = campaign["company_data"]
    result["detected_event"] = campaign["detected_event"]
    result["ads"] = ads

    try:
        display_path, clean_path = image_agent.generate_ad_image(
            campaign["company_name"], ads.get("instagram", ""), ads.get("image_headline", ""),
            campaign["detected_event"], company_data, company_data.get("logo_url"),
            static_dir=_STATIC_DIR,
        )
    except Exception as e:
        result["error"] = f"image generation failed: {e}"
        return result

    result["image_path"] = clean_path
    result["success"] = True

    posts = {}
    if do_post:
        for platform, poster in _POSTERS.items():
            try:
                post_id = poster(clean_path, ads.get(platform, ""))
                posts[platform] = {"success": True, "post_id": post_id}
            except Exception as e:
                posts[platform] = {"success": False, "error": str(e)}
    result["posts"] = posts

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--companies", required=True, help="Path to a JSON file listing companies to run.")
    parser.add_argument("--no-post", action="store_true", help="Generate copy + image only; skip posting to social platforms.")
    parser.add_argument("--results-out", default=None, help="Path to write a JSON results summary (default: printed to stdout only).")
    args = parser.parse_args()

    with open(args.companies, "r", encoding="utf-8") as f:
        companies = json.load(f)

    os.makedirs(_STATIC_DIR, exist_ok=True)

    results = []
    for company in companies:
        name = company.get("company_name", "<unnamed>")
        print(f"[batch] running campaign for {name}...")
        result = _run_one(company, do_post=not args.no_post)
        results.append(result)

        if not result["success"]:
            print(f"[batch] {name}: FAILED — {result.get('error')}")
            continue

        print(f"[batch] {name}: generated OK (event: {result.get('detected_event')})")
        for platform, outcome in result.get("posts", {}).items():
            status = "posted" if outcome["success"] else f"FAILED ({outcome.get('error')})"
            print(f"[batch]   {platform}: {status}")

    summary = {
        "run_at": datetime.now().isoformat(),
        "total": len(results),
        "succeeded": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
    }

    if args.results_out:
        with open(args.results_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"[batch] results written to {args.results_out}")

    print(f"[batch] done: {summary['succeeded']}/{summary['total']} succeeded")

    any_generation_failed = any(not r["success"] for r in results)
    sys.exit(1 if any_generation_failed else 0)


if __name__ == "__main__":
    main()

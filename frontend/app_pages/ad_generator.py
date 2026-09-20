"""Ad generator module — calls its own backend over HTTP (AD_GENERATOR_BACKEND_URL,
falling back to BACKEND_BASE_URL). Recreates the original app's flow: fill in
a company -> generate platform ad copy tied to a trending/cultural event ->
generate an image -> post to Instagram/Facebook/LinkedIn.

Colors/fonts/radii come from the shared theme (.streamlit/config.toml, see
frontend/streamlit_app.py) — the CSS below only covers structural layout
config.toml can't express (platform-row layout, section headings)."""
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st

from utils.api import env_flag, make_api, resolve_backend_url
from utils.theme import PALETTE, score_color

BACKEND_BASE_URL = resolve_backend_url("AD_GENERATOR_BACKEND_URL")
_api = make_api(BACKEND_BASE_URL)
# Prefilled values for the Generate form — this deployment's own business, so
# the common case is "just hit Generate". Kept in .env rather than hardcoded
# here so the module stays reusable for another business; blank = empty field.
DEFAULT_COMPANY_URL = os.getenv("DEFAULT_COMPANY_URL", "")
DEFAULT_COMPANY_NAME = os.getenv("DEFAULT_COMPANY_NAME", "")
DEFAULT_CONTACT_URL = os.getenv("DEFAULT_CONTACT_URL", "")
# Off by default — this creates real ad campaigns (drafts only, but still
# talks to live Marketing APIs). Set ENABLE_PAID_PROMOTION=true in .env to
# show the panel.
SHOW_PAID_PROMOTION = env_flag("ENABLE_PAID_PROMOTION", False)

PLATFORMS = [
    {"key": "tiktok", "label": "TikTok / Reels", "color": "#FE2C55"},
    {"key": "instagram", "label": "Instagram", "color": "#C13584"},
    {"key": "twitter", "label": "X / Twitter", "color": "#0f172a"},
    {"key": "facebook", "label": "Facebook", "color": "#1877f2"},
    {"key": "linkedin", "label": "LinkedIn", "color": "#0a66c2"},
]

# Matches tools/linkedin_ads_tool.py's COUNTRY_GEO_URNS — the frontend
# can't import a backend-side tool module directly (they're deployed
# separately), so this small list is kept in sync manually.
AD_COUNTRIES = [("US", "United States"), ("GB", "United Kingdom"), ("CA", "Canada"),
                ("IN", "India"), ("AU", "Australia")]

DETAIL_FIELDS = [
    ("What they do", "what_they_do"), ("Services", "services"),
    ("Target audience", "target_audience"), ("Brand tone", "brand_tone"),
    ("Key values", "key_values"), ("Tagline", "tagline"),
]

st.html(f"""
<style>
.platform-name {{ display: flex; align-items: center; font-weight: 600; font-size: .9rem; padding-top: .5rem; }}
.platform-dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; flex-shrink: 0; }}
.table-header {{
    display: flex; gap: 1rem; padding: 0 0 .6rem; border-bottom: 2px solid var(--pal-border, #e2e8f0);
    font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
    color: {PALETTE["text_muted"]};
}}
.table-row {{
    display: flex; align-items: flex-start; gap: 1rem; padding: 1rem 0;
    border-bottom: 1px solid var(--pal-border, #e2e8f0);
}}
.section-title {{ font-size: 1.15rem; font-weight: 700; margin: 0 0 1rem; color: {PALETTE["text"]}; }}
.section-subtitle {{ color: {PALETTE["text_muted"]}; font-size: .92rem; margin: -.5rem 0 1.25rem; }}
</style>
""")

if "campaign" not in st.session_state:
    st.session_state.campaign = None
if "image" not in st.session_state:
    st.session_state.image = None
if "provider_failed" not in st.session_state:
    st.session_state.provider_failed = None
if "linkedin_post_urn" not in st.session_state:
    st.session_state.linkedin_post_urn = None
if "facebook_ad_draft" not in st.session_state:
    st.session_state.facebook_ad_draft = None
if "linkedin_ad_draft" not in st.session_state:
    st.session_state.linkedin_ad_draft = None


def _generate_image(campaign, ads, details, fallback_company_name, custom_prompt="", contact_url=""):
    """Calls /generate-image and updates session state — shared by the
    auto-generate-on-first-campaign path below and the manual "Generate /
    regenerate image" button in the Image & publish tab."""
    try:
        data = _api("POST", "/generate-image", json={
            "company_name": campaign.get("detected_company_name", fallback_company_name),
            "instagram_copy": ads.get("instagram", ""),
            "image_headline": ads.get("image_headline", ""),
            "event_context": campaign.get("detected_event", ""),
            "company_details": details,
            "logo_url": details.get("logo_url"),
            "custom_prompt": custom_prompt,
            "contact_url": contact_url,
        })
        if data.get("success"):
            st.session_state.image = data
            st.session_state.provider_failed = None
        elif data.get("provider_failed"):
            st.session_state.provider_failed = data
        else:
            st.session_state.provider_failed = None
            st.error(f"Image error: {data.get('error')}")
    except Exception as e:
        st.error(f"Something went wrong generating the image: {e}")


st.title("Ad generator", anchor=False)
st.caption("Research a company, tie the campaign to a real event, and generate ad copy + images.")

gen_tab, review_tab, publish_tab = st.tabs([
    "1. Generate", "2. Review copy", "3. Image & publish",
])

with gen_tab:
    with st.container(border=True):
        st.markdown('<p class="section-title">Start a new campaign</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="section-subtitle">Paste your website. Get platform-ready ad copy tied to a real world event.</p>',
            unsafe_allow_html=True,
        )
        with st.form("generate_form"):
            col1, col2 = st.columns(2)
            with col1:
                company_url = st.text_input("Company website URL (optional)", value=DEFAULT_COMPANY_URL,
                                             placeholder="https://www.nike.com")
            with col2:
                company_name = st.text_input("Company name", value=DEFAULT_COMPANY_NAME, placeholder="Nike")

            product_description = st.text_area("What does your product do? (optional — auto-filled from URL)")
            col3, col4 = st.columns(2)
            with col3:
                ad_idea = st.text_area("Your ad idea or angle (optional)")
            with col4:
                event_context = st.text_input("Current event to connect to (optional)",
                                               placeholder="2026 World Cup, Diwali, ...")

            contact_url = st.text_input(
                "Contact URL for the ad's call-to-action (optional)",
                value=DEFAULT_CONTACT_URL,
                placeholder="https://yoursite.com/contact",
                help="Printed as small plain text on the image in place of a CTA button — a generated "
                     "image can't actually be clickable. Leave blank to use the company website URL above.",
            )

            submitted = st.form_submit_button("Generate ads", width="stretch", type="primary",
                                               icon=":material/bolt:")

    if submitted:
        if not company_name and not company_url:
            st.error("Please fill in at least the company name or website URL.")
        else:
            with st.spinner("Researching company, detecting the best event, and writing your ad copy..."):
                try:
                    data = _api("POST", "/generate", json={
                        "company_name": company_name,
                        "product_description": product_description,
                        "ad_idea": ad_idea,
                        "event_context": event_context or None,
                        "company_url": company_url or None,
                    })
                except Exception as e:
                    st.error(f"Something went wrong talking to the backend: {e}")
                    data = None

            if data:
                if data.get("exhausted"):
                    st.error(f"All text generation providers are exhausted: {data.get('error')}")
                elif data.get("success"):
                    st.session_state.campaign = data
                    st.session_state.image = None
                    effective_contact_url = (
                        contact_url.strip() or company_url.strip() or (data.get("website_url") or "").strip()
                    )
                    with st.spinner("Generating your ad image..."):
                        _generate_image(
                            data, data.get("ads", {}), data.get("company_details") or {}, company_name,
                            contact_url=effective_contact_url,
                        )
                else:
                    st.error(f"Error: {data.get('error')}")

    campaign = st.session_state.campaign
    if campaign:
        st.success(f"Campaign ready for **{campaign.get('detected_company_name', company_name)}** — open the "
                   "**Review copy** tab to see it, or **Image & publish** to generate the ad image.")
        m1, m2, m3 = st.columns(3)
        m1.metric("Detected event", campaign.get("detected_event") or "—")
        m2.metric("Quality score", f"{campaign.get('quality_score', 0)}/10")
        m3.metric("Platforms generated", str(len(PLATFORMS)))

campaign = st.session_state.campaign

with review_tab:
    if not campaign:
        st.info("Generate a campaign in the **Generate** tab first.")
    else:
        if campaign.get("detected_event"):
            ev_col, retry_col = st.columns([4, 1])
            ev_col.info(f"Event used: **{campaign['detected_event']}**")
            if retry_col.button("Try different event", width="stretch", icon=":material/refresh:"):
                with st.spinner("Finding a new event and regenerating..."):
                    try:
                        data = _api("POST", "/retry-event", json={
                            "company_name": campaign.get("detected_company_name", company_name),
                            "company_url": company_url,
                        })
                        if data.get("success"):
                            st.session_state.campaign = data
                            st.session_state.image = None
                            st.rerun()
                        else:
                            st.error(f"Could not get a new event: {data.get('error')}")
                    except Exception as e:
                        st.error(f"Something went wrong retrying the event: {e}")

        score = campaign.get("quality_score", 0)
        if score:
            with st.container(border=True):
                sc1, sc2 = st.columns([1, 5])
                with sc1:
                    st.markdown(f"""
                    <div style="text-align:center;">
                        <div style="font-size:1.8rem;font-weight:800;color:{score_color(score)};">{score}/10</div>
                        <div style="font-size:.75rem;color:{PALETTE["text_muted"]};font-weight:600;text-transform:uppercase;">quality</div>
                    </div>
                    """, unsafe_allow_html=True)
                with sc2:
                    st.markdown("**Ad quality report**")
                    st.caption(campaign.get("quality_reason", ""))

        details = campaign.get("company_details") or {}
        if details:
            with st.expander("Company details used in generation", icon=":material/domain:"):
                df = pd.DataFrame([
                    {"Field": label, "Value": details.get(field) or "—"}
                    for label, field in DETAIL_FIELDS
                ])
                st.dataframe(df, hide_index=True, width="stretch")

        ads = campaign.get("ads", {})
        with st.container(border=True):
            st.markdown('<p class="section-title">Platform captions</p>', unsafe_allow_html=True)
            st.markdown("""
            <div class="table-header">
                <div style="min-width:140px;">Platform</div>
                <div style="flex:1;">Caption</div>
                <div style="min-width:160px;">Action</div>
            </div>
            """, unsafe_allow_html=True)
            for platform in PLATFORMS:
                st.markdown('<div class="table-row">', unsafe_allow_html=True)
                name_col, copy_col, action_col = st.columns([1.4, 4, 1.4])
                with name_col:
                    st.markdown(
                        f'<div class="platform-name"><span class="platform-dot" '
                        f'style="background:{platform["color"]}"></span>{platform["label"]}</div>',
                        unsafe_allow_html=True,
                    )
                with copy_col:
                    st.text_area(
                        platform["label"], value=ads.get(platform["key"], ""),
                        key=f"copy_{platform['key']}", height=90, label_visibility="collapsed",
                    )
                with action_col:
                    st.download_button(
                        "Download", icon=":material/download:",
                        data=ads.get(platform["key"], ""),
                        file_name=f"{platform['key']}_caption.txt",
                        mime="text/plain",
                        key=f"download_{platform['key']}",
                        width="stretch",
                    )
                st.markdown('</div>', unsafe_allow_html=True)

with publish_tab:
    if not campaign:
        st.info("Generate a campaign in the **Generate** tab first.")
    else:
        ads = campaign.get("ads", {})
        details = campaign.get("company_details") or {}

        with st.container(border=True):
            st.markdown('<p class="section-title">Ad image</p>', unsafe_allow_html=True)

            last_prompt = (st.session_state.image or {}).get("prompt", "")
            with st.expander("Customize image prompt", icon=":material/tune:"):
                st.caption(
                    "By default the background scene is written automatically by AI, "
                    "tailored to your company/event/copy — you don't need to fill this in. "
                    "The box below is only for overriding that with your own description."
                )
                use_custom_prompt = st.checkbox("Use my own image prompt instead")
                custom_prompt = st.text_area(
                    "Describe the image you want",
                    value=last_prompt,
                    disabled=not use_custom_prompt,
                )

            if st.button("Generate / regenerate image", width="stretch", type="primary",
                         icon=":material/auto_awesome:"):
                effective_contact_url = (
                    contact_url.strip() or company_url.strip() or (campaign.get("website_url") or "").strip()
                )
                with st.spinner("Generating image..."):
                    _generate_image(
                        campaign, ads, details, company_name,
                        custom_prompt=custom_prompt if use_custom_prompt else "",
                        contact_url=effective_contact_url,
                    )

            # Rendered outside the generate button's block (not nested inside it) —
            # a button nested inside another button's `if` only appears on the run
            # that button triggered, and its own click is never seen on the next
            # rerun, so this state has to survive in session_state instead.
            pending = st.session_state.get("provider_failed")
            if pending:
                st.warning(f"{pending['failed_provider']} failed. Switch to {pending['next_provider_label']} and try again.")
                if st.button(f"Switch to {pending['next_provider_label']}"):
                    _api("POST", "/switch-image-provider", json={"provider": pending["next_provider_name"]})
                    st.session_state.provider_failed = None
                    st.rerun()

            image = st.session_state.image
            if image:
                image_url = f"{BACKEND_BASE_URL}{image['clean_image_url']}"
                st.image(image_url, width="stretch")
                st.caption(f"Image model: {image.get('provider', 'openai_image')}")

                if image.get("prompt"):
                    with st.expander("Background prompt used (AI-written)", expanded=True, icon=":material/history_edu:"):
                        st.code(image["prompt"], language=None, wrap_lines=True)

                try:
                    image_bytes = requests.get(image_url, timeout=30).content
                    st.download_button(
                        "Download ad image", icon=":material/download:",
                        data=image_bytes,
                        file_name=os.path.basename(image_url),
                        mime="image/jpeg",
                        key="download_image",
                    )
                except Exception as e:
                    st.caption(f"(Download unavailable: {e})")

        if image:
            with st.container(border=True):
                st.markdown('<p class="section-title">Post to your accounts</p>', unsafe_allow_html=True)
                st.caption("Review the copy and image above, then approve posting to each platform individually.")
                pi, pf, pl = st.columns(3)

                with pi:
                    st.markdown(
                        '<div class="platform-name"><span class="platform-dot" style="background:#C13584"></span>Instagram</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Post to Instagram", width="stretch", key="post_instagram"):
                        with st.spinner("Posting to Instagram..."):
                            try:
                                r = _api("POST", "/post-to-instagram", json={"caption": ads.get("instagram", ""), "image_url": image_url})
                                st.success("Posted!") if r.get("success") else st.error(r.get("error"))
                            except Exception as e:
                                st.error(str(e))

                with pf:
                    st.markdown(
                        '<div class="platform-name"><span class="platform-dot" style="background:#1877f2"></span>Facebook</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Post to Facebook", width="stretch", key="post_facebook"):
                        with st.spinner("Posting to Facebook..."):
                            try:
                                r = _api("POST", "/post-to-facebook", json={"caption": ads.get("facebook", ""), "image_url": image_url})
                                st.success("Posted!") if r.get("success") else st.error(r.get("error"))
                            except Exception as e:
                                st.error(str(e))

                with pl:
                    st.markdown(
                        '<div class="platform-name"><span class="platform-dot" style="background:#0a66c2"></span>LinkedIn</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("Post to LinkedIn", width="stretch", key="post_linkedin"):
                        with st.spinner("Posting to LinkedIn..."):
                            try:
                                r = _api("POST", "/post-to-linkedin", json={"caption": ads.get("linkedin", ""), "image_url": image_url})
                                if r.get("success"):
                                    st.session_state.linkedin_post_urn = r.get("post_id")
                                    st.success("Posted!")
                                else:
                                    st.error(r.get("error"))
                            except Exception as e:
                                st.error(str(e))

        if image and SHOW_PAID_PROMOTION:
            with st.container(border=True):
                st.markdown('<p class="section-title">Paid promotion (Meta &amp; LinkedIn)</p>', unsafe_allow_html=True)
                st.caption(
                    "Creates a draft campaign only — nothing is ever activated automatically. "
                    "Review the numbers below, then explicitly activate when you're ready to spend."
                )

                fb_tab, li_tab = st.tabs(["Meta (Facebook/Instagram)", "LinkedIn"])

                with fb_tab:
                    draft = st.session_state.facebook_ad_draft
                    if not draft:
                        fb_budget = st.number_input("Daily budget (USD)", min_value=1.0, value=10.0, step=1.0, key="fb_budget")
                        fb_days = st.number_input("Run for how many days", min_value=1, value=7, step=1, key="fb_days")
                        fb_countries = st.multiselect(
                            "Countries to target", options=[c for c, _ in AD_COUNTRIES],
                            format_func=lambda c: dict(AD_COUNTRIES)[c], default=["US"], key="fb_countries",
                        )
                        if st.button("Create draft campaign", icon=":material/drafts:", key="create_fb_ad",
                                     disabled=not fb_countries):
                            start_dt = datetime.now(timezone.utc)
                            end_dt = start_dt + timedelta(days=fb_days)
                            with st.spinner("Creating draft campaign on Meta..."):
                                try:
                                    r = _api("POST", "/create-facebook-ad-campaign", json={
                                        "name": f"{campaign.get('detected_company_name', company_name)} - "
                                                f"{campaign.get('detected_event') or 'campaign'}",
                                        "image_url": image_url,
                                        "message": ads.get("facebook", ""),
                                        "link": (contact_url.strip() or company_url.strip()
                                                 or (campaign.get("website_url") or "").strip()),
                                        "daily_budget_usd": fb_budget,
                                        "countries": fb_countries,
                                        "start_time": start_dt.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                        "end_time": end_dt.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                    })
                                    if r.get("success"):
                                        r["_daily_budget"] = fb_budget
                                        r["_days"] = fb_days
                                        st.session_state.facebook_ad_draft = r
                                        st.rerun()
                                    else:
                                        st.error(r.get("error"))
                                except Exception as e:
                                    st.error(f"Something went wrong creating the campaign: {e}")
                    else:
                        est_spend = draft["_daily_budget"] * draft["_days"]
                        st.success("Draft campaign created — status: PAUSED (not spending).")
                        st.write(f"Campaign `{draft['campaign_id']}` / ad set `{draft['adset_id']}` / ad `{draft['ad_id']}`")
                        st.metric("Estimated total spend", f"${est_spend:,.2f}",
                                  help=f"${draft['_daily_budget']:,.2f}/day x {draft['_days']} days")
                        fb_password = st.text_input(
                            "Execution password (required to activate — this will start spending real budget)",
                            type="password", key="fb_execution_password",
                        )
                        col_a, col_b = st.columns(2)
                        if col_a.button("Activate campaign", icon=":material/rocket_launch:", type="primary",
                                         width="stretch", disabled=not fb_password, key="activate_fb_ad"):
                            with st.spinner("Activating campaign..."):
                                try:
                                    r = _api("POST", "/activate-facebook-ad-campaign", json={
                                        "campaign_id": draft["campaign_id"],
                                        "adset_id": draft["adset_id"],
                                        "ad_id": draft["ad_id"],
                                        "password": fb_password,
                                    })
                                    if r.get("success"):
                                        st.success("Campaign activated — it's now live and spending.")
                                    else:
                                        st.error(r.get("error"))
                                except Exception as e:
                                    st.error(str(e))
                        if col_b.button("Discard draft", width="stretch", key="discard_fb_ad"):
                            st.session_state.facebook_ad_draft = None
                            st.rerun()

                with li_tab:
                    li_post_urn = st.session_state.linkedin_post_urn
                    draft = st.session_state.linkedin_ad_draft
                    if not li_post_urn:
                        st.info("Post to LinkedIn organically first (above) so there's content to promote — "
                                "this reuses that post rather than creating new sponsored content from scratch.")
                    elif not draft:
                        st.caption(f"Will promote the post you just published: `{li_post_urn}`")
                        li_budget = st.number_input("Daily budget (USD)", min_value=1.0, value=10.0, step=1.0, key="li_budget")
                        li_days = st.number_input("Run for how many days", min_value=1, value=7, step=1, key="li_days")
                        li_country = st.selectbox(
                            "Country to target", options=[c for c, _ in AD_COUNTRIES],
                            format_func=lambda c: dict(AD_COUNTRIES)[c], key="li_country",
                        )
                        if st.button("Create draft campaign", icon=":material/drafts:", key="create_li_ad"):
                            start_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                            end_ms = start_ms + li_days * 86400000
                            with st.spinner("Creating draft campaign on LinkedIn..."):
                                try:
                                    r = _api("POST", "/create-linkedin-ad-campaign", json={
                                        "name": f"{campaign.get('detected_company_name', company_name)} - "
                                                f"{campaign.get('detected_event') or 'campaign'}",
                                        "share_urn": li_post_urn,
                                        "daily_budget_usd": li_budget,
                                        "country_code": li_country,
                                        "start_time_ms": start_ms,
                                        "end_time_ms": end_ms,
                                    })
                                    if r.get("success"):
                                        r["_daily_budget"] = li_budget
                                        r["_days"] = li_days
                                        st.session_state.linkedin_ad_draft = r
                                        st.rerun()
                                    else:
                                        st.error(r.get("error"))
                                except Exception as e:
                                    st.error(f"Something went wrong creating the campaign: {e}")
                    else:
                        est_spend = draft["_daily_budget"] * draft["_days"]
                        st.success("Draft campaign created — status: DRAFT (not spending).")
                        st.write(f"Campaign group `{draft['campaign_group_urn']}` / campaign `{draft['campaign_urn']}` "
                                 f"/ creative `{draft['creative_urn']}`")
                        st.metric("Estimated total spend", f"${est_spend:,.2f}",
                                  help=f"${draft['_daily_budget']:,.2f}/day x {draft['_days']} days")
                        li_password = st.text_input(
                            "Execution password (required to activate — this will start spending real budget)",
                            type="password", key="li_execution_password",
                        )
                        col_a, col_b = st.columns(2)
                        if col_a.button("Activate campaign", icon=":material/rocket_launch:", type="primary",
                                         width="stretch", disabled=not li_password, key="activate_li_ad"):
                            with st.spinner("Activating campaign..."):
                                try:
                                    r = _api("POST", "/activate-linkedin-ad-campaign", json={
                                        "campaign_group_urn": draft["campaign_group_urn"],
                                        "campaign_urn": draft["campaign_urn"],
                                        "creative_urn": draft["creative_urn"],
                                        "password": li_password,
                                    })
                                    if r.get("success"):
                                        st.success("Campaign activated — it's now live and spending.")
                                    else:
                                        st.error(r.get("error"))
                                except Exception as e:
                                    st.error(str(e))
                        if col_b.button("Discard draft", width="stretch", key="discard_li_ad"):
                            st.session_state.linkedin_ad_draft = None
                            st.rerun()

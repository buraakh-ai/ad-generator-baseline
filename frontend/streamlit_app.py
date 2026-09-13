"""Streamlit frontend — calls the FastAPI backend over HTTP using
BACKEND_BASE_URL. Deployed independently of the backend, per the brief.
Recreates the original app's flow: fill in a company -> generate platform
ad copy tied to a trending/cultural event -> generate an image -> post to
Instagram/Facebook/LinkedIn."""
import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Ad Generator", page_icon="⬛", layout="wide")

PLATFORMS = [
    {"key": "tiktok", "label": "TikTok / Reels", "color": "#FE2C55"},
    {"key": "instagram", "label": "Instagram", "color": "#C13584"},
    {"key": "twitter", "label": "X / Twitter", "color": "#0f172a"},
    {"key": "facebook", "label": "Facebook", "color": "#1877f2"},
    {"key": "linkedin", "label": "LinkedIn", "color": "#0a66c2"},
]

DETAIL_FIELDS = [
    ("What they do", "what_they_do"), ("Services", "services"),
    ("Target audience", "target_audience"), ("Brand tone", "brand_tone"),
    ("Key values", "key_values"), ("Tagline", "tagline"),
]

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #f8fafc; }
.main .block-container { max-width: 1120px; padding-top: 1.25rem; padding-bottom: 3rem; }

/* ---- navbar ---- */
.navbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 1rem 1.5rem; background: #fff; border: 1px solid #e2e8f0;
    border-radius: 12px; margin-bottom: 1.5rem;
}
.navbar-brand { font-weight: 800; font-size: 1.1rem; color: #0f172a; letter-spacing: -.01em; }
.navbar-status { display: flex; align-items: center; gap: .5rem; font-size: .82rem; color: #64748b; font-weight: 600; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

/* ---- containers / surfaces ---- */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border: 1px solid #e2e8f0 !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
}
div[data-testid="stExpander"] {
    border-radius: 10px !important;
    border: 1px solid #e2e8f0 !important;
    overflow: hidden;
}
.stAlert { border-radius: 10px; }

/* ---- tabs ---- */
button[data-baseweb="tab"] { font-weight: 600; color: #64748b; font-size: .95rem; }
button[data-baseweb="tab"][aria-selected="true"] { color: #4f46e5; }
div[data-baseweb="tab-highlight"] { background-color: #4f46e5 !important; }
div[data-baseweb="tab-border"] { background-color: #e2e8f0 !important; }

/* ---- inputs ---- */
.stTextArea textarea, .stTextInput input {
    border-radius: 8px;
    border: 1px solid #e2e8f0;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: #4f46e5;
    box-shadow: 0 0 0 3px rgba(79, 70, 229, .12);
}

/* ---- buttons: neutral by default, solid indigo for primary actions ---- */
.stButton > button, .stDownloadButton > button {
    border-radius: 8px;
    font-weight: 600;
    border: 1px solid #e2e8f0;
    background: #fff;
    color: #334155;
    transition: background .12s ease, border-color .12s ease, color .12s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    border-color: #4f46e5;
    color: #4f46e5;
    background: #eef2ff;
}
button[kind="primary"], [data-testid="stBaseButton-primary"] {
    background: #4f46e5 !important;
    border: 1px solid #4f46e5 !important;
    color: #fff !important;
}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover {
    background: #4338ca !important;
    border-color: #4338ca !important;
}

/* ---- platform table rows ---- */
.table-header {
    display: flex; gap: 1rem; padding: 0 0 .6rem; border-bottom: 2px solid #e2e8f0;
    font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #94a3b8;
}
.table-row {
    display: flex; align-items: flex-start; gap: 1rem; padding: 1rem 0; border-bottom: 1px solid #e2e8f0;
}
.platform-name { display: flex; align-items: center; font-weight: 600; font-size: .9rem; color: #0f172a; padding-top: .5rem; }
.platform-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; flex-shrink: 0; }

.section-title { font-size: 1.15rem; font-weight: 700; margin: 0 0 1rem; color: #0f172a; }
.section-subtitle { color: #64748b; font-size: .92rem; margin: -.5rem 0 1.25rem; }
</style>
""", unsafe_allow_html=True)

if "campaign" not in st.session_state:
    st.session_state.campaign = None
if "image" not in st.session_state:
    st.session_state.image = None
if "provider_failed" not in st.session_state:
    st.session_state.provider_failed = None


def _api(method, path, **kwargs):
    r = requests.request(method, f"{BACKEND_BASE_URL}{path}", timeout=180, **kwargs)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=30, show_spinner=False)
def _backend_online():
    try:
        return requests.get(f"{BACKEND_BASE_URL}/", timeout=2).status_code == 200
    except Exception:
        return False


def _score_color(score):
    if score >= 8:
        return "#16a34a"
    if score >= 5:
        return "#d97706"
    return "#dc2626"


def _generate_image(campaign, ads, details, fallback_company_name, custom_prompt=""):
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


online = _backend_online()
st.markdown(f"""
<div class="navbar">
    <div class="navbar-brand">⬛ Ad Generator</div>
    <div class="navbar-status">
        <span class="status-dot" style="background:{'#16a34a' if online else '#dc2626'}"></span>
        Backend {"online" if online else "offline"}
    </div>
</div>
""", unsafe_allow_html=True)

gen_tab, review_tab, publish_tab = st.tabs(["1. Generate", "2. Review copy", "3. Image & publish"])

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
                company_url = st.text_input("Company website URL (optional)", placeholder="https://www.nike.com")
            with col2:
                company_name = st.text_input("Company name", placeholder="Nike")

            product_description = st.text_area("What does your product do? (optional — auto-filled from URL)")
            col3, col4 = st.columns(2)
            with col3:
                ad_idea = st.text_area("Your ad idea or angle (optional)")
            with col4:
                event_context = st.text_input("Current event to connect to (optional)",
                                               placeholder="2026 World Cup, Diwali, ...")

            submitted = st.form_submit_button("Generate ads", use_container_width=True, type="primary")

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
                    with st.spinner("Generating your ad image..."):
                        _generate_image(
                            data, data.get("ads", {}), data.get("company_details") or {}, company_name,
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
            if retry_col.button("Try different event", use_container_width=True):
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
                        <div style="font-size:1.8rem;font-weight:800;color:{_score_color(score)};">{score}/10</div>
                        <div style="font-size:.75rem;color:#94a3b8;font-weight:600;text-transform:uppercase;">quality</div>
                    </div>
                    """, unsafe_allow_html=True)
                with sc2:
                    st.markdown("**Ad quality report**")
                    st.caption(campaign.get("quality_reason", ""))

        details = campaign.get("company_details") or {}
        if details:
            with st.expander("Company details used in generation"):
                df = pd.DataFrame([
                    {"Field": label, "Value": details.get(field) or "—"}
                    for label, field in DETAIL_FIELDS
                ])
                st.dataframe(df, hide_index=True, use_container_width=True)

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
                        "Download",
                        data=ads.get(platform["key"], ""),
                        file_name=f"{platform['key']}_caption.txt",
                        mime="text/plain",
                        key=f"download_{platform['key']}",
                        use_container_width=True,
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
            with st.expander("Customize image prompt"):
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

            if st.button("Generate / regenerate image", use_container_width=True, type="primary"):
                with st.spinner("Generating image..."):
                    _generate_image(
                        campaign, ads, details, company_name,
                        custom_prompt=custom_prompt if use_custom_prompt else "",
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
                st.image(image_url, use_container_width=True)
                st.caption(f"Image model: {image.get('provider', 'openai_image')}")

                if image.get("prompt"):
                    with st.expander("Background prompt used (written by gpt-4o-mini)", expanded=True):
                        st.code(image["prompt"], language=None, wrap_lines=True)

                try:
                    image_bytes = requests.get(image_url, timeout=30).content
                    st.download_button(
                        "Download ad image",
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
                    if st.button("Post to Instagram", use_container_width=True, key="post_instagram"):
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
                    if st.button("Post to Facebook", use_container_width=True, key="post_facebook"):
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
                    if st.button("Post to LinkedIn", use_container_width=True, key="post_linkedin"):
                        with st.spinner("Posting to LinkedIn..."):
                            try:
                                r = _api("POST", "/post-to-linkedin", json={"caption": ads.get("linkedin", ""), "image_url": image_url})
                                st.success("Posted!") if r.get("success") else st.error(r.get("error"))
                            except Exception as e:
                                st.error(str(e))

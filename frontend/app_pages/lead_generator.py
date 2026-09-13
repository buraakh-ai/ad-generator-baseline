"""Placeholder module — not built yet. Once it exists, it'll follow the
same pattern as app_pages/ad_generator.py: its own backend base URL
(LEAD_GENERATOR_BACKEND_URL), resolved via utils.api.resolve_backend_url,
pointing at its own separately-deployed backend container (this project's
stated direction is one AWS ECS service per backend module)."""
import streamlit as st

st.title("Lead generator", anchor=False)
st.caption("Not built yet — shown here so the module navigation reflects where this suite is headed.")

with st.container(border=True):
    st.markdown("#### :material/construction: Coming soon")
    st.write(
        "This module will connect to its own backend (a separate AWS ECS service, "
        "same pattern as the Ad generator module) to find and qualify leads."
    )
    st.caption("Ask to have this module built once its backend exists.")

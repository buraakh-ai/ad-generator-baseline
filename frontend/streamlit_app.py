"""CRM-style shell for a suite of AI growth modules, each its own page under
app_pages/ talking to its own backend container (this project's stated
direction: one AWS ECS service per backend). Today there's one real module,
Ad generator (app_pages/ad_generator.py, calls the FastAPI backend in this
repo); Lead generator is a placeholder until its own backend exists.

Colors/fonts come from .streamlit/config.toml (native theming) — see that
file's header comment for why it lives at the repo root."""
from dotenv import load_dotenv
import streamlit as st

from utils.theme import inject_global_css

load_dotenv()

st.set_page_config(page_title="Buraq Growth Suite", page_icon=":material/rocket_launch:", layout="wide")
inject_global_css()

with st.sidebar:
    st.markdown("### :material/hub: Buraq Growth Suite")
    st.caption("AI marketing & growth modules")
    st.divider()

page = st.navigation({
    "Modules": [
        st.Page("app_pages/ad_generator.py", title="Ad generator", icon=":material/campaign:", default=True),
        st.Page("app_pages/lead_generator.py", title="Lead generator", icon=":material/person_search:"),
    ],
})
page.run()

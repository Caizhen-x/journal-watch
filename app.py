"""Navigation entrypoint for the Journal Watch Streamlit app."""
from pathlib import Path

import streamlit as st

from auth import require_password

REPO_ROOT = Path(__file__).parent
LOGO_PATH = str(REPO_ROOT / "assets" / "hu-logo.png")

st.set_page_config(
    page_title="Agrifood Journal Watch — HU Berlin",
    page_icon=LOGO_PATH,
    layout="wide",
)

st.logo(LOGO_PATH, size="large")

require_password()

dashboard_page = st.Page("views/dashboard.py", title="Dashboard", icon="📚", default=True)
trends_page = st.Page("views/trends.py", title="Trends", icon="📊")

pg = st.navigation([dashboard_page, trends_page])
pg.run()

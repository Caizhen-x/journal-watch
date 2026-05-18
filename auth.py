"""Shared password gate for Streamlit pages.

Usage in any page:
    from auth import require_password
    require_password()  # st.stop()s if not authed

The password is read from st.secrets["app_password"]. When deployed on
Streamlit Cloud, set it in the app's Secrets section.

If no password is configured, the gate fails CLOSED (refuses access) unless
the developer explicitly opts in by setting JOURNAL_WATCH_DEV_MODE=true in
their local environment — this prevents accidental wide-open hosting if the
secret is ever removed in production.
"""
import os

import streamlit as st


def require_password():
    if st.session_state.get("authed"):
        return

    expected = st.secrets.get("app_password") if hasattr(st, "secrets") else None
    if not expected:
        if os.environ.get("JOURNAL_WATCH_DEV_MODE") == "true":
            st.session_state.authed = True
            return
        st.error(
            "🔒 Authentication is not configured. "
            "Set `app_password` in Streamlit secrets, or run locally with "
            "`JOURNAL_WATCH_DEV_MODE=true` to bypass."
        )
        st.stop()

    st.markdown("## 🔒 Journal Watch")
    st.caption("Enter the group password to continue.")
    pw = st.text_input("Password", type="password", label_visibility="collapsed")
    if pw:
        if pw == expected:
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

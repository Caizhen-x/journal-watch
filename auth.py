"""Shared password gate for Streamlit pages.

Usage in any page:
    from auth import require_password
    require_password()  # st.stop()s if not authed

The password is read from st.secrets["app_password"]. When running locally,
set it in .streamlit/secrets.toml (gitignored). When deployed on Streamlit Cloud,
set it in the app's Secrets section in the dashboard.
"""
import streamlit as st


def require_password():
    if st.session_state.get("authed"):
        return

    expected = st.secrets.get("app_password") if hasattr(st, "secrets") else None
    if not expected:
        # No password configured — auth is effectively off (e.g., local dev without secrets.toml).
        st.session_state.authed = True
        return

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

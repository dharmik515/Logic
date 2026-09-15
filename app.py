"""Daily Agent Report - a field team's daily log.

Run locally:   streamlit run app.py
Deploy:        push to GitHub, then share.streamlit.io -> New app -> app.py

See README.md for the Supabase setup that makes data survive a redeploy.
"""
from __future__ import annotations

import streamlit as st

from lib import config as C
from lib import ui, view_admin, view_agent, view_login
from lib.storage import get_store

st.set_page_config(
    page_title=C.APP_TITLE,
    page_icon=C.APP_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"about": "Daily Agent Report - field team daily log."},
)

ui.inject_css()

# NB: no default for "login_mode" - that is a widget key, and seeding it here
# would clash with the widget's own default.
for key, default in (
    ("role", None), ("agent", None), ("agent_pin", None),
    ("admin_pin", None), ("forgot", False),
):
    st.session_state.setdefault(key, default)


def logout() -> None:
    keep = {"login_mode"}
    for k in [k for k in st.session_state if k not in keep]:
        st.session_state.pop(k, None)
    st.session_state.role = None
    st.rerun()


def topbar() -> None:
    """Shown once logged in: who you are, the date, and the way out."""
    role = st.session_state.role
    who = st.session_state.agent if role == "agent" else "Admin"
    icon = "🧑‍💼" if role == "agent" else "🛡️"

    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;'
            'padding:2px 0 10px">'
            '<span style="font-size:20px">{}</span>'
            '<span style="font-weight:750">{}</span>'
            '<span class="pill flat">{}</span></div>'.format(
                icon, ui.e(who), ui.e(C.fmt_date(C.today_str()))
            ),
            unsafe_allow_html=True,
        )
    with c2:
        if st.button("Log out", width="stretch", key="logout_btn"):
            logout()


def storage_warning() -> None:
    """Loud, once, for the admin: SQLite on a cloud host is not durable."""
    store = get_store()
    if getattr(store, "persistent_on_cloud", False):
        return
    st.warning(
        "**Storage: SQLite (a local file).** Fine on this machine, but on "
        "Streamlit Community Cloud the disk is wiped whenever the app sleeps or "
        "redeploys - you would lose the month's reports and photos. Create a "
        "free Postgres (Neon, Supabase, Railway), put its connection string in "
        "app secrets as `DATABASE_URL`, and reboot. The app creates its own "
        "tables - there is no SQL to run.",
        icon="⚠️",
    )


def main() -> None:
    role = st.session_state.role

    if role == "agent":
        topbar()
        view_agent.render()
    elif role == "admin":
        topbar()
        storage_warning()
        view_admin.render()
    else:
        view_login.render()

    st.markdown(
        '<div style="text-align:center;color:#8a91a0;font-size:12px;padding:30px 0 6px">'
        "Daily Agent Report · data kept for {} days · operational numbers only"
        "</div>".format(C.RETENTION_DAYS),
        unsafe_allow_html=True,
    )


main()

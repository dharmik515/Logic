"""Test harness: runs the real app with a session pre-seeded from the
environment, so a browser can be pointed at any screen without logging in.

    SHOT_ROLE=admin streamlit run tests/_harness_app.py

Used by check_responsive.py. Not part of the app itself - never deploy it.
"""
import os
import sys

import streamlit as st

sys.path.insert(0, os.getcwd())

role = os.environ.get("SHOT_ROLE", "")
if role == "admin":
    st.session_state.setdefault("role", "admin")
    st.session_state.setdefault("admin_pin", os.environ.get("SHOT_ADMIN_PIN", "24668"))
elif role == "agent":
    st.session_state.setdefault("role", "agent")
    st.session_state.setdefault("agent", os.environ.get("SHOT_AGENT", "Alpha"))
    if os.environ.get("SHOT_EDIT"):
        st.session_state.setdefault("day_key", "")
        st.session_state.setdefault("edit_mode", True)

exec(compile(open("app.py", encoding="utf-8").read(), "app.py", "exec"))

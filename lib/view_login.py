"""Login screen: agent (name + personal PIN) or admin (one PIN), plus the
self-service 'I forgot my PIN' request that an admin later approves."""
from __future__ import annotations

import streamlit as st

from . import auth
from . import config as C
from . import security
from . import ui


def _choose_name(key: str):
    """Wrapping chips on new Streamlit, a radio grid on older versions."""
    names = auth.load_agents()
    if hasattr(st, "pills"):
        return st.pills("Your name", names, selection_mode="single", key=key)
    return st.radio("Your name", names, index=None, horizontal=True, key=key)


def _login_agent() -> None:
    st.markdown("###### 👤 Who is reporting?")

    if not auth.load_agents():
        ui.note(
            "No agents have been added yet. Your admin needs to open the Admin tab "
            "and add the team under 'Team, PINs & reset requests' before anyone "
            "can log in.",
            "warn",
        )
        return

    name = _choose_name("pick_agent")

    pin = st.text_input(
        "Your PIN",
        type="password",
        max_chars=6,
        placeholder="• • • •",
        key="pin_agent",
        help="Your personal 4-6 digit PIN. Ask your admin if you do not have it.",
    )

    if st.button("Log in", type="primary", width="stretch", key="go_agent"):
        if not name:
            st.warning("Please tap your name first.")
        elif not pin:
            st.warning("Please enter your PIN.")
        elif auth.check_agent(name, pin):
            st.session_state.update(role="agent", agent=name, agent_pin=pin)
            st.toast("Welcome back, {}!".format(name), icon="👋")
            st.rerun()
        else:
            locked, left = auth.locked_out(name or "")
            if locked:
                st.error(security.describe_lockout(left))
            else:
                st.error("That PIN does not match. Try again, or use 'Forgot my PIN' below.")

    st.markdown("")
    if st.button("🔑 Forgot my PIN", width="stretch", key="to_forgot"):
        st.session_state.forgot = True
        st.rerun()


def _login_admin() -> None:
    st.markdown("###### 🛡️ Admin access")

    if not C.admin_configured():
        ui.note(
            "Admin access is not set up yet. Add ADMIN_PIN to this app's secrets "
            "(Streamlit Cloud: Manage app → Settings → Secrets) and reboot. "
            "There is deliberately no built-in PIN - the source is public.",
            "warn",
        )
        return

    pin = st.text_input(
        "Admin PIN", type="password", max_chars=10, placeholder="• • • • •", key="pin_admin"
    )
    if st.button("Open dashboard", type="primary", width="stretch", key="go_admin"):
        if auth.check_admin(pin):
            st.session_state.update(role="admin", admin_pin=pin)
            st.toast("Admin dashboard unlocked", icon="🛡️")
            st.rerun()
        else:
            locked, left = auth.locked_out("admin")
            st.error(security.describe_lockout(left) if locked else "Wrong admin PIN.")


def _forgot() -> None:
    st.markdown("###### 🔑 Request a new PIN")
    ui.note(
        "Pick your name, choose the new PIN you want, and send the request. "
        "Your admin has to approve it before it starts working.",
        "info",
    )
    ui.spacer(10)

    if not auth.load_agents():
        ui.note("No agents have been added yet - ask your admin.", "warn")
        return

    name = _choose_name("pick_reset")
    new_pin = st.text_input(
        "New PIN you want", max_chars=6, placeholder="4 to 6 digits", key="pin_reset"
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Send request", type="primary", width="stretch"):
            ok, msg = auth.request_reset(name or "", new_pin)
            if ok:
                st.session_state.forgot = False
                st.session_state.reset_sent = msg
                st.rerun()
            else:
                st.error(msg)
    with c2:
        if st.button("Back to login", width="stretch"):
            st.session_state.forgot = False
            st.rerun()


def render() -> None:
    ui.hero(
        "Daily Agent Report",
        "Log your day in under a minute - odometer, deals, fuel and cash.",
        ["🔒 Private", "📱 Works on any phone", "🗓️ {}".format(C.fmt_date(C.today_str()))],
    )
    ui.spacer(18)

    sent = st.session_state.pop("reset_sent", None)
    if sent:
        st.success(sent, icon="✅")

    left, right = st.columns([1, 1])
    with left:
        with st.container(border=True):
            # The widget is its own source of truth - Streamlit reruns on change,
            # so there is no second copy of this state to keep in sync.
            if hasattr(st, "segmented_control"):
                mode = st.segmented_control(
                    "Mode", ["Agent", "Admin"], default="Agent",
                    key="login_mode", label_visibility="collapsed",
                )
            else:
                mode = st.radio(
                    "Mode", ["Agent", "Admin"], horizontal=True,
                    key="login_mode", label_visibility="collapsed",
                )

            st.markdown("")
            if (mode or "Agent") == "Agent":
                _forgot() if st.session_state.get("forgot") else _login_agent()
            else:
                _login_admin()

    with right:
        st.markdown(
            """
            <div class="panel fade">
              <div class="sec" style="margin-top:0">
                <div class="ico">📋</div>
                <div><h3>How your day works</h3>
                <p class="sub">Two quick check-ins, that is all</p></div>
              </div>
              <div class="drow" style="grid-template-columns:1fr">
                <div class="c" style="margin-bottom:10px">
                  <div class="k">Morning</div>
                  <div class="v" style="font-size:14px">Type your Starting KM and snap the odometer.</div>
                </div>
                <div class="c" style="margin-bottom:10px">
                  <div class="k">Evening</div>
                  <div class="v" style="font-size:14px">Ending KM + photo, deals done, fuel, cash spent
                  and any differential collected.</div>
                </div>
                <div class="c">
                  <div class="k">Anything wrong?</div>
                  <div class="v" style="font-size:14px">You can reopen and edit today's report until midnight.</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

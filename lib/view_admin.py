"""The admin dashboard: totals, charts, per-agent detail with photos, CSV
export, PIN management and the reset-request approvals."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import pandas as pd
import streamlit as st

from . import auth, charts, config as C, export, images, records, ui
from .storage import get_store


# ---------------------------------------------------------------- photo view
def _render_photo(agent: str, date: str, which: str, label: str) -> None:
    data = records.photo(agent, date, which)
    raw = images.decode(data)
    if raw:
        st.image(raw, caption="{} · {} · {}".format(agent, C.fmt_date(date), label),
                 width="stretch")
    else:
        st.warning("That photo is not on file.")


if hasattr(st, "dialog"):

    @st.dialog("Photo", width="large")
    def show_photo(agent: str, date: str, which: str, label: str) -> None:
        _render_photo(agent, date, which, label)

else:  # older Streamlit - fall back to rendering inline

    def show_photo(agent: str, date: str, which: str, label: str) -> None:
        st.session_state.photo_inline = (agent, date, which, label)
        st.rerun()


# -------------------------------------------------------------------- pins
def _pins_panel() -> None:
    reqs = auth.load_requests()
    pins = auth.load_pins()

    if reqs:
        ui.section("🔔", "Pending PIN requests", "Approve to switch the agent to their new PIN.")
        for agent, req in list(reqs.items()):
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    st.markdown(
                        "**{}** wants PIN `{}`  \n<span class='pill flat'>asked {}</span>".format(
                            agent, req.get("requestedPin", "?"), C.fmt_time(req.get("at")) or "-"),
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button("✅ Approve", key="ap_" + agent, type="primary",
                                 width="stretch"):
                        ok, msg = auth.approve_request(agent)
                        st.toast(msg, icon="✅" if ok else "⚠️")
                        st.rerun()
                with c3:
                    if st.button("✕ Reject", key="rj_" + agent, width="stretch"):
                        ok, msg = auth.reject_request(agent)
                        st.toast(msg, icon="🚫")
                        st.rerun()
        ui.spacer(10)

    roster = auth.load_agents()

    # ---- add someone new -------------------------------------------------
    ui.section("➕", "Add an agent", "They can log in as soon as you add them.")
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.5, 1, 0.9])
        with c1:
            new_name = st.text_input("Name", key="new_agent_name", placeholder="e.g. Rahul",
                                     max_chars=30)
        with c2:
            new_pin = st.text_input("PIN", key="new_agent_pin", placeholder="4-6 digits",
                                    max_chars=6)
        with c3:
            st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
            if st.button("Add agent", key="add_agent", type="primary", width="stretch"):
                ok, msg = auth.add_agent(new_name, new_pin)
                if ok:
                    st.success(msg + " Note it down - PINs are stored hashed and "
                               "cannot be shown again.", icon="✅")
                else:
                    st.toast(msg, icon="⚠️")
                if ok:
                    # clear the form for the next one
                    st.session_state.pop("new_agent_name", None)
                    st.session_state.pop("new_agent_pin", None)
                    st.rerun()
                st.error(msg)

    # ---- the team --------------------------------------------------------
    ui.section("🔑", "The team",
               "{} agents. PINs are stored hashed, so none can be shown here - "
               "set a new one if somebody is locked out.".format(len(roster)))
    pending_removal = st.session_state.get("confirm_remove")

    for agent in roster:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.3, 1.1, 0.8, 0.8])
            with c1:
                st.markdown("<div style='padding-top:30px;font-weight:700'>{}</div>".format(
                    ui.e(agent)), unsafe_allow_html=True)
            with c2:
                st.text_input("Set a new PIN", value="", key="pin_" + agent,
                              max_chars=6, placeholder="4-6 digits",
                              help="Type a new PIN and press Save. The existing one "
                                   "cannot be displayed - it is stored as a hash.")
            with c3:
                st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
                if st.button("Save", key="sv_" + agent, width="stretch"):
                    typed = st.session_state.get("pin_" + agent, "")
                    ok, msg = auth.set_pin(agent, typed)
                    if ok:
                        # Shown once, to the person who just typed it, so they
                        # can pass it on. It is a hash from here on.
                        st.success("{}'s PIN is now {} - tell them, it cannot be "
                                   "looked up later.".format(agent, typed), icon="🔑")
                    else:
                        st.toast(msg, icon="⚠️")
            with c4:
                st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
                if st.button("Remove", key="rm_" + agent, width="stretch"):
                    st.session_state.confirm_remove = agent
                    st.rerun()

            # Removing someone is not undoable from the UI, so make them confirm.
            if pending_removal == agent:
                ui.note(
                    "Remove {} from the team? They will not be able to log in again. "
                    "Their reports from the last {} days stay on the dashboard."
                    .format(agent, C.RETENTION_DAYS), "warn")
                d1, d2 = st.columns(2)
                with d1:
                    if st.button("Yes, remove {}".format(agent), key="rmy_" + agent,
                                 width="stretch"):
                        ok, msg = auth.remove_agent(agent)
                        st.session_state.pop("confirm_remove", None)
                        st.toast(msg, icon="🗑️" if ok else "⚠️")
                        st.rerun()
                with d2:
                    if st.button("Cancel", key="rmn_" + agent, width="stretch"):
                        st.session_state.pop("confirm_remove", None)
                        st.rerun()


# ------------------------------------------------------------- agent detail
def _agent_card(entry: Dict, show_date: bool) -> None:
    agent = entry.get("agent", "?")
    date = entry.get("date", "")
    done = entry.get("status") == "completed"

    with st.container(border=True):
        head = "**{}**".format(agent)
        if show_date:
            head += "  ·  {}".format(C.fmt_date(date))
        st.markdown(
            head + "  " + ui.pill("Submitted" if done else "Start only", "good" if done else "warn"),
            unsafe_allow_html=True,
        )

        # A start-only day has no deals or spend *yet* - that is different from
        # a day where the agent reported zero, so show a dash, not a 0.
        def n(field, fmt="{:,.0f}", suffix=""):
            v = entry.get(field)
            return "-" if v is None else fmt.format(v) + suffix

        cells = [
            ("Start KM", n("startKm"), C.fmt_time(entry.get("startKmAt"))),
            ("End KM", n("endKm"), C.fmt_time(entry.get("endKmAt"))),
            ("Distance", n("distance", suffix=" km"), ""),
            ("Deals", n("totalDeals"), ""),
            ("Fuel", n("fuelAmount", "₹{:,.0f}"), C.fmt_time(entry.get("fuelAt"))),
            ("Opening", n("openingBalance", "₹{:,.0f}"), ""),
            ("Spent", n("spentAmount", "₹{:,.0f}"), ""),
            ("Remaining", n("remainingBalance", "₹{:,.0f}"),
             "short by {:,.0f}".format(abs(entry["remainingBalance"]))
             if entry.get("remainingBalance") is not None and entry["remainingBalance"] < 0 else ""),
            ("Differential",
             "₹{:,.0f}".format(entry.get("diffTotal") or 0) if entry.get("diffs") else "-",
             records.diff_breakdown(entry)),
        ]
        st.markdown(
            '<div class="drow">'
            + "".join(
                '<div class="c"><div class="k">{}</div><div class="v">{}</div>'
                '<div class="t">{}</div></div>'.format(ui.e(k), ui.e(v), ui.e(t))
                for k, v, t in cells
            )
            + "</div>",
            unsafe_allow_html=True,
        )

        shots = [
            ("start", "Start odometer", entry.get("hasStartPhoto")),
            ("end", "End odometer", entry.get("hasEndPhoto")),
            ("fuel", "Fuel receipt", entry.get("hasFuelPhoto")),
        ]
        available = [s for s in shots if s[2]]
        if available:
            cols = st.columns(len(available))
            for col, (which, label, _) in zip(cols, available):
                with col:
                    if st.button("📷 {}".format(label),
                                 key="ph_{}_{}_{}".format(date, agent, which),
                                 width="stretch"):
                        show_photo(agent, date, which, label)
        else:
            st.caption("No photos on file.")


# ------------------------------------------------------------------- render
def render() -> None:
    entries_all = records.all_entries()
    reqs = auth.load_requests()

    ui.hero(
        "Admin dashboard",
        "Everything the team filed, with photos, totals and a CSV to download.",
        ["👥 {} agents".format(len(auth.load_agents())),
         "🗄️ {} records kept".format(len(entries_all)),
         "🗓️ {}-day window".format(C.RETENTION_DAYS),
         "💾 {}".format(get_store().name)],
    )
    ui.spacer(16)

    if reqs:
        ui.note("🔔 {} PIN reset request(s) waiting: {}. Open 'Team, PINs & reset requests' below."
                .format(len(reqs), ", ".join(reqs.keys())), "warn")
        ui.spacer(10)

    # ---- controls --------------------------------------------------------
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.1, 1.1, 0.8])
        with c1:
            scope = st.radio(
                "View", ["By day", "Last {} days".format(C.RETENTION_DAYS)],
                horizontal=True, key="adm_scope", label_visibility="visible",
            )
        with c2:
            day = st.date_input(
                "Day", value=datetime.strptime(C.today_str(), "%Y-%m-%d").date(),
                key="adm_day", format="DD/MM/YYYY",
                disabled=scope != "By day",
            )
        with c3:
            ui.spacer(28)
            if st.button("🔄 Refresh", width="stretch"):
                st.rerun()

    day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else C.today_str()
    if scope == "By day":
        view = [e for e in entries_all if e.get("date") == day_str]
        scope_label = C.fmt_date(day_str)
    else:
        view = entries_all
        scope_label = "Last {} days".format(C.RETENTION_DAYS)

    t = records.totals(view)

    # ---- headline numbers ------------------------------------------------
    ui.spacer(14)
    ui.tiles([
        ("Total deals executed", "{:,}".format(int(t["deals"])), scope_label),
        ("Total amount spent", "₹{:,.0f}".format(t["spent"]), scope_label),
        ("Total differential", "₹{:,.0f}".format(t["diff"]), scope_label),
        ("Opening balance", "₹{:,.0f}".format(t["opening"]), "cash issued"),
        ("Cash remaining", "₹{:,.0f}".format(t["remaining"]), "should be in hand"),
        ("Distance covered", "{:,} km".format(int(t["distance"])), scope_label),
        ("Fuel money", "₹{:,.0f}".format(t["fuel"]), scope_label),
    ])

    # ---- who is in, who is missing ---------------------------------------
    ui.spacer(14)
    if scope == "By day":
        reported = {e.get("agent") for e in view}
        pending = [a for a in auth.load_agents() if a not in reported]
        bits = [
            ui.pill("{} submitted".format(int(t["submitted"])), "good"),
            ui.pill("{} start only".format(int(t["started"])), "warn"),
            ui.pill("{} not started".format(len(pending)), "crit" if pending else "flat"),
        ]
        st.markdown(" ".join(bits), unsafe_allow_html=True)
        if pending:
            st.caption("Waiting on: " + ", ".join(pending))
    else:
        st.markdown(
            ui.pill("{} submitted".format(int(t["submitted"])), "good") + " "
            + ui.pill("{} start only".format(int(t["started"])), "warn") + " "
            + ui.pill("{} days of data".format(len({e.get('date') for e in view})), "flat"),
            unsafe_allow_html=True,
        )

    # ---- download --------------------------------------------------------
    ui.spacer(12)
    st.download_button(
        "⬇️ Download CSV ({})".format(scope_label),
        data=export.build_csv(view),
        file_name=export.filename(day_str if scope == "By day" else "last{}days".format(C.RETENTION_DAYS)),
        mime="text/csv",
        width="stretch",
        disabled=not view,
    )

    # ---- charts ----------------------------------------------------------
    if view:
        ui.section("📊", "Breakdown", "Pick what you want to compare.")
        measures = list(charts.MEASURES.keys())
        if hasattr(st, "segmented_control"):
            measure = st.segmented_control(
                "Measure", measures, default=measures[0], key="adm_measure",
                label_visibility="collapsed",
            ) or measures[0]
        else:
            measure = st.radio("Measure", measures, horizontal=True, key="adm_measure",
                               label_visibility="collapsed")

        st.altair_chart(charts.by_agent(view, measure), use_container_width=True)
        if scope != "By day":
            ui.spacer(8)
            st.altair_chart(charts.over_time(view, measure), use_container_width=True)

    # ---- per-agent detail ------------------------------------------------
    ui.section("👥", "Agent by agent", "Tap a photo button to see the proof.")
    if not view:
        ui.note("Nothing filed for {} yet.".format(scope_label), "info")
    else:
        for entry in sorted(view, key=lambda e: (e.get("date", ""), e.get("agent", "")), reverse=True):
            _agent_card(entry, show_date=(scope != "By day"))

    # inline photo fallback for Streamlit versions without st.dialog
    inline = st.session_state.pop("photo_inline", None)
    if inline:
        with st.container(border=True):
            _render_photo(*inline)

    # ---- full table ------------------------------------------------------
    if view:
        with st.expander("📋 Full table (sortable)"):
            df = pd.DataFrame(export.rows_for(view), columns=export.COLUMNS)
            st.dataframe(df, width="stretch", hide_index=True)

    # ---- pins ------------------------------------------------------------
    ui.spacer(8)
    with st.expander("🔑 Team, PINs & reset requests" + ("  ·  {} pending".format(len(reqs)) if reqs else "")):
        _pins_panel()

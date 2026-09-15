"""The agent's screen.

Two stages, one screen each:

  morning  - Starting KM (typed) + odometer photo, nothing else
  evening  - Ending KM + photo, deals, fuel, cash spent, differentials, submit

Both KM readings need a typed number *and* a photo: the number is what gets
reported, the photo is the proof behind it.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from . import config as C
from . import images, records, ui

SLOTS = ("ph_start", "ph_end", "ph_fuel")


# ---------------------------------------------------------------- day state
def _reset_day_state() -> None:
    for k in SLOTS:
        st.session_state.pop(k, None)
        st.session_state.pop(k + "_n", None)
    st.session_state.pop("diffs", None)
    st.session_state.pop("edit_mode", None)


def _ensure_day_state(agent: str, date: str) -> None:
    key = "{}|{}".format(agent, date)
    if st.session_state.get("day_key") != key:
        st.session_state.day_key = key
        _reset_day_state()


# ------------------------------------------------------------ photo capture
def photo_picker(slot: str, title: str, hint: str, on_file: bool = False) -> Optional[str]:
    """Live-camera photo input.

    There is deliberately no upload option: the photo has to be taken here and
    now, so it is evidence of the odometer at that moment rather than a file
    that could have come from anywhere.

    Returns a freshly captured data URL, or None when nothing new was taken
    (which may still be fine - `on_file` means one is already saved).

    NEVER call st.rerun() from in here. This block sits *above* the deals, cash
    and fuel fields, and a rerun mid-script aborts before those render -
    Streamlit then discards the state of every widget it did not see, silently
    wiping what the agent had already typed below the photo. Instead the camera
    and the preview share one st.empty() slot, so taking or retaking a photo
    swaps the UI in place within the same run.
    """
    nonce = slot + "_n"
    holder = st.empty()

    def preview(data: str) -> bool:
        """Show the captured photo. Returns True if Retake was pressed."""
        with holder.container():
            st.image(images.decode(data), width="stretch")
            size, unit = images.human_size(images.approx_size(data))
            c1, c2 = st.columns([1, 1])
            with c1:
                st.markdown(
                    ui.pill("✓ Photo ready · {} {}".format(size, unit), "good"),
                    unsafe_allow_html=True,
                )
            with c2:
                return st.button("↻ Retake", key=slot + "_retake", width="stretch")

    staged = st.session_state.get(slot)
    if staged:
        if not preview(staged):
            return staged
        # Retake: drop it and fall through to the camera in this same run.
        st.session_state.pop(slot, None)
        st.session_state[nonce] = st.session_state.get(nonce, 0) + 1
        holder.empty()

    with holder.container():
        if on_file:
            st.markdown(ui.pill("✓ Photo already saved", "good"), unsafe_allow_html=True)
            ui.spacer(6)
            with st.expander("Replace this photo"):
                shot = _camera(slot, hint)
        else:
            shot = _camera(slot, hint)

    if shot:
        holder.empty()          # take the camera off screen...
        preview(shot)           # ...and put the photo in its place
        return shot
    return None


def _camera(slot: str, hint: str) -> Optional[str]:
    n = st.session_state.get(slot + "_n", 0)

    st.caption("📷 " + hint)
    shot = st.camera_input(
        "Camera", key="{}_cam_{}".format(slot, n), label_visibility="collapsed"
    )
    st.caption("The photo must be taken here - saved pictures cannot be uploaded.")

    if shot is None:
        return None
    data = images.to_data_url(shot)
    if not data:
        st.error("That photo could not be read. Please take it again.")
        return None
    st.session_state[slot] = data
    return data


# -------------------------------------------------------------- stage: start
def _start_of_day(agent: str, date: str, entry) -> None:
    ui.section("💵", "Opening balance", "The cash you are starting the day with.")
    with st.container(border=True):
        saved_ob = entry.get("openingBalance") if entry else None
        opening = st.number_input(
            "Opening balance (₹)", min_value=0.0, step=100.0,
            value=None if saved_ob is None else float(saved_ob),
            placeholder="e.g. 5000", key="in_opening",
            help="Cash in hand right now, before you spend anything today. "
                 "Enter 0 if you are not carrying any.",
        )
        if opening is not None:
            st.markdown(
                '<div class="note info">Starting with <b>₹{:,.0f}</b>. This evening you will '
                "enter what you spent, and the app works out what should be left."
                "</div>".format(opening),
                unsafe_allow_html=True,
            )

    ui.section("🌅", "Start of day", "Two things: the number on the odometer, and a photo of it.")

    with st.container(border=True):
        start_km = st.number_input(
            "Starting KM",
            min_value=0, max_value=9_999_999, step=1,
            value=int(entry["startKm"]) if entry and entry.get("startKm") is not None else None,
            placeholder="e.g. 45231",
            key="in_start_km",
            help="Type the total kilometres showing on your odometer right now.",
        )
        ui.spacer(6)
        st.markdown("**Odometer photo**")
        photo = photo_picker(
            "ph_start",
            "Starting odometer",
            "Hold steady and fill the frame with the odometer numbers.",
            on_file=bool(entry and entry.get("hasStartPhoto")),
        )

    has_photo = bool(photo) or bool(entry and entry.get("hasStartPhoto"))
    ready = opening is not None and start_km is not None and has_photo

    if not ready:
        missing = []
        if opening is None:
            missing.append("your opening balance")
        if start_km is None:
            missing.append("the Starting KM number")
        if not has_photo:
            missing.append("a photo of the odometer")
        ui.note("Still needed: " + ", ".join(missing) + ".", "warn")

    ui.spacer(8)
    if st.button(
        "✅ Save start of day", type="primary", width="stretch", disabled=not ready
    ):
        records.save_start(agent, date, start_km, st.session_state.get("ph_start"),
                           opening_balance=opening)
        st.session_state.pop("ph_start", None)
        st.toast("Start of day saved. Come back this evening!", icon="🌅")
        st.balloons()
        st.rerun()


# ---------------------------------------------------------------- diff rows
def _differentials() -> list:
    if "diffs" not in st.session_state:
        st.session_state.diffs = []
    rows = st.session_state.diffs

    ui.section("💰", "Differential collected", "Any extra amount you collected today. Skip if none.")

    with st.container(border=True):
        # Chips rather than a row of columns: they wrap to the screen instead of
        # becoming three full-width buttons on a phone.
        options = ["＋ {}".format(r) for r in C.quick_remarks()] + ["＋ Other"]
        nonce = st.session_state.get("diff_nonce", 0)
        if hasattr(st, "pills"):
            picked = st.pills("Add a row", options, selection_mode="single",
                              key="diff_add_{}".format(nonce), label_visibility="collapsed")
        else:
            picked = None
            cols = st.columns(len(options))
            for col, opt in zip(cols, options):
                with col:
                    if st.button(opt, key="q_{}_{}".format(opt, nonce), width="stretch"):
                        picked = opt
        if picked:
            remark = "" if picked.endswith("Other") else picked.replace("＋ ", "")
            rows.append({"amount": None, "remark": remark})
            st.session_state.diff_nonce = nonce + 1   # reset the chip selection
            st.rerun()

        if not rows:
            st.caption("No differential amounts yet. Use the buttons above to add one.")

        total = 0.0
        for idx, row in enumerate(list(rows)):
            c1, c2, c3, c4 = st.columns([1.0, 1.3, 1.2, 0.5])
            with c1:
                # float(), because min_value/step here are floats and Streamlit
                # rejects a widget that mixes int and float.
                saved = row.get("amount")
                amt = st.number_input(
                    "Amount (₹)", min_value=0.0, step=50.0,
                    value=None if saved is None else float(saved),
                    placeholder="0", key="d_amt_{}".format(idx),
                )
            with c2:
                did = st.text_input(
                    "Deal / Order ID", value=row.get("dealId", ""),
                    placeholder="e.g. ORD-48219", key="d_id_{}".format(idx),
                    help="The deal or order ID this amount came from.",
                )
            with c3:
                rmk = st.text_input(
                    "Remark", value=row.get("remark", ""), placeholder="who it was for",
                    key="d_rmk_{}".format(idx),
                )
            with c4:
                st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
                # Labelled, not a bare icon: on a phone this button goes
                # full-width and an unlabelled bin is ambiguous.
                if st.button("🗑 Remove", key="d_del_{}".format(idx), width="stretch",
                             help="Remove this differential row"):
                    rows.pop(idx)
                    _renumber_diff_widgets()
                    st.rerun()
            rows[idx] = {"amount": amt, "remark": rmk, "dealId": did}
            total += float(amt or 0)

        if rows:
            st.markdown(
                '<div class="note good" style="margin-top:6px">Differential total: '
                "<b>₹{:,.0f}</b></div>".format(total),
                unsafe_allow_html=True,
            )
    return rows


def _renumber_diff_widgets() -> None:
    """Row widgets are keyed by index, so drop their state when a row is removed
    - otherwise the values below the deleted row shift up by one."""
    for k in [k for k in st.session_state if k.startswith(("d_amt_", "d_rmk_", "d_id_"))]:
        st.session_state.pop(k, None)


# ---------------------------------------------------------------- stage: end
def _end_of_day(agent: str, date: str, entry) -> None:
    started_at = C.fmt_time(entry.get("dayStartAt"))
    if started_at:
        line = "🌅 Day started at {} · Starting KM {:,}".format(
            started_at, int(entry.get("startKm") or 0))
        if entry.get("openingBalance") is not None:
            line += " · Opening balance ₹{:,.0f}".format(entry["openingBalance"])
        ui.note(line, "info")
        ui.spacer(10)

    ui.section("🌇", "End of day", "Close the day: final odometer reading, then the numbers.")

    with st.container(border=True):
        end_km = st.number_input(
            "Ending KM",
            min_value=0, max_value=9_999_999, step=1,
            value=int(entry["endKm"]) if entry.get("endKm") is not None else None,
            placeholder="e.g. 45298", key="in_end_km",
            help="The total kilometres on the odometer now.",
        )

        start_km = entry.get("startKm")
        if start_km is not None and end_km is not None:
            dist = records.distance_of(start_km, end_km)
            if end_km < start_km:
                ui.note(
                    "Ending KM ({:,}) is lower than the Starting KM ({:,}). "
                    "Please check the reading.".format(int(end_km), int(start_km)),
                    "crit",
                )
            else:
                st.markdown(
                    '<div class="note good">🛣️ Distance today: <b>{:,} km</b></div>'.format(dist),
                    unsafe_allow_html=True,
                )

        ui.spacer(8)
        st.markdown("**Odometer photo**")
        photo_end = photo_picker(
            "ph_end", "Ending odometer",
            "Same as this morning - fill the frame with the numbers.",
            on_file=bool(entry.get("hasEndPhoto")),
        )

    ui.section("📦", "Work done", "What the day produced.")
    with st.container(border=True):
        deals = st.number_input(
            "Total deals done", min_value=0, max_value=999, step=1,
            value=int(entry["totalDeals"]) if entry.get("totalDeals") is not None else None,
            placeholder="0", key="in_deals",
        )

    ui.section("💵", "Cash", "Opening balance minus what you spent - the app does the maths.")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            saved_ob = entry.get("openingBalance")
            opening = st.number_input(
                "Opening balance (₹)", min_value=0.0, step=100.0,
                value=None if saved_ob is None else float(saved_ob),
                placeholder="0", key="in_opening_eve",
                help="What you started the day with. Correct it here if it was wrong.",
            )
        with c2:
            spent = st.number_input(
                "Total amount spent today (₹)", min_value=0.0, step=50.0,
                value=float(entry["spentAmount"]) if entry.get("spentAmount") is not None else None,
                placeholder="0", key="in_spent",
                help="Every rupee that went out today, fuel included if you paid cash.",
            )

        remaining = records.remaining_of(opening, spent)
        if remaining is None:
            st.caption("Enter your opening balance to see the remaining balance.")
        elif remaining < 0:
            st.markdown(
                '<div class="note crit">⚠️ Remaining balance: <b>-₹{:,.0f}</b><br>'
                "You spent ₹{:,.0f} more than the ₹{:,.0f} you started with. "
                "Check the numbers, and tell your admin if that is correct."
                "</div>".format(abs(remaining), abs(remaining), opening or 0),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="note good">💰 Remaining balance: <b>₹{:,.0f}</b>'
                '<span class="muted"> &nbsp;=&nbsp; ₹{:,.0f} opening − ₹{:,.0f} spent</span>'
                "</div>".format(remaining, opening or 0, spent or 0),
                unsafe_allow_html=True,
            )

    ui.section("⛽", "Fuel", "Optional - only if you filled up today.")
    with st.container(border=True):
        fuel = st.number_input(
            "Fuel money spent (₹)", min_value=0.0, step=50.0,
            value=float(entry["fuelAmount"]) if entry.get("fuelAmount") is not None else None,
            placeholder="0", key="in_fuel",
            help="Enter 0 if you did not fill up today.",
        )
        photo_fuel = None
        if fuel:
            st.markdown("**Fuel receipt photo**")
            photo_fuel = photo_picker(
                "ph_fuel", "Fuel receipt", "A clear shot of the receipt.",
                on_file=bool(entry.get("hasFuelPhoto")),
            )
        elif fuel == 0:
            st.caption("No fuel today - no receipt needed.")

    rows = _differentials()

    # ---- submit ----------------------------------------------------------
    # Every field has to be filled in. 0 is a perfectly good answer - what is
    # not allowed is leaving a box blank, because then nobody can tell whether
    # the agent meant zero or simply skipped it.
    has_end_photo = bool(st.session_state.get("ph_end")) or bool(entry.get("hasEndPhoto"))
    has_fuel_photo = bool(st.session_state.get("ph_fuel")) or bool(entry.get("hasFuelPhoto"))

    missing = []
    if end_km is None:
        missing.append("Ending KM")
    if not has_end_photo:
        missing.append("a photo of the odometer")
    if deals is None:
        missing.append("Total deals done (enter 0 if none)")
    if opening is None:
        missing.append("Opening balance (enter 0 if none)")
    if spent is None:
        missing.append("Total amount spent (enter 0 if none)")
    if fuel is None:
        missing.append("Fuel money (enter 0 if you did not fill up)")
    if fuel and not has_fuel_photo:
        missing.append("the fuel receipt photo")

    incomplete_diffs = [
        i + 1 for i, r in enumerate(rows)
        if r.get("amount") is None or not str(r.get("remark") or "").strip()
        or not str(r.get("dealId") or "").strip()
    ]
    if incomplete_diffs:
        missing.append("every part of differential row {}".format(
            ", ".join(str(i) for i in incomplete_diffs)))

    ready = not missing

    ui.spacer(10)
    if not ready:
        ui.note("Still needed: " + "; ".join(missing) + ".", "warn")
        ui.spacer(8)

    if st.button(
        "🚀 Submit final report", type="primary", width="stretch", disabled=not ready
    ):
        records.save_final(
            agent, date,
            end_km=end_km,
            total_deals=deals,
            fuel_amount=fuel,
            opening_balance=opening,
            spent_amount=spent,
            diffs=rows,
            photo_end=st.session_state.get("ph_end"),
            photo_fuel=st.session_state.get("ph_fuel"),
        )
        for k in ("ph_end", "ph_fuel"):
            st.session_state.pop(k, None)
        st.session_state.edit_mode = False
        st.toast("Report submitted. Thank you!", icon="🎉")
        st.balloons()
        st.rerun()


# ------------------------------------------------------------ stage: done
def _summary(agent: str, date: str, entry) -> None:
    ui.note("🎉 Your report for {} is submitted at {}. Thank you!".format(
        C.fmt_date(date), C.fmt_time(entry.get("submittedAt"))), "good")
    ui.spacer(14)

    rem = entry.get("remainingBalance")
    ui.tiles([
        ("Distance", "{:,} km".format(int(entry.get("distance") or 0)), "Start to end"),
        ("Deals done", "{:,}".format(int(entry.get("totalDeals") or 0)), "Today"),
        ("Opening balance", "₹{:,.0f}".format(entry.get("openingBalance") or 0), "Cash at start"),
        ("Spent", "₹{:,.0f}".format(entry.get("spentAmount") or 0), "During the day"),
        ("Remaining balance", "-" if rem is None else "₹{:,.0f}".format(rem),
         "Should be in hand"),
        ("Differential", "₹{:,.0f}".format(entry.get("diffTotal") or 0),
         records.diff_breakdown(entry) or "None"),
        ("Fuel", "₹{:,.0f}".format(entry.get("fuelAmount") or 0),
         C.fmt_time(entry.get("fuelAt")) or "Not filled"),
    ])

    ui.spacer(16)
    with st.container(border=True):
        st.markdown(
            '<div class="drow">'
            '<div class="c"><div class="k">Start KM</div><div class="v">{:,}</div>'
            '<div class="t">{}</div></div>'
            '<div class="c"><div class="k">End KM</div><div class="v">{:,}</div>'
            '<div class="t">{}</div></div>'
            "</div>".format(
                int(entry.get("startKm") or 0), C.fmt_time(entry.get("startKmAt")) or "-",
                int(entry.get("endKm") or 0), C.fmt_time(entry.get("endKmAt")) or "-",
            ),
            unsafe_allow_html=True,
        )

    ui.spacer(14)
    if st.button("✏️ Edit my report", width="stretch"):
        st.session_state.edit_mode = True
        st.rerun()


# ------------------------------------------------------------------ render
def render() -> None:
    agent = st.session_state.agent
    date = C.today_str()
    _ensure_day_state(agent, date)

    entry = records.load(agent, date)
    completed = bool(entry and entry.get("status") == "completed")
    started = entry is not None

    hour = C.local_now().hour
    greet = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
    status = "Submitted" if completed else ("Day started" if started else "Not started yet")
    ui.hero(
        "{}, {} 👋".format(greet, agent),
        "Your daily report for {}".format(C.fmt_date(date)),
        ["🗓️ {}".format(C.fmt_date(date)), "📍 {}".format(status)],
    )
    ui.spacer(16)

    ui.stepper(3 if completed else (2 if started else 1), done_final=completed)
    ui.spacer(10)

    # Prefill the differential rows once, from what is already saved.
    if started and "diffs" not in st.session_state:
        st.session_state.diffs = [dict(d) for d in (entry.get("diffs") or [])]

    if completed and not st.session_state.get("edit_mode"):
        _summary(agent, date, entry)
    elif started:
        _end_of_day(agent, date, entry)
    else:
        _start_of_day(agent, date, entry)

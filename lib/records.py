"""The day record: shape, read/write, and the roll-ups the admin view needs.

One record per agent per day. The day happens in two stages:

    morning  -> status "started"    (Starting KM number + photo only)
    evening  -> status "completed"  (everything else + submitted timestamp)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import config as C
from .storage import get_store


def _num(v) -> Optional[float]:
    """Anything -> float, or None. Blank inputs must stay None, not 0."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None  # reject NaN/inf


def _int(v) -> Optional[int]:
    f = _num(v)
    return None if f is None else int(round(f))


def blank(agent: str, date: str) -> Dict[str, Any]:
    return {
        "agent": agent,
        "date": date,
        "status": "started",
        "startKm": None,
        "startKmAt": None,
        "dayStartAt": None,
        "endKm": None,
        "endKmAt": None,
        "distance": None,
        "totalDeals": None,
        "fuelAmount": None,
        "fuelAt": None,

        # Cash: the float handed out in the morning, what went out during the
        # day, and what should still be in hand. remainingBalance is derived,
        # never typed.
        "openingBalance": None,
        "spentAmount": None,
        "remainingBalance": None,
        "diffs": [],
        "diffTotal": 0,
        "hasStartPhoto": False,
        "hasEndPhoto": False,
        "hasFuelPhoto": False,
        "submittedAt": None,
    }


def load(agent: str, date: str) -> Optional[Dict[str, Any]]:
    entry = get_store().get_entry(date, agent)
    if not entry:
        return None
    base = blank(agent, date)
    base.update(entry)
    base["diffs"] = [d for d in (base.get("diffs") or []) if isinstance(d, dict)]
    return base


def remaining_of(opening, spent) -> Optional[float]:
    """What should still be in hand. None until an opening balance exists.

    Deliberately allowed to go negative - an agent who spent more than their
    float used their own money, and hiding that would lose real information.
    """
    o = _num(opening)
    if o is None:
        return None
    return float(o) - float(_num(spent) or 0.0)


def distance_of(start_km, end_km) -> Optional[int]:
    s, e = _num(start_km), _num(end_km)
    if s is None or e is None:
        return None
    return max(0, int(round(e - s)))


def clean_diffs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop empty rows, coerce amounts, trim remarks and deal IDs.

    `amount` is always a float, never an int: it is fed straight back into a
    st.number_input whose min_value/step are floats, and Streamlit refuses a
    mix of int and float on one widget (StreamlitMixedNumericTypesError).
    """
    out = []
    for r in rows or []:
        amount = float(_num(r.get("amount")) or 0.0)
        remark = str(r.get("remark") or "").strip()[:120]
        deal_id = str(r.get("dealId") or "").strip()[:60]
        if amount or remark or deal_id:
            out.append({"amount": amount, "remark": remark, "dealId": deal_id})
    return out[:50]


def save_start(
    agent: str, date: str, start_km, photo: Optional[str], opening_balance=None
) -> Dict[str, Any]:
    """Morning save. Creates the record, or tops up an existing one."""
    store = get_store()
    entry = load(agent, date) or blank(agent, date)

    if opening_balance not in (None, ""):
        entry["openingBalance"] = _num(opening_balance)
    entry["remainingBalance"] = remaining_of(entry.get("openingBalance"), entry.get("spentAmount"))
    entry["startKm"] = _int(start_km)
    entry["dayStartAt"] = entry.get("dayStartAt") or C.now_iso()
    if photo:
        entry["startKmAt"] = C.now_iso()
        entry["hasStartPhoto"] = True
        store.put_photo(date, agent, "start", photo)
    entry["distance"] = distance_of(entry["startKm"], entry.get("endKm"))
    if entry.get("status") != "completed":
        entry["status"] = "started"

    store.put_entry(entry)
    return entry


def save_final(
    agent: str,
    date: str,
    *,
    start_km=None,
    end_km=None,
    total_deals=None,
    fuel_amount=None,
    opening_balance=None,
    spent_amount=None,
    diffs: Optional[List[Dict[str, Any]]] = None,
    photo_end: Optional[str] = None,
    photo_fuel: Optional[str] = None,
) -> Dict[str, Any]:
    """Evening submit. Photos already on file are left untouched when the
    matching argument is None, which is how the morning photo survives."""
    store = get_store()
    entry = load(agent, date) or blank(agent, date)

    if start_km not in (None, ""):
        entry["startKm"] = _int(start_km)
    entry["endKm"] = _int(end_km)
    entry["distance"] = distance_of(entry.get("startKm"), entry.get("endKm"))
    entry["totalDeals"] = _int(total_deals)
    entry["fuelAmount"] = _num(fuel_amount)
    if opening_balance not in (None, ""):
        entry["openingBalance"] = _num(opening_balance)
    entry["spentAmount"] = _num(spent_amount)
    entry["remainingBalance"] = remaining_of(entry.get("openingBalance"), entry.get("spentAmount"))

    rows = clean_diffs(diffs or [])
    entry["diffs"] = rows
    entry["diffTotal"] = sum(r["amount"] for r in rows)

    if photo_end:
        entry["endKmAt"] = C.now_iso()
        entry["hasEndPhoto"] = True
        store.put_photo(date, agent, "end", photo_end)
    if photo_fuel:
        entry["fuelAt"] = C.now_iso()
        entry["hasFuelPhoto"] = True
        store.put_photo(date, agent, "fuel", photo_fuel)

    entry["dayStartAt"] = entry.get("dayStartAt") or C.now_iso()
    entry["status"] = "completed"
    entry["submittedAt"] = C.now_iso()

    store.put_entry(entry)
    return entry


def photo(agent: str, date: str, which: str) -> Optional[str]:
    return get_store().get_photo(date, agent, which)


# ------------------------------------------------------------- admin reads --
def all_entries(purge: bool = True) -> List[Dict[str, Any]]:
    """Every entry inside the retention window, newest day first.

    The purge runs here, on admin load, which keeps the store trimmed without
    needing a scheduler.
    """
    store = get_store()
    if purge:
        try:
            store.purge_before(C.cutoff_str())
        except Exception as exc:
            print("purge skipped:", exc)

    rows = [e for e in store.list_entries() if e and e.get("date")]
    cut = C.cutoff_str()
    rows = [e for e in rows if str(e["date"]) >= cut]
    rows.sort(key=lambda e: (e.get("date", ""), str(e.get("agent", ""))), reverse=True)
    return rows


def totals(entries: List[Dict[str, Any]]) -> Dict[str, float]:
    def s(field):
        return sum(_num(e.get(field)) or 0 for e in entries)

    return {
        "deals": s("totalDeals"),
        "spent": s("spentAmount"),
        "diff": s("diffTotal"),
        "distance": s("distance"),
        "fuel": s("fuelAmount"),
        "opening": s("openingBalance"),
        "remaining": s("remainingBalance"),
        "submitted": sum(1 for e in entries if e.get("status") == "completed"),
        "started": sum(1 for e in entries if e.get("status") != "completed"),
    }


def diff_breakdown(entry: Dict[str, Any]) -> str:
    """'client A 500 (ORD-9912) + client B 300' - the readable summary."""
    parts = []
    for d in entry.get("diffs") or []:
        amt = _num(d.get("amount")) or 0
        remark = str(d.get("remark") or "").strip()
        deal_id = str(d.get("dealId") or "").strip()
        piece = "{} {:g}".format(remark, amt) if remark else "{:g}".format(amt)
        if deal_id:
            piece += " ({})".format(deal_id)
        parts.append(piece)
    return " + ".join(parts)


def diff_ids(entry: Dict[str, Any]) -> str:
    """Just the deal / order IDs, comma separated - easy to filter in Excel."""
    ids = [str(d.get("dealId") or "").strip() for d in entry.get("diffs") or []]
    return ", ".join(i for i in ids if i)

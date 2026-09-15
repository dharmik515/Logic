"""CSV export of whatever the admin is currently looking at.

Shape: one **Day** row per agent per day carrying all of that day's numbers,
followed by one **Differential** row for each differential they collected.
Differentials get a row each rather than being crammed into a single cell, so
every amount, deal ID and remark lands in its own column and Excel can sort and
filter on them.

    Row Type      Date        Agent | Differential | Amount | Deal ID   | Remark
    Day           2026-09-14  Asha  | 4770         |        |           |
    Differential  2026-09-14  Asha  |              | 278    | ORD-10023 | client A
    Differential  2026-09-14  Asha  |              | 3746   | ORD-10024 | client B

A UTF-8 BOM is prepended so Excel opens it with the right encoding.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List

from . import config as C
from . import records

COLUMNS = [
    "Row Type", "Date", "Agent", "Status", "Day Start Time",
    "Starting KM", "Start KM Time", "Ending KM", "End KM Time", "Distance KM",
    "Total Deals Done", "Fuel Money", "Fuel Time",
    "Opening Balance", "Amount Spent (day)", "Remaining Balance",
    "Differential Collected",
    "Differential Amount", "Deal / Order ID", "Differential Remark",
    "Start Photo", "End Photo", "Fuel Receipt", "Submitted At",
]
_IDX = {name: i for i, name in enumerate(COLUMNS)}


def _row(values: Dict[str, Any]) -> List[Any]:
    """Build a full-width row from just the columns you actually have.

    Everything else stays None, which csv.writer writes as an empty cell and
    pandas reads as a real gap - so numeric columns keep a numeric dtype
    instead of collapsing to `object`, which Arrow then refuses to serialise.
    Addressing cells by name also means adding a column never shifts a value
    into the wrong slot.
    """
    out: List[Any] = [None] * len(COLUMNS)
    for key, value in values.items():
        out[_IDX[key]] = value
    return out


def _v(x):
    return None if x is None or x == "" else x


def _yn(b) -> str:
    return "Yes" if b else "No"


def rows_for(entries: List[Dict[str, Any]]) -> List[List[Any]]:
    out: List[List[Any]] = []
    for e in entries:
        date, agent = e.get("date", ""), e.get("agent", "")

        out.append(_row({
            "Row Type": "Day",
            "Date": date,
            "Agent": agent,
            "Status": "Submitted" if e.get("status") == "completed" else "Start only",
            "Day Start Time": C.fmt_time(e.get("dayStartAt")),
            "Starting KM": _v(e.get("startKm")),
            "Start KM Time": C.fmt_time(e.get("startKmAt")),
            "Ending KM": _v(e.get("endKm")),
            "End KM Time": C.fmt_time(e.get("endKmAt")),
            "Distance KM": _v(e.get("distance")),
            "Total Deals Done": _v(e.get("totalDeals")),
            "Fuel Money": _v(e.get("fuelAmount")),
            "Fuel Time": C.fmt_time(e.get("fuelAt")),
            "Opening Balance": _v(e.get("openingBalance")),
            "Amount Spent (day)": _v(e.get("spentAmount")),
            "Remaining Balance": _v(e.get("remainingBalance")),
            "Differential Collected": _v(e.get("diffTotal")) or 0,
            "Start Photo": _yn(e.get("hasStartPhoto")),
            "End Photo": _yn(e.get("hasEndPhoto")),
            "Fuel Receipt": _yn(e.get("hasFuelPhoto")),
            "Submitted At": e.get("submittedAt") or "",
        }))

        # One row per differential, directly beneath its day.
        for d in e.get("diffs") or []:
            out.append(_row({
                "Row Type": "Differential",
                "Date": date,
                "Agent": agent,
                "Differential Amount": _v(d.get("amount")),
                "Deal / Order ID": str(d.get("dealId") or ""),
                "Differential Remark": str(d.get("remark") or ""),
            }))
    return out


def build_csv(entries: List[Dict[str, Any]]) -> bytes:
    t = records.totals(entries)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for row in rows_for(entries):
        w.writerow(row)

    w.writerow([])
    w.writerow(_row({
        "Row Type": "TOTAL",
        "Date": "{} day-records".format(len(entries)),
        "Distance KM": int(t["distance"]),
        "Total Deals Done": int(t["deals"]),
        "Fuel Money": t["fuel"],
        "Opening Balance": t["opening"],
        "Amount Spent (day)": t["spent"],
        "Remaining Balance": t["remaining"],
        "Differential Collected": t["diff"],
    }))
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def filename(scope: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in scope)
    return "daily-agent-report_{}.csv".format(safe)

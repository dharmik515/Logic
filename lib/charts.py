"""Admin charts.

Two forms, one measure at a time - picked by the measure selector above them:

* **Per agent** - magnitude compared across identities -> horizontal bars, sorted
  by value, one hue (a single series needs no legend; the title names it), with
  direct value labels so the numbers are readable without hovering.
* **Over time**  - change across days -> a single 2px line with 60px-ish markers.

Deliberately never a dual-axis chart: deals, kilometres and rupees live on
different scales, so they get their own view rather than a second y-axis.
Palette, gridlines and ink come from the reference data-viz palette, on the
light chart surface the app pins.
"""
from __future__ import annotations

from typing import List

import altair as alt
import pandas as pd

SURFACE = "#fcfcfb"
SERIES = "#2a78d6"      # categorical slot 1 / sequential blue 450
SERIES_SOFT = "#9ec5f4"  # blue 200
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# label -> (record field, unit prefix, unit suffix)
MEASURES = {
    "Deals": ("totalDeals", "", ""),
    "Distance": ("distance", "", " km"),
    "Amount spent": ("spentAmount", "₹", ""),
    "Differential": ("diffTotal", "₹", ""),
    "Opening balance": ("openingBalance", "₹", ""),
    "Remaining": ("remainingBalance", "₹", ""),
    "Fuel": ("fuelAmount", "₹", ""),
}


def _base(chart: alt.Chart) -> alt.Chart:
    return (
        chart.configure_view(strokeWidth=0, fill=SURFACE)
        .configure_axis(
            grid=True,
            gridColor=GRID,
            gridWidth=1,
            domainColor=AXIS,
            tickColor=AXIS,
            labelColor=MUTED,
            titleColor=MUTED,
            labelFontSize=12,
            titleFontSize=11,
            titleFontWeight="normal",
        )
        .configure_axisY(grid=False, domain=False, ticks=False, labelColor=INK, labelFontWeight=600)
        .configure_title(fontSize=13, color=INK, anchor="start", offset=8)
    )


def by_agent(entries: List[dict], measure: str) -> alt.Chart:
    """Horizontal bars, one per agent, sorted high to low."""
    field, pre, suf = MEASURES[measure]
    rows = [
        {"Agent": e.get("agent", "?"), "Value": float(e.get(field) or 0)}
        for e in entries
        if e.get("agent")
    ]
    df = pd.DataFrame(rows or [{"Agent": "-", "Value": 0.0}])
    df = df.groupby("Agent", as_index=False)["Value"].sum()
    df = df.sort_values("Value", ascending=False)
    df["Label"] = df["Value"].map(lambda v: "{}{:,.0f}{}".format(pre, v, suf))

    order = df["Agent"].tolist()
    height = max(150, 34 * len(order))

    base = alt.Chart(df).encode(
        y=alt.Y("Agent:N", sort=order, title=None),
        tooltip=[
            alt.Tooltip("Agent:N"),
            alt.Tooltip("Value:Q", title=measure, format=",.0f"),
        ],
    )
    bars = base.mark_bar(cornerRadiusEnd=4, height=16, color=SERIES).encode(
        # Counts are whole things - never label an axis 0.5 deals. tickCount
        # keeps the grid recessive instead of one line per unit.
        x=alt.X("Value:Q", title=None,
                axis=alt.Axis(labelFlush=True, format=",.0f", tickMinStep=1, tickCount=5))
    )
    labels = base.mark_text(align="left", dx=7, fontSize=12, color=MUTED, fontWeight=600).encode(
        x=alt.X("Value:Q"), text="Label:N"
    )

    return _base(
        (bars + labels)
        .properties(height=height, title="{} by agent".format(measure), padding={"right": 44})
    )


def over_time(entries: List[dict], measure: str) -> alt.Chart:
    """One line: the team's daily total for the selected measure."""
    field, pre, suf = MEASURES[measure]
    rows = [
        {"Date": str(e.get("date")), "Value": float(e.get(field) or 0)}
        for e in entries
        if e.get("date")
    ]
    df = pd.DataFrame(rows or [{"Date": "", "Value": 0.0}])
    df = df.groupby("Date", as_index=False)["Value"].sum().sort_values("Date")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    if df.empty:
        df = pd.DataFrame({"Date": pd.to_datetime([]), "Value": []})

    base = alt.Chart(df).encode(
        x=alt.X("Date:T", title=None, axis=alt.Axis(format="%d %b", labelAngle=0, tickCount=6)),
        y=alt.Y("Value:Q", title=None,
                axis=alt.Axis(format=",.0f", tickMinStep=1, tickCount=5)),
        tooltip=[
            alt.Tooltip("Date:T", title="Day", format="%d %b %Y"),
            alt.Tooltip("Value:Q", title=measure, format=",.0f"),
        ],
    )
    area = base.mark_area(color=SERIES_SOFT, opacity=0.28, line=False)
    line = base.mark_line(color=SERIES, strokeWidth=2, interpolate="monotone")
    dots = base.mark_circle(color=SERIES, size=64, stroke=SURFACE, strokeWidth=2)

    return _base(
        (area + line + dots).properties(
            height=230, title="{} per day (team total)".format(measure)
        )
    )

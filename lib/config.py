"""Central configuration: roster, PINs, retention, timezone.

Every value can be overridden from `.streamlit/secrets.toml` (on Streamlit
Community Cloud: App settings -> Secrets) or from an environment variable.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

# --------------------------------------------------------------------- roster
# No names live in this repository. Real people's names are personal data and
# this source is public, so the team comes from configuration instead:
#
#   AGENTS = "Asha, Ravi, Meera"        in .streamlit/secrets.toml
#
# It is only a *seed*. After the first run the live roster lives in the store
# and is edited from the admin panel - read it with auth.load_agents(). With no
# seed configured the app starts with an empty team and the admin adds everyone
# from the dashboard, which is the recommended way to set it up.
def _csv_secret(key, fallback=()):
    raw = _secret(key, None)
    if raw is None:
        return list(fallback)
    if isinstance(raw, (list, tuple)):
        names = list(raw)
    else:
        names = str(raw).split(",")
    return [str(n).strip() for n in names if str(n).strip()]


def default_agents():
    """Seed roster from configuration. Empty unless AGENTS is set."""
    return _csv_secret("AGENTS")


def quick_remarks():
    """Optional quick-pick labels on the differential rows, e.g. your regular
    clients. Configure with QUICK_REMARKS = "Acme, Globex"; empty by default so
    no commercial relationship is disclosed by this repository."""
    return _csv_secret("QUICK_REMARKS")

APP_TITLE = "Daily Agent Report"
APP_ICON = "🚗"

# ----------------------------------------------------------------- retention
RETENTION_DAYS = 30

# ------------------------------------------------------------------- photos
MAX_IMAGE_EDGE = 1400      # longest side, px, after downscaling
JPEG_QUALITY = 72          # good enough to read an odometer, small enough to store
MAX_PHOTO_BYTES = 4_000_000


def _secret(key: str, default=None):
    """secrets.toml -> environment -> default, without exploding when there is
    no secrets file at all (the normal case on a laptop)."""
    try:
        import streamlit as st

        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


DEFAULT_ADMIN_PIN = "24668"
DEFAULT_AGENT_PIN = "12345"


def admin_pin() -> str:
    return str(_secret("ADMIN_PIN", DEFAULT_ADMIN_PIN))


def using_default_admin_pin() -> bool:
    """True while the dashboard is still protected by the PIN published in this
    (public) source. Surfaced loudly in the admin view."""
    return str(admin_pin()) == DEFAULT_ADMIN_PIN


def default_agent_pin() -> str:
    return str(_secret("AGENT_PIN", DEFAULT_AGENT_PIN))


def timezone_name() -> str:
    return str(_secret("APP_TIMEZONE", "Asia/Kolkata"))


def local_now() -> datetime:
    """Now, in the team's timezone. Falls back to machine local time if the
    tz database is unavailable (Windows without `tzdata`)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(timezone_name()))
    except Exception:
        return datetime.now().astimezone()


def today_str() -> str:
    return local_now().strftime("%Y-%m-%d")


def cutoff_str(days: int = RETENTION_DAYS) -> str:
    return (local_now() - timedelta(days=days)).strftime("%Y-%m-%d")


def now_iso() -> str:
    return local_now().isoformat(timespec="seconds")


def fmt_time(iso: str) -> str:
    """ISO timestamp -> '18:42'. Empty string when missing or unparseable."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(str(iso)).strftime("%H:%M")
    except Exception:
        return ""


def fmt_date(ymd: str) -> str:
    """'2026-09-14' -> '14 Sep 2026'."""
    if not ymd:
        return ""
    try:
        return datetime.strptime(str(ymd)[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except Exception:
        return str(ymd)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

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


DEFAULT_AGENTS = [
    "Sultan", "Ifham", "Athar", "Neshar", "Aslam", "Ali",
    "Mirza", "Mudassir", "Abdulla", "Thalla", "Ibrahim",
]

DEFAULT_QUICK_REMARKS = ["Samsung", "Amazon"]


def default_agents():
    """Seed roster. Override per-deployment with AGENTS = "Asha, Ravi"."""
    return _csv_secret("AGENTS", DEFAULT_AGENTS)


def quick_remarks():
    """Quick-pick labels on the differential rows. Override with
    QUICK_REMARKS = "Acme, Globex"."""
    return _csv_secret("QUICK_REMARKS", DEFAULT_QUICK_REMARKS)


def agent_pins():
    """Per-agent starting PINs, supplied as a secret and never written here:

        AGENT_PINS = "Sultan:4821, Ifham:7390"

    Anything not listed gets a random PIN the admin can read off the Team
    panel. No PIN belongs in this file - the repository is public.
    """
    out = {}
    for pair in _csv_secret("AGENT_PINS"):
        if ":" in pair:
            name, _, pin = pair.partition(":")
            name, pin = name.strip(), pin.strip()
            if name and pin:
                out[name] = pin
    return out

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


# No PIN is written in this file. A password committed to a public repository
# is not a password - so there is no fallback, and the app fails closed: until
# ADMIN_PIN is configured, the dashboard simply cannot be opened by anyone.
def admin_pin():
    """The configured admin PIN, or None when nobody has set one."""
    pin = _secret("ADMIN_PIN", None)
    pin = str(pin).strip() if pin is not None else ""
    return pin or None


def admin_configured() -> bool:
    return admin_pin() is not None


def default_agent_pin():
    """Starting PIN for an agent seeded from AGENTS.

    None means "make one up per agent" - see auth.load_pins(). Again, no
    shipped default, because a published starting PIN is a published password.
    """
    pin = _secret("AGENT_PIN", None)
    pin = str(pin).strip() if pin is not None else ""
    return pin or None


def random_pin() -> str:
    """A 6-digit PIN the admin can read off the Team panel and pass on."""
    import secrets

    return "".join(secrets.choice("0123456789") for _ in range(6))


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

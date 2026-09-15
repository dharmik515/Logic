"""Login, per-agent PINs, and the admin-approved forgot-PIN flow.

PINs are stored in plain text on purpose: the admin has to be able to read an
agent's PIN back to them over the phone, which is the whole point of the
"forgot my PIN" workflow here. This is light gating for a field log shared over
WhatsApp - it is not authentication. See README, Security.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from . import config as C
from .storage import get_store

PIN_RE = re.compile(r"^\d{4,6}$")

PINS_KEY = "agentpins"
REQS_KEY = "resetrequests"
ROSTER_KEY = "roster"

# A name is used as a record key, so keep it plain and bounded.
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,29}$")


def load_agents() -> List[str]:
    """The live roster - the source of truth once the app has run once.

    Seeded from the AGENTS setting the first time, then owned by the admin
    panel. An empty roster is a valid state: the admin simply adds the team
    from the dashboard.
    """
    store = get_store()
    roster = store.get_config(ROSTER_KEY)
    if isinstance(roster, list):
        return [str(a) for a in roster]
    seed = C.default_agents()
    store.set_config(ROSTER_KEY, seed)
    return list(seed)


def save_agents(roster: List[str]) -> None:
    get_store().set_config(ROSTER_KEY, list(roster))


def add_agent(name: str, pin: str) -> Tuple[bool, str]:
    """Add a person to the team, with their starting PIN."""
    name = " ".join(str(name or "").split())
    pin = str(pin or "").strip()
    if not NAME_RE.match(name):
        return False, "Name must be 2-30 letters (spaces, . ' - allowed)."
    if not PIN_RE.match(pin):
        return False, "PIN must be 4 to 6 digits."

    roster = load_agents()
    if any(a.lower() == name.lower() for a in roster):
        return False, "{} is already on the team.".format(name)

    roster.append(name)
    save_agents(roster)

    pins = load_pins()
    pins[name] = pin
    get_store().set_config(PINS_KEY, pins)
    return True, "{} added. They can log in with PIN {}.".format(name, pin)


def remove_agent(name: str) -> Tuple[bool, str]:
    """Take someone off the team.

    Their past reports are deliberately left in place - they are part of the
    30-day record and still show on the dashboard for days already filed.
    Only the ability to log in goes away.
    """
    roster = load_agents()
    if name not in roster:
        return False, "{} is not on the team.".format(name)

    save_agents([a for a in roster if a != name])

    store = get_store()
    pins = load_pins()
    if pins.pop(name, None) is not None:
        store.set_config(PINS_KEY, pins)
    reqs = load_requests()
    if reqs.pop(name, None) is not None:
        save_requests(reqs)
    return True, "{} removed. Their past reports are kept.".format(name)


def load_pins() -> Dict[str, str]:
    """The agent -> PIN map, seeding any agent who does not have one yet.

    Only *missing* agents are seeded, so changing AGENT_PIN later never
    rewrites an agent who already has a PIN - change those in Agent PINs.
    """
    store = get_store()
    pins = store.get_config(PINS_KEY) or {}
    if not isinstance(pins, dict):
        pins = {}
    changed = False
    default = C.default_agent_pin()
    per_agent = C.agent_pins()          # AGENT_PINS = "Sultan:4821, Ifham:7390"
    for a in load_agents():
        if not pins.get(a):
            # Order: the PIN set for this agent in secrets, then a shared
            # AGENT_PIN, then a random one. Never a value from this source
            # file - the repository is public, so a PIN in it is published.
            pins[a] = per_agent.get(a) or default or C.random_pin()
            changed = True
    if changed:
        store.set_config(PINS_KEY, pins)
    return pins


def load_requests() -> Dict[str, Dict[str, Any]]:
    reqs = get_store().get_config(REQS_KEY) or {}
    return reqs if isinstance(reqs, dict) else {}


def save_requests(reqs: Dict[str, Dict[str, Any]]) -> None:
    get_store().set_config(REQS_KEY, reqs)


# ------------------------------------------------------------------- login --
def check_admin(pin: str) -> bool:
    """Fail closed: with no ADMIN_PIN configured, nothing opens the dashboard.

    Note the `configured is None` guard - without it an unset PIN would compare
    equal to an empty submission and let anyone straight in.
    """
    configured = C.admin_pin()
    if configured is None:
        return False
    return str(pin or "").strip() == str(configured)


def check_agent(agent: str, pin: str) -> bool:
    if agent not in load_agents():
        return False
    return str(pin or "").strip() == str(load_pins().get(agent, ""))


# --------------------------------------------------------------- admin ops --
def set_pin(agent: str, pin: str) -> Tuple[bool, str]:
    """Admin sets a PIN directly. Also clears any pending request for them."""
    pin = str(pin or "").strip()
    if agent not in load_agents():
        return False, "Unknown agent."
    if not PIN_RE.match(pin):
        return False, "PIN must be 4 to 6 digits."

    store = get_store()
    pins = load_pins()
    pins[agent] = pin
    store.set_config(PINS_KEY, pins)

    reqs = load_requests()
    if agent in reqs:
        reqs.pop(agent)
        save_requests(reqs)
    return True, "PIN updated for {}.".format(agent)


def approve_request(agent: str) -> Tuple[bool, str]:
    reqs = load_requests()
    req = reqs.get(agent)
    if not req:
        return False, "No pending request."
    ok, msg = set_pin(agent, str(req.get("requestedPin", "")))
    return ok, ("Approved - {} can now log in with their new PIN.".format(agent) if ok else msg)


def reject_request(agent: str) -> Tuple[bool, str]:
    reqs = load_requests()
    if agent not in reqs:
        return False, "No pending request."
    reqs.pop(agent)
    save_requests(reqs)
    return True, "Request from {} rejected.".format(agent)


# --------------------------------------------------------------- agent ops --
def request_reset(agent: str, requested_pin: str) -> Tuple[bool, str]:
    """Agent asks for a new PIN. Nothing changes until the admin approves."""
    requested_pin = str(requested_pin or "").strip()
    if agent not in load_agents():
        return False, "Please pick your name first."
    if not PIN_RE.match(requested_pin):
        return False, "Your new PIN must be 4 to 6 digits."

    reqs = load_requests()
    reqs[agent] = {
        "requestedPin": requested_pin,
        "at": C.now_iso(),
        "status": "pending",
    }
    save_requests(reqs)
    return True, "Request sent. Ask your admin to approve it, then log in with your new PIN."

"""Login, per-agent PINs, and the admin-approved forgot-PIN flow.

No PIN is ever stored. Everything written here is a salted PBKDF2 hash (see
lib/security.py), so a leaked database yields nothing anyone can log in with,
and the admin cannot read a PIN back to an agent - nobody can. Failed logins
are counted and lock a name out, which is what actually defeats guessing at
this PIN length.

With LOCK_PIN_CHANGES set, the roster and the PINs belong to the backend: this
module refuses every write and re-applies what the secrets say instead.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Tuple

from . import config as C
from . import security
from .storage import get_store

PIN_RE = re.compile(r"^\d{4,6}$")

PINS_KEY = "agentpins"
REQS_KEY = "resetrequests"
ROSTER_KEY = "roster"
ATTEMPTS_KEY = "loginattempts"

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
    if isinstance(roster, list) and roster:
        return [str(a) for a in roster]

    # An *empty* stored roster counts as "never seeded", not as a deliberate
    # empty team. Otherwise a deployment that first started with no roster
    # configured would stay empty forever, and the names added to config.py
    # afterwards would never appear. Removing everybody by hand and wanting it
    # to stick is not a real use case; getting your team back is.
    seed = C.default_agents()
    store.set_config(ROSTER_KEY, seed)
    return list(seed)


def save_agents(roster: List[str]) -> None:
    get_store().set_config(ROSTER_KEY, list(roster))


def add_agent(name: str, pin: str) -> Tuple[bool, str]:
    """Add a person to the team, with their starting PIN."""
    if C.pins_locked():
        return False, "The roster is locked to the backend. Edit AGENTS in the app's secrets and reboot."
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
    pins[name] = security.hash_pin(pin)      # never the PIN itself
    get_store().set_config(PINS_KEY, pins)
    return True, "{} added. They can log in with PIN {}.".format(name, pin)


def remove_agent(name: str) -> Tuple[bool, str]:
    """Take someone off the team.

    Their past reports are deliberately left in place - they are part of the
    30-day record and still show on the dashboard for days already filed.
    Only the ability to log in goes away.
    """
    if C.pins_locked():
        return False, "The roster is locked to the backend. Edit AGENTS in the app's secrets and reboot."
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

    if C.pins_locked():
        # Backend owns the PINs: re-apply what secrets say on every load, so a
        # change there takes effect on reboot and nothing set through the UI
        # can survive. Only re-hash when the PIN actually changed, otherwise
        # the salt would differ every run and churn the database.
        for a in load_agents():
            want = per_agent.get(a) or default
            if want and not security.verify_pin(want, pins.get(a, "")):
                pins[a] = security.hash_pin(want)
                changed = True
        if changed:
            store.set_config(PINS_KEY, pins)
        return pins

    for a in load_agents():
        if not pins.get(a):
            # Order: the PIN set for this agent in secrets, then a shared
            # AGENT_PIN, then a random one. Never a value from this source
            # file - the repository is public, so a PIN in it is published.
            pin = per_agent.get(a) or default or C.random_pin()
            pins[a] = security.hash_pin(pin)
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
def _attempts() -> Dict[str, Any]:
    rec = get_store().get_config(ATTEMPTS_KEY) or {}
    return rec if isinstance(rec, dict) else {}


def locked_out(who: str) -> Tuple[bool, int]:
    """(locked, seconds left) - a short lockout is what actually defeats
    guessing, since a 4-digit PIN is only 10,000 possibilities."""
    return security.too_many_attempts(_attempts().get(who), time.time())


def _record_failure(who: str) -> None:
    all_rec = _attempts()
    all_rec[who] = security.register_failure(all_rec.get(who), time.time())
    get_store().set_config(ATTEMPTS_KEY, all_rec)


def _record_success(who: str) -> None:
    all_rec = _attempts()
    if all_rec.pop(who, None) is not None:
        get_store().set_config(ATTEMPTS_KEY, all_rec)


def check_admin(pin: str) -> bool:
    """Fail closed: with nothing configured, nothing opens the dashboard.

    Note the `is None` guard - without it an unconfigured PIN would compare
    equal to an empty submission and let anyone straight in.
    """
    locked, _ = locked_out("admin")
    if locked:
        return False

    stored = C.admin_secret()
    if stored is None:
        return False
    if security.verify_pin(str(pin or "").strip(), stored):
        _record_success("admin")
        return True
    _record_failure("admin")
    return False


def check_agent(agent: str, pin: str) -> bool:
    if agent not in load_agents():
        return False
    locked, _ = locked_out(agent)
    if locked:
        return False

    pins = load_pins()
    stored = pins.get(agent, "")
    if not security.verify_pin(str(pin or "").strip(), stored):
        _record_failure(agent)
        return False

    # A database written before hashing existed holds plaintext; quietly
    # upgrade it now that we have the PIN in hand and know it is correct.
    if not security.is_hash(stored):
        pins[agent] = security.hash_pin(str(pin or "").strip())
        get_store().set_config(PINS_KEY, pins)
    _record_success(agent)
    return True


# --------------------------------------------------------------- admin ops --
def set_pin(agent: str, pin: str) -> Tuple[bool, str]:
    """Admin sets a PIN directly. Also clears any pending request for them."""
    if C.pins_locked():
        return False, "PIN changes are locked to the backend. Edit AGENT_PINS in the app's secrets and reboot."
    pin = str(pin or "").strip()
    if agent not in load_agents():
        return False, "Unknown agent."
    if not PIN_RE.match(pin):
        return False, "PIN must be 4 to 6 digits."

    store = get_store()
    pins = load_pins()
    pins[agent] = security.hash_pin(pin)
    store.set_config(PINS_KEY, pins)
    _record_success(agent)          # a deliberate reset clears any lockout

    reqs = load_requests()
    if agent in reqs:
        reqs.pop(agent)
        save_requests(reqs)
    return True, "PIN updated for {}.".format(agent)


def approve_request(agent: str) -> Tuple[bool, str]:
    if C.pins_locked():
        return False, "PIN changes are locked to the backend - update AGENT_PINS in secrets."
    reqs = load_requests()
    req = reqs.get(agent)
    if not req:
        return False, "No pending request."
    # The requested PIN was hashed the moment it was submitted, so approving
    # moves a hash across - the admin never learns what the agent chose.
    stored = req.get("requestedPinHash") or ""
    if not stored:
        return False, "That request predates this version - ask them to send it again."

    pins = load_pins()
    pins[agent] = stored
    get_store().set_config(PINS_KEY, pins)
    reqs.pop(agent, None)
    save_requests(reqs)
    _record_success(agent)
    return True, "Approved - {} can now log in with the PIN they chose.".format(agent)


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
        "requestedPinHash": security.hash_pin(requested_pin),
        "at": C.now_iso(),
        "status": "pending",
    }
    save_requests(reqs)
    return True, "Request sent. Ask your admin to approve it, then log in with your new PIN."

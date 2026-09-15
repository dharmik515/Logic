"""LOCK_PIN_CHANGES: the team and their PINs belong to the backend.

With it set, nobody sitting at the admin screen can add, remove or re-PIN
anyone. Secrets are the only route, and they are re-applied on every start.
"""
import os, sys

os.environ["SQLITE_PATH"] = "data/lock.db"
try: os.remove("data/lock.db")
except OSError: pass
os.environ["ADMIN_PIN"] = "22446688"
os.environ["AGENTS"] = "Alpha, Bravo, Charlie"
os.environ["AGENT_PINS"] = "Alpha:111111, Bravo:222222, Charlie:333333"
os.environ["LOCK_PIN_CHANGES"] = "true"
sys.path.insert(0, ".")   # run from the project root
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

from streamlit.testing.v1 import AppTest
from lib import auth, config as C, security
from lib.storage import get_store

assert C.pins_locked()
print("OK  LOCK_PIN_CHANGES is on")

# --- PINs come from secrets and work -------------------------------------
auth.load_pins()
assert auth.check_agent("Alpha", "111111") and auth.check_agent("Bravo", "222222")
assert not auth.check_agent("Alpha", "222222")
print("OK  agents log in with the PINs set in secrets")

stored = get_store().get_config("agentpins")
assert all(security.is_hash(v) for v in stored.values())
assert "111111" not in str(stored), "a PIN is readable in the database"
print("OK  and they are still stored only as hashes")

# --- every write path refuses --------------------------------------------
for label, result in (
        ("set_pin", auth.set_pin("Alpha", "999999")),
        ("add_agent", auth.add_agent("Delta", "444444")),
        ("remove_agent", auth.remove_agent("Bravo")),
):
    ok, msg = result
    assert not ok, "%s went through while locked" % label
    assert "backend" in msg.lower(), msg
print("OK  set_pin, add_agent and remove_agent all refuse:", msg)

assert auth.check_agent("Alpha", "111111"), "a refused set_pin still changed the PIN"
assert auth.load_agents() == ["Alpha", "Bravo", "Charlie"], auth.load_agents()
print("OK  nothing actually changed - roster and PINs intact")

auth.request_reset("Charlie", "5150")
ok, msg = auth.approve_request("Charlie")
assert not ok and "backend" in msg.lower(), msg
assert not auth.check_agent("Charlie", "5150"), "an approval slipped through"
print("OK  a reset request cannot be approved into effect either")

# --- editing secrets is the way, and it takes effect ---------------------
os.environ["AGENT_PINS"] = "Alpha:777777, Bravo:222222, Charlie:333333"
auth.load_pins()                      # what a reboot does
assert auth.check_agent("Alpha", "777777"), "the secret change did not apply"
assert not auth.check_agent("Alpha", "111111"), "the old PIN still works"
print("OK  changing AGENT_PINS and restarting is the only thing that works")

# stable across restarts: no re-hash churn when nothing changed
before = get_store().get_config("agentpins")["Bravo"]
auth.load_pins(); auth.load_pins()
assert get_store().get_config("agentpins")["Bravo"] == before, "re-hashed unnecessarily"
print("OK  unchanged PINs are not re-hashed on every start")

# --- the admin screen offers no way in -----------------------------------
at = AppTest.from_file("app.py", default_timeout=60)
at.session_state.role = "admin"
at.session_state.admin_pin = "22446688"
at.run()
assert not at.exception, [e.value for e in at.exception]
labels = [b.label for b in at.button]
for forbidden in ("Add agent", "Remove", "Save"):
    assert forbidden not in labels, "%r is still on the locked dashboard" % forbidden
screen = " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])
assert "locked to the backend" in screen, screen[:200]
for secret in ("111111", "222222", "333333", "777777", "22446688"):
    assert secret not in screen, "%r is visible on screen" % secret
print("OK  the dashboard shows no add/remove/save controls and no PINs")

# --- and the strongest form: secrets hold hashes, not PINs ---------------
A, B = "444444", "555555"
os.environ["AGENT_PINS"] = "Alpha:{}, Bravo:{}".format(
    security.hash_pin(A), security.hash_pin(B))
os.environ["ADMIN_PIN_HASH"] = security.hash_pin("224466-gate")
os.environ.pop("ADMIN_PIN", None)
get_store().set_config("loginattempts", {})

auth.load_pins()
assert auth.check_agent("Alpha", A) and auth.check_agent("Bravo", B)
assert not auth.check_agent("Alpha", B)
assert auth.check_admin("224466-gate") and not auth.check_admin("22446688")
print("OK  logins work when secrets carry hashes instead of PINs")

blob = os.environ["AGENT_PINS"] + os.environ["ADMIN_PIN_HASH"] + str(
    get_store().get_config("agentpins"))
for secret in (A, B, "224466-gate"):
    assert secret not in blob, "%r is readable in secrets or the database" % secret
print("OK  neither secrets nor the database holds a usable PIN")

# a hash must be stored verbatim - re-hashing one would lock everybody out
stored = get_store().get_config("agentpins")["Alpha"]
auth.load_pins(); auth.load_pins()
assert get_store().get_config("agentpins")["Alpha"] == stored
assert auth.check_agent("Alpha", A), "a supplied hash got re-hashed"
print("OK  supplied hashes are stored verbatim and survive restarts")

print()
print("*** BACKEND LOCK VERIFIED ***")

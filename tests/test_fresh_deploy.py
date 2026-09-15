"""A brand-new deploy: no secrets, no roster, no database.

This is what a fresh Streamlit Community Cloud app looks like on its first
visit, so it is the path most likely to be broken and least likely to be
noticed. Run from the project root.
"""
import os, sys

for _k in ("AGENTS", "QUICK_REMARKS", "ADMIN_PIN", "AGENT_PIN",
           "SUPABASE_URL", "SUPABASE_KEY"):
    os.environ.pop(_k, None)
os.environ["SQLITE_PATH"] = "data/fresh.db"
try: os.remove("data/fresh.db")
except OSError: pass
sys.path.insert(0, ".")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

from streamlit.testing.v1 import AppTest
from lib import auth, config as C


def run(label, **state):
    at = AppTest.from_file("app.py", default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    if at.exception:
        print("!! EXCEPTION on", label)
        for e in at.exception:
            print("   ", e.value)
        sys.exit(1)
    print("OK ", label)
    return at


md = lambda at: " ".join(m.value for m in at.markdown)
errs = lambda at: " ".join(e.value for e in at.error)

# --- 1. the roster ships, but not a single PIN ----------------------------
roster = auth.load_agents()
assert roster == C.DEFAULT_AGENTS and len(roster) == 11, roster
print("OK  roster seeds from source:", len(roster), "agents")

from lib import security
pins = auth.load_pins()
assert all(security.is_hash(v) for v in pins.values()), pins
assert len(set(pins.values())) == len(pins), "agents share a stored value"
assert not any(v.isdigit() for v in pins.values()), "a PIN is stored in the clear"
print("OK  every agent gets their own random PIN, stored only as a hash")

at = run("login screen lists the team")
names = [getattr(o, "content", o) for o in at.get("button_group")[1].options]
assert names == roster, names

# --- 2. with no ADMIN_PIN set, nothing opens the dashboard ----------------
assert C.admin_pin() is None, "a PIN is baked into the source somewhere"
assert not C.admin_configured()
for attempt in ("", "24668", "12345", "0000", "admin", None):
    assert not auth.check_admin(attempt), "admin login accepted %r with no PIN set" % attempt
print("OK  no ADMIN_PIN configured -> every admin login is refused, including blank")

at = run("admin tab explains what to configure", login_mode="Admin")
assert "Admin access is not set up yet" in md(at), md(at)
assert not any(b.label == "Open dashboard" for b in at.button),     "a login button is offered when admin access cannot work"
print("OK  the admin tab says what to set instead of offering a dead PIN box")

# --- 3. once configured, it opens - and only with that PIN ----------------
os.environ["ADMIN_PIN"] = "918273"
assert C.admin_configured() and auth.check_admin("918273")
assert not auth.check_admin("24668"), "the old published PIN still works"
print("OK  once ADMIN_PIN is set it opens with that PIN and nothing else")

at = run("admin dashboard", role="admin", admin_pin="918273")

ok, msg = auth.add_agent("Asha", "4321"); assert ok, msg
assert "Asha" in auth.load_agents()
assert auth.check_agent("Asha", "4321")
print("OK  admin can add someone, and they can log in straight away")

# --- 4. PINs can be supplied per agent, from secrets only -----------------
os.environ["AGENT_PINS"] = "Nila:4821, Omar:7390"
from lib.storage import get_store
get_store().set_config("roster", ["Nila", "Omar"])
get_store().set_config("agentpins", {})
get_store().set_config("loginattempts", {})
auth.load_pins()
assert auth.check_agent("Nila", "4821") and auth.check_agent("Omar", "7390")
assert not auth.check_agent("Nila", "7390")
stored = get_store().get_config("agentpins")
assert "4821" not in str(stored), "the configured PIN is readable in the database"
print("OK  AGENT_PINS sets each PIN, and only its hash is ever stored")

# --- 5. a deploy that first ran with an empty roster recovers -------------
# The seed runs once. If it ran when nothing was configured, the stored roster
# is [] and the names added to config.py later would never appear.
get_store().set_config("roster", [])
recovered = auth.load_agents()
assert recovered == C.DEFAULT_AGENTS, recovered
print("OK  an empty stored roster re-seeds from config:", len(recovered), "agents")

get_store().set_config("roster", ["Asha", "Ravi"])
assert auth.load_agents() == ["Asha", "Ravi"], "a real roster was overwritten"
print("OK  a roster that has people in it is left alone")

print()
print("*** FRESH-DEPLOY PATH VERIFIED ***")

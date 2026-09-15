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

# --- 1. nothing configured, nothing stored --------------------------------
assert auth.load_agents() == [], "a fresh install must not ship anybody's name"
assert C.quick_remarks() == [], "a fresh install must not ship client names"
print("OK  fresh install: roster empty, no client names, no data")

at = run("login screen with an empty team")
assert "No agents have been added yet" in md(at), md(at)
assert not any(b.label == "Log in" for b in at.button), "login offered with no agents"

at = run("forgot-PIN screen with an empty team", forgot=True)
assert "No agents have been added yet" in md(at)

# --- 2. the admin can still get in and build the team ---------------------
at = run("admin dashboard", role="admin", admin_pin=C.admin_pin())
assert "default admin PIN" in errs(at), "the default-PIN warning is missing"
print("OK  admin warned that the published default PIN is still in force")

ok, msg = auth.add_agent("Asha", "4321"); assert ok, msg
ok, msg = auth.add_agent("Ravi", "4322"); assert ok, msg
assert auth.load_agents() == ["Asha", "Ravi"]
print("OK  admin built the team from scratch:", auth.load_agents())

at = run("login screen once the team exists")
names = [getattr(o, "content", o) for o in at.get("button_group")[1].options]
assert names == ["Asha", "Ravi"], names
assert auth.check_agent("Asha", "4321")
print("OK  the new agents can log in")

# --- 3. the warning clears once a real PIN is set -------------------------
os.environ["ADMIN_PIN"] = "918273"
assert not C.using_default_admin_pin()
at = run("admin dashboard with a configured PIN", role="admin", admin_pin="918273")
assert "default admin PIN" not in errs(at)
print("OK  warning clears once ADMIN_PIN is configured")

print()
print("*** FRESH-DEPLOY PATH VERIFIED ***")

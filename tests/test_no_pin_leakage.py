"""Nothing anywhere should ever hold a PIN you could log in with.

The threats this pins down:
  * the repository is public
  * a database dump, or a leaked DATABASE_URL, exposes every stored row
  * the admin panel is a screen somebody can photograph
  * a 4-digit PIN is 10,000 guesses, which a script does in seconds
"""
import json
import os
import pathlib
import sys
import time

os.environ["SQLITE_PATH"] = "data/leak.db"
try: os.remove("data/leak.db")
except OSError: pass
os.environ["ADMIN_PIN"] = "246810"
os.environ["AGENT_PINS"] = "Sultan:4821, Ifham:7390"
os.environ.pop("ADMIN_PIN_HASH", None)
sys.path.insert(0, ".")   # run from the project root
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

from streamlit.testing.v1 import AppTest

from lib import auth, config as C, security
from lib.storage import get_store

SECRETS = {"4821", "7390", "246810"}


# ---- 1. nothing resembling a PIN is committed to the repository ----------
# The application itself, plus the docs. Test fixtures are excluded on
# purpose: the PINs in them guard a throwaway database and protect nothing.
SKIP = {".git", "data", "__pycache__", "tests"}
tracked = [p for p in pathlib.Path(".").rglob("*")
           if p.is_file() and not SKIP & set(p.parts)
           and p.suffix in (".py", ".md", ".toml", ".txt", ".example", "")]
offenders = []
for f in tracked:
    body = f.read_text(encoding="utf-8", errors="ignore")
    for line in body.splitlines():
        if "PIN" in line.upper() and any(
                tok.isdigit() and 4 <= len(tok) <= 6
                for tok in line.replace('"', " ").replace("'", " ").replace("=", " ").split()):
            # a lone iteration count or a year is fine; a PIN next to "PIN" is not
            if "ITERATIONS" in line.upper() or "120_000" in line:
                continue
            offenders.append("%s: %s" % (f, line.strip()[:70]))
assert not offenders, "PIN-like literals committed:\n  " + "\n  ".join(offenders)
print("OK  %d tracked files scanned - no PIN literal committed" % len(tracked))

# ---- 2. the database stores hashes, not PINs ----------------------------
auth.load_pins()
stored = get_store().get_config("agentpins")
assert all(security.is_hash(v) for v in stored.values()), stored
blob = json.dumps(stored)
for secret in ("4821", "7390"):
    assert secret not in blob, "the PIN %r is recoverable from the database" % secret
print("OK  every stored PIN is a pbkdf2 hash; no PIN appears in the dump")
print("     e.g. %s" % stored["Sultan"][:46] + "...")

assert auth.check_agent("Sultan", "4821"), "the hash does not verify the real PIN"
assert not auth.check_agent("Sultan", "4822")
print("OK  hashes still verify the right PIN and reject the wrong one")

# ---- 3. a reset request never exposes the chosen PIN --------------------
ok, _ = auth.request_reset("Athar", "5150")
assert ok
req_blob = json.dumps(get_store().get_config("resetrequests"))
assert "5150" not in req_blob, "the requested PIN is readable in the database"
assert "requestedPin\"" not in req_blob, "a plaintext requested PIN field survives"
print("OK  a pending reset stores only a hash - the admin cannot see the choice")

ok, msg = auth.approve_request("Athar")
assert ok and auth.check_agent("Athar", "5150"), msg
print("OK  approving it still works:", msg)

# ---- 4. the admin panel does not render any PIN -------------------------
at = AppTest.from_file("app.py", default_timeout=60)
at.session_state.role = "admin"
at.session_state.admin_pin = "246810"
at.run()
assert not at.exception, [e.value for e in at.exception]
screen = " ".join(
    [m.value for m in at.markdown] + [c.value for c in at.caption]
    + [str(getattr(i, "value", "")) for i in at.text_input]
)
for secret in SECRETS:
    assert secret not in screen, "%r is visible on the admin dashboard" % secret
print("OK  the admin dashboard renders no PIN anywhere on screen")

# ---- 5. guessing is throttled -------------------------------------------
for i in range(security.MAX_ATTEMPTS):
    auth.check_agent("Ifham", "0000")
locked, left = auth.locked_out("Ifham")
assert locked, "no lockout after %d wrong PINs" % security.MAX_ATTEMPTS
assert not auth.check_agent("Ifham", "7390"), "the correct PIN works while locked out"
print("OK  %d wrong PINs locks the account for %d minutes - %s"
      % (security.MAX_ATTEMPTS, left // 60 + 1, security.describe_lockout(left)))

for i in range(security.MAX_ATTEMPTS):
    auth.check_admin("999999")
assert auth.locked_out("admin")[0], "the admin login is not throttled"
assert not auth.check_admin("246810"), "admin bypasses its own lockout"
print("OK  the admin login is throttled the same way")

# a deliberate reset clears the lockout, so nobody is stuck out
auth.set_pin("Ifham", "3344")
assert not auth.locked_out("Ifham")[0]
assert auth.check_agent("Ifham", "3344")
print("OK  an admin PIN reset lifts the lockout immediately")

# ---- 6. the admin secret itself can be a hash ---------------------------
os.environ["ADMIN_PIN_HASH"] = security.hash_pin("778899")
get_store().set_config("loginattempts", {})
assert C.admin_secret_is_hashed()
assert auth.check_admin("778899"), "the hashed admin secret does not verify"
assert not auth.check_admin("246810"), "the old plain ADMIN_PIN still works"
print("OK  with ADMIN_PIN_HASH set, not even the secrets store holds the PIN")

print()
print("*** NO PIN IS RECOVERABLE FROM REPO, DATABASE OR SCREEN ***")

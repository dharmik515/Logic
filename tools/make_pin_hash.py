"""Turn PINs into hashes you can paste into secrets.

    python tools/make_pin_hash.py            # the admin PIN
    python tools/make_pin_hash.py --agents   # the whole team

PINs are typed, never echoed, never written to disk. Only the hashes are
printed. Paste those into your secrets and the PINs themselves exist nowhere
at all - not in the repository, not in the database, not in secrets, not on
anyone's screen. Only in the head of whoever chose them.

Note the limit this cannot fix: a 4-6 digit PIN is a small keyspace, so a
hash of one can still be brute-forced offline by someone who steals your whole
database. Guard DATABASE_URL accordingly, and prefer a longer admin secret -
letters beat extra digits by an enormous margin.
"""
import getpass
import os
import sys

_WARNED = []


def _prompt(label):
    """Read a secret without echoing it, where the terminal allows that.

    getpass talks to the console directly on Windows, so it blocks forever
    when there is no interactive one - a piped invocation, or some IDE
    terminals. Fall back to a plain read there, and say so, rather than hang.
    """
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            return getpass.getpass(label).strip()
        except Exception:
            pass
    if not _WARNED:
        print("   (this terminal cannot hide typing - what you enter will be visible)")
        _WARNED.append(True)
    sys.stdout.write(label)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        return ""
    return line.strip()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import config as C  # noqa: E402
from lib import security  # noqa: E402


def ask(label, *, digits_only=True):
    """Prompt twice, echo nothing, return the value or None."""
    first = _prompt("%s: " % label)
    if not first:
        return None
    if digits_only and (not first.isdigit() or not 4 <= len(first) <= 6):
        print("   a PIN should be 4 to 6 digits - skipped")
        return None
    if first != _prompt("   type it again: "):
        print("   they did not match - skipped")
        return None
    return first


def admin() -> int:
    print("Admin secret -> ADMIN_PIN_HASH")
    print("Up to 10 characters. Letters make it far stronger than extra digits.\n")

    first = _prompt("Admin PIN or passphrase: ")
    if not first:
        print("Nothing entered.")
        return 1
    if first != _prompt("Type it again: "):
        print("They did not match.")
        return 1
    if len(first) < 8 or first.isdigit():
        print()
        print("   note: digits alone, or anything short, can be brute-forced")
        print("   offline if your database ever leaks. Letters fix that.")

    print("\nPaste this into your secrets, and delete any ADMIN_PIN line:\n")
    print('ADMIN_PIN_HASH = "{}"\n'.format(security.hash_pin(first)))
    return 0


def agents() -> int:
    roster = C.default_agents()
    if not roster:
        print("No roster configured. Set AGENTS first, or add the team in the app.")
        return 1

    print("Agent PINs -> AGENT_PINS")
    print("4 to 6 digits each. Press Enter to skip anyone and leave them")
    print("with the random PIN the app already gave them.\n")

    pairs = []
    for name in roster:
        pin = ask("  %-10s" % name)
        if pin:
            pairs.append("{}:{}".format(name, security.hash_pin(pin)))

    if not pairs:
        print("\nNothing entered.")
        return 1

    print("\nPaste this single line into your secrets:\n")
    print('AGENT_PINS = "{}"\n'.format(", ".join(pairs)))
    print("Those are hashes, so the PINs themselves are now only in your head -")
    print("write them down for the team before you close this window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(agents() if "--agents" in sys.argv else admin())

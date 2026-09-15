"""PIN hashing and login throttling.

Nothing in this app stores a PIN. It stores a salted PBKDF2-SHA256 hash, which
cannot be turned back into the PIN - so a leaked database, a stolen
DATABASE_URL or a screenshot of the admin panel reveals nothing anyone can log
in with.

That is a deliberate trade. The admin can no longer read an agent's PIN back to
them over the phone, because nobody can. The forgot-PIN flow covers it: the
agent picks the new PIN they want and the admin approves the request without
ever seeing it.

PBKDF2 is used because it is in the standard library - no dependency to install
on a free host, and no build step that can fail a deploy. PINs are short by
nature (4-6 digits, so at most a million possibilities), which is exactly why
`too_many_attempts` matters as much as the hashing does: it is the throttle,
not the hash, that defeats guessing.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Optional, Tuple

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 120_000          # ~50-100ms on a small container: fine per login
SALT_BYTES = 16

# Throttle: this many misses locks that name out for this long.
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_pin(pin: str, *, iterations: int = ITERATIONS) -> str:
    """PIN -> 'pbkdf2_sha256$120000$<salt>$<hash>'. Never reversible."""
    pin = str(pin or "")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return "{}${}${}${}".format(ALGORITHM, iterations, _b64(salt), _b64(digest))


def is_hash(value) -> bool:
    return isinstance(value, str) and value.startswith(ALGORITHM + "$")


def verify_pin(pin: str, stored) -> bool:
    """Check a PIN against a stored hash.

    Accepts a plaintext `stored` as well, purely so a database written by an
    older version keeps working; auth upgrades those to a hash on the next
    successful login.
    """
    if not stored:
        return False
    if not is_hash(stored):
        # legacy plaintext - still constant-time, still no early return
        return hmac.compare_digest(str(pin or ""), str(stored))

    try:
        _, iterations, salt_b64, expected = str(stored).split("$", 3)
        salt = base64.b64decode(salt_b64)
        digest = hashlib.pbkdf2_hmac(
            "sha256", str(pin or "").encode("utf-8"), salt, int(iterations))
    except Exception:
        return False
    return hmac.compare_digest(_b64(digest), expected)


# ------------------------------------------------------------------ throttle
def too_many_attempts(record, now: float) -> Tuple[bool, int]:
    """(locked, seconds_remaining) for a stored attempt record."""
    if not isinstance(record, dict):
        return False, 0
    until = float(record.get("until") or 0)
    if until > now:
        return True, int(until - now) + 1
    return False, 0


def register_failure(record, now: float) -> dict:
    """Count a miss, and lock the account once there are too many."""
    record = dict(record) if isinstance(record, dict) else {}
    # A lockout that has expired starts the count again from zero.
    if float(record.get("until") or 0) <= now and record.get("count", 0) >= MAX_ATTEMPTS:
        record = {}
    count = int(record.get("count", 0)) + 1
    out = {"count": count, "until": 0}
    if count >= MAX_ATTEMPTS:
        out["until"] = now + LOCKOUT_SECONDS
    return out


def describe_lockout(seconds: int) -> str:
    minutes = max(1, (seconds + 59) // 60)
    return "Too many wrong PINs. Try again in {} minute{}.".format(
        minutes, "" if minutes == 1 else "s")

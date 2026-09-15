"""Turn a PIN into a hash you can paste into secrets.

    python tools/make_pin_hash.py

The PIN is typed, never stored, and never echoed. Only the hash is printed -
paste that into your app's secrets as ADMIN_PIN_HASH and the plain PIN exists
nowhere but in your head.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import security


def main() -> int:
    print("Create an admin PIN hash for ADMIN_PIN_HASH")
    print("(nothing is written to disk; the PIN is not echoed)\n")

    first = getpass.getpass("PIN (4-6 digits): ").strip()
    if not first:
        print("Nothing entered.")
        return 1
    if not first.isdigit() or not 4 <= len(first) <= 6:
        print("A PIN should be 4 to 6 digits.")
        return 1
    if first != getpass.getpass("Type it again: ").strip():
        print("They did not match.")
        return 1

    print("\nPaste this line into your secrets:\n")
    print('ADMIN_PIN_HASH = "{}"\n'.format(security.hash_pin(first)))
    print("Then remove any ADMIN_PIN line - it is no longer needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

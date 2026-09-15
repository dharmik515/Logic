"""The Postgres backend, against a real server.

Skips itself unless DATABASE_URL points at one, so it is safe to run in any
checkout. To run it locally with Docker:

    docker run -d --name dar_pg -e POSTGRES_PASSWORD=testpw \
        -e POSTGRES_DB=dar -p 55432:5432 postgres:16-alpine
    DATABASE_URL=postgresql://postgres:testpw@localhost:55432/dar \
        python tests/test_postgres.py
"""
import io
import os
import sys

sys.path.insert(0, ".")   # run from the project root
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DSN = os.environ.get("DATABASE_URL")
if not DSN:
    print("SKIPPED - set DATABASE_URL to a Postgres server to run this suite")
    raise SystemExit(0)

os.environ.setdefault("ADMIN_PIN", "246810")
os.environ.setdefault("AGENT_PIN", "123456")
os.environ.setdefault("AGENTS", "Alpha, Bravo")

from PIL import Image

import lib.auth
import lib.records
import lib.storage as S
from lib import auth, config as C, export, images, records

store = S.build_store()
assert store.name == "Postgres", "DATABASE_URL was not picked up (got %s)" % store.name
print("OK  backend:", store.name, "| survives a restart:", store.persistent_on_cloud)

# Point the app's modules at this server for the duration of the test.
S.get_store = lambda: store
lib.records.get_store = lambda: store
lib.auth.get_store = lambda: store

# Start from a clean database so assertions are about this run only.
store._run("TRUNCATE entries, photos, config")

# --- schema ---------------------------------------------------------------
rows = store._run(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema='public' ORDER BY table_name", fetch="all")
tables = {r[0] for r in rows}
assert {"entries", "photos", "config"} <= tables, tables
print("OK  tables created automatically:", sorted(tables))

buf = io.BytesIO(); Image.new("RGB", (600, 400), (20, 90, 170)).save(buf, "JPEG")
URL = images.to_data_url(buf.getvalue())
d = C.today_str()

# --- roster and PINs live in JSONB ----------------------------------------
auth.load_pins()
assert auth.load_agents() == ["Alpha", "Bravo"], auth.load_agents()
assert auth.check_agent("Alpha", C.default_agent_pin())
print("OK  roster and PINs round-trip:", auth.load_agents())

# --- a whole day ----------------------------------------------------------
records.save_start("Alpha", d, 41000, URL, opening_balance=5000)
e = records.save_final("Alpha", d, end_km=41155, total_deals=4, fuel_amount=0,
                       opening_balance=5000, spent_amount=1250, photo_end=URL,
                       diffs=[{"amount": 900, "dealId": "ORD-1", "remark": "Client A"}])
assert e["distance"] == 155 and e["remainingBalance"] == 3750.0

back = records.load("Alpha", d)
assert back["diffs"][0]["dealId"] == "ORD-1", back
assert records.photo("Alpha", d, "start") and records.photo("Alpha", d, "end")
print("OK  day round-tripped: %s km, remaining %.0f, both photos stored"
      % (back["distance"], back["remainingBalance"]))

raw = images.decode(records.photo("Alpha", d, "end"))
assert raw and raw[:3] == b"\xff\xd8\xff", "the photo did not come back as a JPEG"
print("OK  photo comes back byte-for-byte: %d bytes" % len(raw))

# --- the month-long window ------------------------------------------------
old = records.blank("Bravo", "2025-01-01"); old["status"] = "completed"
store.put_entry(old)
store.put_photo("2025-01-01", "Bravo", "start", URL)
recent = records.blank("Bravo", d); recent["status"] = "completed"
store.put_entry(recent)
assert store.get_entry("2025-01-01", "Bravo")

kept = records.all_entries()          # the admin load performs the purge
assert store.get_entry("2025-01-01", "Bravo") is None, "an old row survived the purge"
assert store.get_photo("2025-01-01", "Bravo", "start") is None, "an old photo survived"
assert store.get_entry(d, "Bravo") is not None, "a recent row was wrongly purged"
print("OK  retention: older than %d days deleted (cutoff %s), %d rows kept"
      % (C.RETENTION_DAYS, C.cutoff_str(), len(kept)))

# --- export ---------------------------------------------------------------
csv = export.build_csv(records.all_entries()).decode("utf-8-sig")
assert "ORD-1" in csv and "Differential" in csv
print("OK  CSV built straight from Postgres: %d lines" % len(csv.splitlines()))

# --- hosted databases drop idle connections -------------------------------
store._conn.close()
assert auth.load_agents() == ["Alpha", "Bravo"], "did not recover from a dead connection"
print("OK  a dropped connection is re-established transparently")

print()
print("*** POSTGRES BACKEND VERIFIED ***")

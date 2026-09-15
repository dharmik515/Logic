import os, sys, io, base64
os.environ.setdefault("AGENTS", "Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliet, Kilo")
os.environ.setdefault("QUICK_REMARKS", "Client A, Client B")
os.environ["SQLITE_PATH"] = "data/smoke.db"
# Start from an empty store every run - otherwise a PIN approved by a
# previous run is still in place and the "before approval" check fails.
try: os.remove("data/smoke.db")
except OSError: pass
sys.path.insert(0, ".")

from lib import config as C, records, auth, export, images
from lib.storage import get_store

store = get_store()
print("backend:", store.name, "| persistent_on_cloud:", store.persistent_on_cloud)

# --- pins -------------------------------------------------------------
pins = auth.load_pins()
assert len(pins) == len(C.default_agents()), pins
assert auth.check_agent("Alpha", C.default_agent_pin())
assert not auth.check_agent("Alpha", "00000")
assert not auth.check_agent("Nobody", "12345")
assert auth.check_admin(C.admin_pin())
print("pins OK, seeded:", list(pins.items())[:2])

# --- forgot-PIN loop --------------------------------------------------
ok, msg = auth.request_reset("Bravo", "9911")
assert ok, msg
assert not auth.check_agent("Bravo", "9911"), "must NOT work before approval"
ok, msg = auth.approve_request("Bravo")
assert ok and auth.check_agent("Bravo", "9911"), msg
print("forgot-PIN flow OK ->", msg)

ok, _ = auth.request_reset("Charlie", "4321")
auth.reject_request("Charlie")
assert not auth.check_agent("Charlie", "4321")
assert auth.load_requests() == {}
print("reject OK")

ok, msg = auth.request_reset("Foxtrot", "12")
assert not ok
print("short-PIN rejected OK ->", msg)

# --- a real photo -----------------------------------------------------
from PIL import Image
buf = io.BytesIO(); Image.new("RGB", (3000, 2000), (30, 80, 160)).save(buf, "JPEG")
url = images.to_data_url(buf.getvalue())
assert url.startswith("data:image/jpeg;base64,")
print("photo compressed: 3000x2000 ->", images.human_size(images.approx_size(url)))
assert not images.too_big(url)
assert images.decode(url)[:3] == b"\xff\xd8\xff"

# garbage bytes must still be stored, never rejected
junk = images.to_data_url(b"\x00\x01not-an-image\xff")
assert junk and junk.startswith("data:")
print("accept-any-image OK ->", junk[:28])

# --- two-stage day ----------------------------------------------------
d = C.today_str()
e = records.save_start("Alpha", d, 45231, url)
assert e["status"] == "started" and e["hasStartPhoto"] and e["dayStartAt"]
assert e["endKm"] is None and e["distance"] is None
print("morning OK:", e["startKm"], e["status"], C.fmt_time(e["startKmAt"]))

e = records.save_final(
    "Alpha", d, end_km=45298, total_deals=4, fuel_amount=120, spent_amount=3500,
    diffs=[{"amount": 500, "remark": "Client A"}, {"amount": 300, "remark": "Client B"},
           {"amount": None, "remark": ""}],
    photo_end=url, photo_fuel=None,
)
assert e["status"] == "completed" and e["distance"] == 67, e
assert e["diffTotal"] == 800 and len(e["diffs"]) == 2
assert e["hasStartPhoto"] and e["hasEndPhoto"] and not e["hasFuelPhoto"], "morning photo must survive"
assert records.photo("Alpha", d, "start"), "start photo lost!"
print("evening OK: dist", e["distance"], "diff", e["diffTotal"], "breakdown:", records.diff_breakdown(e))

# a second agent, start-only
records.save_start("Bravo", d, 10000, url)

rows = records.all_entries()
t = records.totals(rows)
print("totals:", t)
assert t["submitted"] == 1 and t["started"] == 1

# --- retention --------------------------------------------------------
old = records.blank("Echo", "2020-01-01"); old["status"] = "completed"
store.put_entry(old); store.put_photo("2020-01-01", "Echo", "start", url)
assert store.get_entry("2020-01-01", "Echo")
rows = records.all_entries()
assert store.get_entry("2020-01-01", "Echo") is None, "old entry not purged"
assert store.get_photo("2020-01-01", "Echo", "start") is None, "old photo not purged"
print("30-day purge OK (cutoff %s)" % C.cutoff_str())

# --- CSV --------------------------------------------------------------
csv_bytes = export.build_csv(rows)
assert csv_bytes.startswith(b"\xef\xbb\xbf")
text = csv_bytes.decode("utf-8-sig")
lines = text.strip().splitlines()
assert lines[0] == ",".join(export.COLUMNS), lines[0]
# differentials are one row each now, not a single joined cell
import csv as _csv
_rows = list(_csv.reader(lines))
_ti = export.COLUMNS.index("Row Type")
_ri = export.COLUMNS.index("Differential Remark")
_diffs = [r for r in _rows[1:] if len(r) > _ti and r[_ti] == "Differential"]
assert [r[_ri] for r in _diffs] == ["Client A", "Client B"], _diffs
assert "Client A 500 + Client B 300" not in text, "still joining with +"
assert "TOTAL" in lines[-1]
print("CSV OK: %d cols, %d lines" % (len(export.COLUMNS), len(lines)))
print("  header:", lines[0][:70], "...")
print("  total :", lines[-1][:70], "...")

# --- charts -----------------------------------------------------------
from lib import charts
for m in charts.MEASURES:
    charts.by_agent(rows, m).to_dict()
    charts.over_time(rows, m).to_dict()
print("charts render OK for:", ", ".join(charts.MEASURES))
charts.by_agent([], "Deals").to_dict(); charts.over_time([], "Deals").to_dict()
print("charts handle empty data OK")

print("\n*** ALL SMOKE TESTS PASSED ***")

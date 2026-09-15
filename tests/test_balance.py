"""Opening balance -> spend -> remaining balance, end to end."""
import os, sys, io
os.environ.setdefault("AGENTS", "Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliet, Kilo")
os.environ.setdefault("QUICK_REMARKS", "Client A, Client B")
os.environ["SQLITE_PATH"] = "data/balance.db"
try: os.remove("data/balance.db")
except OSError: pass
sys.path.insert(0, ".")   # run from the project root
try: sys.stdout.reconfigure(encoding="utf-8")   # Windows console is cp1252
except Exception: pass

from streamlit.testing.v1 import AppTest
from lib import config as C, records, images, export
from PIL import Image

buf = io.BytesIO(); Image.new("RGB", (500, 350), (20, 90, 170)).save(buf, "JPEG")
URL = images.to_data_url(buf.getvalue()); d = C.today_str()

def run(label, **state):
    at = AppTest.from_file("app.py", default_timeout=60)
    for k, v in state.items(): at.session_state[k] = v
    at.run()
    if at.exception:
        print("!! EXCEPTION in", label)
        for ex in at.exception: print("   ", ex.value)
        sys.exit(1)
    print("OK ", label)
    return at

md = lambda at: " ".join(m.value for m in at.markdown)

# ---- 1. pure arithmetic -------------------------------------------------
assert records.remaining_of(5000, 1200) == 3800.0
assert records.remaining_of(5000, None) == 5000.0
assert records.remaining_of(None, 400) is None, "no opening -> no remaining"
assert records.remaining_of(1000, 2500) == -1500.0, "must be allowed to go negative"
print("OK  remaining_of: 5000-1200=3800, 1000-2500=-1500, None stays None")

# ---- 2. opening balance is required in the morning ----------------------
at = run("morning form shows opening balance first", role="agent", agent="Alpha")
labels = [n.label for n in at.number_input]
assert labels[0] == "Opening balance (₹)", labels
assert "Starting KM" in labels, labels
save = [b for b in at.button if "Save start of day" in b.label][0]
assert save.disabled, "save should be blocked until opening balance is entered"
assert "your opening balance" in md(at), md(at)
print("     -> field order:", labels)

# ---- 3. morning save stores it ------------------------------------------
e = records.save_start("Alpha", d, 45231, URL, opening_balance=5000)
assert e["openingBalance"] == 5000.0 and e["remainingBalance"] == 5000.0, e
print("OK  morning: opening 5000 stored, remaining 5000 (nothing spent yet)")

at = run("evening shows opening in the banner", role="agent", agent="Alpha",
         day_key="Alpha|" + d)
assert "Opening balance ₹5,000" in md(at), md(at)
assert "Cash" in md(at) and "Remaining balance" in md(at)

# ---- 4. evening submit computes remaining -------------------------------
e = records.save_final("Alpha", d, end_km=45298, total_deals=4,
                       opening_balance=5000, spent_amount=1200,
                       fuel_amount=300, photo_end=URL)
assert e["remainingBalance"] == 3800.0, e["remainingBalance"]
print("OK  evening: 5000 - 1200 = %.0f remaining" % e["remainingBalance"])

at = run("submitted summary shows remaining", role="agent", agent="Alpha",
         day_key="Alpha|" + d)
assert "Remaining balance" in md(at) and "3,800" in md(at)

# ---- 5. overspend is surfaced, not hidden -------------------------------
records.save_start("Bravo", d, 10000, URL, opening_balance=1000)
e = records.save_final("Bravo", d, end_km=10050, opening_balance=1000,
                       spent_amount=2500, photo_end=URL)
assert e["remainingBalance"] == -1500.0, e
print("OK  overspend kept as %.0f (not clamped to zero)" % e["remainingBalance"])

# ---- 6. admin totals, tiles and CSV -------------------------------------
rows = records.all_entries()
t = records.totals(rows)
assert t["opening"] == 6000.0 and t["remaining"] == 2300.0, t
print("OK  admin totals: opening %.0f, remaining %.0f" % (t["opening"], t["remaining"]))

at = run("admin dashboard", role="admin", admin_pin=C.admin_pin())
m = md(at)
for needle in ("Opening balance", "Cash remaining", "Remaining"):
    assert needle in m, "missing on dashboard: " + needle

text = export.build_csv(rows).decode("utf-8-sig")
hdr = text.splitlines()[0].split(",")
assert hdr == export.COLUMNS, hdr   # count is not pinned: columns get added
i_open, i_rem = hdr.index("Opening Balance"), hdr.index("Remaining Balance")
tot = [l for l in text.splitlines() if l.startswith("TOTAL")][0].split(",")
assert len(tot) == len(hdr), (len(tot), len(hdr))
assert float(tot[i_open]) == 6000.0 and float(tot[i_rem]) == 2300.0, (tot[i_open], tot[i_rem])
print("OK  CSV: %d cols, TOTAL row opening=%s remaining=%s" % (len(hdr), tot[i_open], tot[i_rem]))

# ---- 7. records from before this feature still work ---------------------
from lib.storage import get_store
old = records.blank("Charlie", d)
old.update(status="completed", startKm=1, endKm=2, distance=1, spentAmount=700,
           dayStartAt=C.now_iso(), submittedAt=C.now_iso())
old.pop("openingBalance"); old.pop("remainingBalance")   # keys did not exist yet
get_store().put_entry(old)
loaded = records.load("Charlie", d)
assert loaded["openingBalance"] is None and loaded["remainingBalance"] is None
run("legacy record (no balance keys) on agent form", role="agent", agent="Charlie",
    day_key="Charlie|" + d, edit_mode=True)
run("legacy record on admin dashboard", role="admin", admin_pin=C.admin_pin())
assert export.build_csv(records.all_entries())
print("OK  pre-feature records load, render and export")

print("\n*** BALANCE TESTS PASSED ***")

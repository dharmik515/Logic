"""Mandatory agent fields, one-row-per-differential CSV, and the admin's
add/remove-agent panel."""
import os, sys, io
os.environ.setdefault("ADMIN_PIN", "246810")
os.environ.setdefault("AGENT_PIN", "123456")
os.environ.setdefault("AGENTS", "Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliet, Kilo")
os.environ.setdefault("QUICK_REMARKS", "Client A, Client B")
os.environ["SQLITE_PATH"] = "data/roster.db"
try: os.remove("data/roster.db")
except OSError: pass
sys.path.insert(0, ".")   # run from the project root
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# AppTest mishandles single-select button groups (st.pills); patch it.
from streamlit.testing.v1.element_tree import ButtonGroup
def _indices(self):
    v = self.value
    if v is None: return []
    if not isinstance(v, (list, tuple)): v = [v]
    norm = lambda o: getattr(o, "content", o)
    opts = [norm(o) for o in self.options]
    return [opts.index(norm(self.format_func(x))) for x in v]
ButtonGroup.indices = property(_indices)
ButtonGroup.set_value = lambda self, val: (setattr(self, "_value", val), self)[1]

import csv as _csv
from streamlit.testing.v1 import AppTest
from lib import config as C, auth, records, images, export
from PIL import Image

buf = io.BytesIO(); Image.new("RGB", (400, 300), (20, 90, 170)).save(buf, "JPEG")
URL = images.to_data_url(buf.getvalue()); d = C.today_str()


def fresh(**state):
    at = AppTest.from_file("app.py", default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    return at


def evening(**state):
    """An agent sitting on the evening form, with an end photo already staged."""
    # edit_mode keeps the form on screen even once the day is submitted.
    base = dict(role="agent", agent="Alpha", day_key="Alpha|" + d, ph_end=URL,
                edit_mode=True)
    base.update(state)
    return fresh(**base)


def check(at, label):
    if at.exception:
        print("!! EXCEPTION in", label)
        for ex in at.exception:
            print("   ", ex.value)
        sys.exit(1)
    print("OK ", label)
    return at


md = lambda at: " ".join(m.value for m in at.markdown)
btn = lambda at, text: [b for b in at.button if text in b.label][0]
options = lambda at, i: [getattr(o, "content", o) for o in at.get("button_group")[i].options]


# ======================================================== 1. mandatory fields
records.save_start("Alpha", d, 45231, URL, opening_balance=5000)

at = check(evening(), "evening form loads")
assert btn(at, "Submit final report").disabled, "submit enabled with everything blank"
need = md(at)
for field in ("Ending KM", "Total deals done", "Opening balance",
              "Total amount spent", "Fuel money"):
    assert field in need, "not listed as required: " + field
print("     -> blocked, needs:", need.split("Still needed: ")[1][:100])

# Zeros are a real answer and must be accepted.
at = evening()
at.number_input(key="in_end_km").set_value(45231).run()
at.number_input(key="in_deals").set_value(0).run()
at.number_input(key="in_opening_eve").set_value(0.0).run()
at.number_input(key="in_spent").set_value(0.0).run()
at.number_input(key="in_fuel").set_value(0.0).run()
assert not btn(at, "Submit final report").disabled, "zeros should be accepted"
check(at, "all zeros accepted - submit enabled")

btn(at, "Submit final report").click().run()
e = records.load("Alpha", d)
assert e["totalDeals"] == 0 and e["spentAmount"] == 0 and e["fuelAmount"] == 0, e
assert e["openingBalance"] == 0 and e["remainingBalance"] == 0, e
print("OK  zeros stored as real zeros, not blanks")

at = evening()
at.number_input(key="in_fuel").set_value(500.0).run()
assert "fuel receipt photo" in md(at), "receipt not demanded when fuel > 0"
check(at, "fuel > 0 requires the receipt photo")

at = evening(diffs=[{"amount": None, "remark": "Client A", "dealId": ""}])
assert "differential row 1" in md(at), md(at)
check(at, "incomplete differential row blocks submit")


# =================================================== 2. CSV: one row per diff
records.save_final(
    "Bravo", d, end_km=100, opening_balance=1000, spent_amount=100,
    total_deals=2, fuel_amount=0, photo_end=URL,
    diffs=[{"amount": 278, "dealId": "ORD-686423", "remark": "T83783"},
           {"amount": 3746, "dealId": "ORD-894983", "remark": "T636373"},
           {"amount": 746, "dealId": "ORD-635269", "remark": "T763637"}])

text = export.build_csv(records.all_entries()).decode("utf-8-sig")
lines = [l for l in text.splitlines() if l.strip()]
parsed = list(_csv.reader(lines))
hdr = parsed[0]
assert hdr == export.COLUMNS

i_type = hdr.index("Row Type")
i_amt = hdr.index("Differential Amount")
i_id = hdr.index("Deal / Order ID")
i_rmk = hdr.index("Differential Remark")

day_rows = [r for r in parsed[1:] if r[i_type] == "Day"]
diff_rows = [r for r in parsed[1:] if r[i_type] == "Differential"]
assert len(diff_rows) == 3, len(diff_rows)
assert [r[i_amt] for r in diff_rows] == ["278.0", "3746.0", "746.0"], [r[i_amt] for r in diff_rows]
assert diff_rows[0][i_id] == "ORD-686423" and diff_rows[0][i_rmk] == "T83783"
# No cell should join several differentials together any more. (Checked on the
# differential columns only - submittedAt legitimately contains a "+05:30".)
assert all("+" not in r[i] for r in parsed[1:] for i in (i_amt, i_id, i_rmk)), \
    "differential cells are still joined with +"
assert "Differential Breakdown" not in hdr, "the joined breakdown column is still there"
assert all(len(r) == len(hdr) for r in parsed), "ragged row widths"
print("OK  CSV: %d Day rows, %d Differential rows, one per line" % (len(day_rows), len(diff_rows)))
print("     ->", " | ".join(diff_rows[0][i] for i in (i_type, 1, 2, i_amt, i_id, i_rmk)))

tot = [r for r in parsed if r[i_type] == "TOTAL"][0]
assert len(tot) == len(hdr)
assert float(tot[hdr.index("Differential Collected")]) == 4770.0, tot
print("OK  TOTAL row aligned, differential total =", tot[hdr.index("Differential Collected")])

import pandas as pd, pyarrow as pa
pa.Table.from_pandas(pd.DataFrame(export.rows_for(records.all_entries()), columns=export.COLUMNS))
print("OK  admin dataframe still Arrow-clean")


# =================================================== 3. add / remove an agent
assert auth.load_agents() == C.default_agents(), "roster should seed from the defaults"

ok, msg = auth.add_agent("Rahul", "4455")
assert ok, msg
assert "Rahul" in auth.load_agents() and auth.check_agent("Rahul", "4455")
print("OK  add_agent:", msg)

for bad, why in [("Rahul", "duplicate"), ("R", "too short"), ("", "empty"), ("Bob9", "digits")]:
    ok, _ = auth.add_agent(bad, "1234")
    assert not ok, "accepted a bad name (%s): %r" % (why, bad)
ok, _ = auth.add_agent("Priya", "12")
assert not ok, "accepted a short PIN"
print("OK  rejects duplicates, bad names and short PINs")

at = check(fresh(), "login screen")
assert "Rahul" in options(at, 1), options(at, 1)
print("OK  new agent appears in the login name picker")

records.save_start("Rahul", d, 10, URL, opening_balance=100)
ok, msg = auth.remove_agent("Rahul")
assert ok, msg
assert "Rahul" not in auth.load_agents()
assert not auth.check_agent("Rahul", "4455"), "removed agent can still log in"
assert records.load("Rahul", d) is not None, "past reports must be kept"
print("OK  remove_agent:", msg)

at = check(fresh(), "login screen after removal")
assert "Rahul" not in options(at, 1), options(at, 1)

at = check(fresh(role="admin", admin_pin=C.admin_pin()), "admin panel renders")
labels = [b.label for b in at.button]
assert "Add agent" in labels and "Remove" in labels and "Save" in labels, labels
print("OK  admin panel has Add agent / Save / Remove")

# Removal is destructive, so it must take two deliberate clicks.
at = fresh(role="admin", admin_pin=C.admin_pin())
at.button(key="rm_Bravo").click().run()
check(at, "remove asks for confirmation first")
assert "Bravo" in auth.load_agents(), "removed without confirming"
assert "Remove Bravo from the team?" in md(at)

at.button(key="rmy_Bravo").click().run()
check(at, "confirmed removal")
assert "Bravo" not in auth.load_agents(), "confirm did not remove"
print("OK  two-step confirm: nothing happens until 'Yes, remove'")

print("\n*** ROSTER + CSV + MANDATORY-FIELD TESTS PASSED ***")


# ============================================= 4. camera only - no uploads
# Morning form for an agent with no record yet: nothing staged, so the capture
# widget itself is on screen.
at = fresh(role="agent", agent="Golf")
assert len(at.get("camera_input")) >= 1, "no camera input on the morning form"
assert len(at.get("file_uploader")) == 0, "the morning form still offers an upload"
caps = " ".join(c.value for c in at.caption)
assert "must be taken here" in caps, caps
check(at, "morning form: camera only, no upload widget")

# Evening form (a photo is already staged, so the widget is behind Retake) -
# what matters is that no uploader exists anywhere on the page.
at = evening()
assert len(at.get("file_uploader")) == 0, "the evening form still offers an upload"
check(at, "evening form: no upload widget")

# And nothing in the source still builds one.
import pathlib as _pl
src = " ".join(_pl.Path("lib", f).read_text(encoding="utf-8")
               for f in ("view_agent.py", "view_admin.py", "view_login.py"))
assert "file_uploader" not in src, "st.file_uploader is still referenced in a view"
print("OK  no st.file_uploader anywhere in the views")

print()
print("*** CAMERA-ONLY CAPTURE CONFIRMED ***")

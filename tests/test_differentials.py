"""Reproduce the reported crash, then prove the fix + the new Deal ID field."""
import os, sys
os.environ.setdefault("ADMIN_PIN", "246810")
os.environ.setdefault("AGENT_PIN", "123456")
os.environ.setdefault("AGENTS", "Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliet, Kilo")
os.environ.setdefault("QUICK_REMARKS", "Client A, Client B")
os.environ["SQLITE_PATH"] = "data/regress.db"
try: os.remove("data/regress.db")
except OSError: pass
sys.path.insert(0, ".")
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

from streamlit.testing.v1 import AppTest
from lib import config as C, records, images
from PIL import Image
import io

buf = io.BytesIO(); Image.new("RGB", (600, 400), (20, 90, 170)).save(buf, "JPEG")
URL = images.to_data_url(buf.getvalue()); d = C.today_str(); A = "Alpha"

# ---- 1. the exact shape that crashed: a quick-add row with a remark but no
#         amount, saved and then reloaded.
records.save_start(A, d, 1000, URL)
e = records.save_final(A, d, end_km=1100, photo_end=URL,
                       diffs=[{"amount": None, "remark": "Client A"}])
amt = e["diffs"][0]["amount"]
assert isinstance(amt, float) and not isinstance(amt, bool), type(amt)
print("OK  blank amount stored as %r (%s) - not int" % (amt, type(amt).__name__))

at = AppTest.from_file("app.py", default_timeout=60)
at.session_state.role = "agent"; at.session_state.agent = A
at.session_state.day_key = A + "|" + d; at.session_state.edit_mode = True
at.run()
if at.exception:
    print("!! STILL CRASHES:")
    for ex in at.exception: print("   ", ex.value)
    sys.exit(1)
print("OK  reopening that report renders without StreamlitMixedNumericTypesError")

# ---- 2. the new Deal / Order ID field ---------------------------------
ids = [t.label for t in at.text_input]
assert "Deal / Order ID" in ids, ids
print("OK  Deal / Order ID field present:", ids)

at.number_input(key="d_amt_0").set_value(500.0).run()
at.text_input(key="d_id_0").input("ORD-48219").run()
at.text_input(key="d_rmk_0").input("Client A").run()
for b in at.button:
    if "Submit final report" in b.label: b.click().run(); break
assert not at.exception, [x.value for x in at.exception]

e = records.load(A, d)
row = e["diffs"][0]
assert row["dealId"] == "ORD-48219" and row["amount"] == 500.0, row
print("OK  saved row:", row)
print("OK  breakdown:", records.diff_breakdown(e))
print("OK  ids      :", records.diff_ids(e))

# ---- 3. CSV carries the IDs -------------------------------------------
from lib import export
text = export.build_csv(records.all_entries()).decode("utf-8-sig")
lines = text.strip().splitlines()
assert lines[0].split(",") == export.COLUMNS
assert "ORD-48219" in text
hdr = lines[0].split(",")
assert "Deal / Order ID" in hdr, hdr   # by name: columns move as fields are added
import csv as _csv
_rows = list(_csv.reader(lines))
_ti, _ii = hdr.index("Row Type"), hdr.index("Deal / Order ID")
_diffs = [r for r in _rows[1:] if len(r) > _ti and r[_ti] == "Differential"]
assert len(_diffs) == 1 and _diffs[0][_ii] == "ORD-48219", _diffs
tot = [l for l in lines if l.startswith("TOTAL")][0]
assert len(tot.split(",")) == len(hdr), (len(tot.split(",")), len(hdr))
print("OK  CSV: %d cols, IDs column at %d, TOTAL row aligned"
      % (len(hdr), hdr.index("Deal / Order ID")))

# ---- 4. admin still renders + dataframe stays Arrow-clean --------------
import pandas as pd, pyarrow as pa
pa.Table.from_pandas(pd.DataFrame(export.rows_for(records.all_entries()), columns=export.COLUMNS))
at2 = AppTest.from_file("app.py", default_timeout=60)
at2.session_state.role = "admin"; at2.session_state.admin_pin = C.admin_pin()
at2.run()
assert not at2.exception, [x.value for x in at2.exception]
assert "ORD-48219" in " ".join(m.value for m in at2.markdown), "ID not shown on admin card"
print("OK  admin dashboard renders and shows the deal ID")

print("\n*** REGRESSION + FEATURE TESTS PASSED ***")

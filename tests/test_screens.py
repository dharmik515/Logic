import os, sys, io
os.environ.setdefault("AGENTS", "Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliet, Kilo")
os.environ.setdefault("QUICK_REMARKS", "Client A, Client B")
os.environ["SQLITE_PATH"] = "data/apptest.db"
for _f in ("data/apptest.db",):
    try: os.remove(_f)
    except OSError: pass
sys.path.insert(0, ".")
from streamlit.testing.v1 import AppTest
from lib import config as C, records, images
from PIL import Image

def run(label, **state):
    at = AppTest.from_file("app.py", default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    if at.exception:
        print("!! EXCEPTION in", label)
        for ex in at.exception:
            print("   ", ex.value)
        sys.exit(1)
    print("OK  %-26s buttons=%-2d fields=%-2d md=%-3d charts=%d" % (
        label, len(at.button), len(at.number_input) + len(at.text_input),
        len(at.markdown), len(at.get("arrow_vega_lite_chart"))))
    return at

md = lambda at: " ".join(m.value for m in at.markdown)
labels = lambda at: [b.label for b in at.button]

at = run("login (agent mode)")
assert "Daily Agent Report" in md(at) and "How your day works" in md(at)
assert "Log in" in labels(at) and "🔑 Forgot my PIN" in labels(at)

at = run("login (admin mode)", login_mode="Admin")
assert "Open dashboard" in labels(at), labels(at)

at = run("login (forgot PIN)", forgot=True)
assert "Send request" in labels(at), labels(at)

# ---- agent: morning ----------------------------------------------------
at = run("agent (not started)", role="agent", agent="Alpha")
assert any("Save start of day" in b for b in labels(at)), labels(at)
assert not any("Submit final" in b for b in labels(at)), "evening form shown too early"
assert "Still needed" in md(at), "missing-field guidance absent"

buf = io.BytesIO(); Image.new("RGB", (900, 700), (20, 90, 170)).save(buf, "JPEG")
url = images.to_data_url(buf.getvalue())
d = C.today_str()
records.save_start("Alpha", d, 45231, url)

# ---- agent: evening ----------------------------------------------------
at = run("agent (end of day)", role="agent", agent="Alpha")
assert any("Submit final report" in b for b in labels(at)), labels(at)
assert "Day started at" in md(at), "start-of-day banner missing"
assert "Differential collected" in md(at)

records.save_final("Alpha", d, end_km=45298, total_deals=4, fuel_amount=120,
                   spent_amount=3500, diffs=[{"amount": 500, "remark": "Client A"}],
                   photo_end=url)

at = run("agent (submitted)", role="agent", agent="Alpha")
assert any("Edit my report" in b for b in labels(at)), labels(at)
assert "is submitted at" in md(at)

# day_key mimics a session already on today (it is set on the first render);
# that is what makes "Edit my report" stick instead of being reset.
at = run("agent (editing)", role="agent", agent="Alpha", edit_mode=True,
         day_key="Alpha|" + d)
assert any("Submit final report" in b for b in labels(at))

# ---- dataframe must be Arrow-clean (no mixed str/int columns) ----------
import pandas as pd, pyarrow as pa
from lib import export as _ex
_df = pd.DataFrame(_ex.rows_for(records.all_entries()), columns=_ex.COLUMNS)
pa.Table.from_pandas(_df)   # raises if a column is mixed-type
print("OK  %-26s dtypes clean, %d cols" % ("admin full table", len(_df.columns)))

# ---- admin -------------------------------------------------------------
records.save_start("Bravo", d, 10000, url)
at = run("admin (by day)", role="admin", admin_pin=C.admin_pin())
m = md(at)
for needle in ("Admin dashboard", "Total deals executed", "Total amount spent",
               "Total differential", "Agent by agent", "1 submitted", "1 start only"):
    assert needle in m, "missing: " + needle
assert any("Download CSV" in b.label for b in at.get("download_button")), "no CSV button"
assert any("📷" in b for b in labels(at)), "no photo buttons"
assert "Waiting on:" in " ".join(c.value for c in at.caption), "pending list missing"

at = run("admin (30-day view)", role="admin", admin_pin=C.admin_pin(),
         adm_scope="Last 30 days")
assert len(at.get("arrow_vega_lite_chart")) == 2, "trend chart missing in 30-day view"

at = run("admin (empty day)", role="admin", admin_pin=C.admin_pin(),
         adm_scope="By day", adm_day=__import__("datetime").date(2026, 9, 1))
assert "Nothing filed" in md(at), "empty state missing"

print("\n*** ALL APP TESTS PASSED ***")

"""One full journey through the app, driven the way a person drives it.

Admin adds an agent -> that agent logs in -> files the morning -> comes back and
files the evening -> admin sees it, downloads the CSV -> agent forgets their PIN
-> admin approves the reset -> agent logs in again -> admin removes them.

Everything goes through real widgets and real button clicks. The only seam is
the camera: st.camera_input cannot be driven from AppTest, so the captured
photo is placed in the session slot the widget would have filled
(`ph_start` / `ph_end`) - exactly what _capture_widgets does on a real capture.
"""
import os, sys, io

os.environ.setdefault("AGENTS", "Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliet, Kilo")
os.environ.setdefault("QUICK_REMARKS", "Client A, Client B")
os.environ["SQLITE_PATH"] = "data/e2e.db"
try: os.remove("data/e2e.db")
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
from lib import config as C, auth, records, export, images
from lib.storage import get_store
from PIL import Image, ImageDraw

STEP = [0]


def step(msg):
    STEP[0] += 1
    print("%2d. %s" % (STEP[0], msg))


def app(**state):
    at = AppTest.from_file("app.py", default_timeout=90)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    return at


def ok(at, label):
    if at.exception:
        print("   !! EXCEPTION:", label)
        for ex in at.exception:
            print("      ", ex.value)
        sys.exit(1)
    return at


def btn(at, text):
    for b in at.button:
        if text in b.label:
            return b
    raise AssertionError("no button %r; have %s" % (text, [b.label for b in at.button]))


md = lambda at: " ".join(m.value for m in at.markdown)


def odometer(km):
    """A photo the way the camera would hand one over."""
    im = Image.new("RGB", (900, 360), (26, 30, 42))
    ImageDraw.Draw(im).text((120, 170), "  %s km" % format(km, ","), fill=(130, 220, 255))
    b = io.BytesIO(); im.save(b, "JPEG")
    return images.to_data_url(b.getvalue())


AGENT, PIN, NEW_PIN = "Priya", "4321", "8899"
TODAY = C.today_str()

print("\n=== END TO END: %s ===\n" % C.fmt_date(TODAY))

# ---------------------------------------------------------------- 1. admin in
at = ok(app(login_mode="Admin"), "login page")
at.text_input(key="pin_admin").input(C.admin_pin()).run()
btn(at, "Open dashboard").click().run()
ok(at, "admin login")
assert at.session_state.role == "admin"
assert "Admin dashboard" in md(at)
step("Admin logs in")

# ------------------------------------------------------- 2. admin adds agent
at.text_input(key="new_agent_name").input(AGENT).run()
at.text_input(key="new_agent_pin").input(PIN).run()
btn(at, "Add agent").click().run()
ok(at, "add agent")
assert AGENT in auth.load_agents(), auth.load_agents()
step("Admin adds %s with PIN %s" % (AGENT, PIN))

# ------------------------------------------------------- 3. the agent logs in
at = ok(app(), "login page")
names = [getattr(o, "content", o) for o in at.get("button_group")[1].options]
assert AGENT in names, names
at.get("button_group")[1].set_value(AGENT)
at.text_input(key="pin_agent").input("0000").run()
btn(at, "Log in").click().run()
assert at.session_state.role is None, "wrong PIN let them in"
assert any("does not match" in e.value for e in at.error)
step("Wrong PIN is refused")

at = app()
at.get("button_group")[1].set_value(AGENT)
at.text_input(key="pin_agent").input(PIN).run()
btn(at, "Log in").click().run()
ok(at, "agent login")
assert at.session_state.role == "agent" and at.session_state.agent == AGENT
step("%s logs in" % AGENT)

# ------------------------------------------------------------- 4. the morning
assert "Opening balance" in md(at) and "Start of day" in md(at)
assert not any("Submit final report" in b.label for b in at.button), "evening form shown too early"
assert btn(at, "Save start of day").disabled
step("Morning form only - no evening fields, save disabled")

at = app(role="agent", agent=AGENT, day_key=AGENT + "|" + TODAY)
at.number_input(key="in_opening").set_value(6000.0).run()
at.number_input(key="in_start_km").set_value(52000).run()
assert btn(at, "Save start of day").disabled, "saved without the odometer photo"
step("Numbers alone are not enough - photo still required")

at.session_state.ph_start = odometer(52000)     # the camera fires
at.run()
assert not btn(at, "Save start of day").disabled
btn(at, "Save start of day").click().run()
ok(at, "save start of day")

e = records.load(AGENT, TODAY)
assert e["status"] == "started" and e["startKm"] == 52000
assert e["openingBalance"] == 6000.0 and e["remainingBalance"] == 6000.0
assert e["hasStartPhoto"] and records.photo(AGENT, TODAY, "start")
step("Morning filed: 52,000 km, ₹6,000 opening, photo stored")

# ------------------------------------------- 5. back in the evening, same day
at = ok(app(role="agent", agent=AGENT), "evening form")
assert "Day started at" in md(at) and "Opening balance ₹6,000" in md(at)
assert any("Submit final report" in b.label for b in at.button)
step("Returns that evening - banner shows the morning, full form appears")

at = app(role="agent", agent=AGENT, day_key=AGENT + "|" + TODAY)
at.number_input(key="in_end_km").set_value(52140).run()
assert "140 km" in md(at), "live distance not shown"
step("Distance updates live: 52,140 - 52,000 = 140 km")

at.number_input(key="in_deals").set_value(6).run()
at.number_input(key="in_opening_eve").set_value(6000.0).run()
at.number_input(key="in_spent").set_value(1750.0).run()
assert "4,250" in md(at), "remaining balance not calculated"
step("Remaining balance calculated live: ₹6,000 - ₹1,750 = ₹4,250")

at.number_input(key="in_fuel").set_value(0.0).run()
assert btn(at, "Submit final report").disabled, "submitted without the end photo"

# two differentials, added with the quick-pick chips
at.get("button_group")[-1].set_value("＋ Client A")
at.run()
at.number_input(key="d_amt_0").set_value(1200.0).run()
at.text_input(key="d_id_0").input("ORD-77120").run()
at.text_input(key="d_rmk_0").input("Client A").run()
at.get("button_group")[-1].set_value("＋ Client B")
at.run()
at.number_input(key="d_amt_1").set_value(450.0).run()
at.text_input(key="d_id_1").input("ORD-77121").run()
at.text_input(key="d_rmk_1").input("Client B").run()
assert "1,650" in md(at), "differential total not shown"
step("Two differentials added via chips, total ₹1,650")

assert btn(at, "Submit final report").disabled, "end photo still missing but submit enabled"
at.session_state.ph_end = odometer(52140)
at.run()
assert not btn(at, "Submit final report").disabled
btn(at, "Submit final report").click().run()
ok(at, "submit")
step("Evening submitted")

e = records.load(AGENT, TODAY)
assert e["status"] == "completed" and e["submittedAt"]
assert e["endKm"] == 52140 and e["distance"] == 140
assert e["totalDeals"] == 6 and e["spentAmount"] == 1750.0 and e["fuelAmount"] == 0
assert e["openingBalance"] == 6000.0 and e["remainingBalance"] == 4250.0
assert e["diffTotal"] == 1650.0 and len(e["diffs"]) == 2
assert e["diffs"][0]["dealId"] == "ORD-77120"
assert e["hasStartPhoto"] and e["hasEndPhoto"], "the morning photo was lost on submit"
assert records.photo(AGENT, TODAY, "start") and records.photo(AGENT, TODAY, "end")
step("Record verified, and the morning photo survived the evening write")

at = ok(app(role="agent", agent=AGENT), "summary")
assert "is submitted at" in md(at) and "4,250" in md(at)
assert any("Edit my report" in b.label for b in at.button)
step("Agent sees their summary with an edit option")

# ------------------------------------------------------- 6. admin sees it all
at = ok(app(role="admin", admin_pin=C.admin_pin()), "dashboard")
m = md(at)
for needle in (AGENT, "Total deals executed", "Cash remaining", "4,250", "ORD-77120"):
    assert needle in m, "dashboard missing: " + needle
assert "1 submitted" in m
step("Dashboard shows the day, the cash position and the deal ID")

t = records.totals(records.all_entries())
assert t["deals"] == 6 and t["spent"] == 1750 and t["remaining"] == 4250 and t["diff"] == 1650
step("Totals correct: 6 deals, ₹1,750 spent, ₹4,250 remaining, ₹1,650 differential")

# ------------------------------------------------------------------ 7. export
rows = records.all_entries()
text = export.build_csv(rows).decode("utf-8-sig")
parsed = [r for r in _csv.reader([l for l in text.splitlines() if l.strip()])]
hdr = parsed[0]
it = hdr.index("Row Type")
day = [r for r in parsed if r[it] == "Day"]
diffs = [r for r in parsed if r[it] == "Differential"]
assert len(day) == 1 and len(diffs) == 2, (len(day), len(diffs))
assert day[0][hdr.index("Remaining Balance")] == "4250.0"
assert [r[hdr.index("Deal / Order ID")] for r in diffs] == ["ORD-77120", "ORD-77121"]
assert all(len(r) == len(hdr) for r in parsed)
step("CSV: 1 Day row + 2 Differential rows, one differential per line")

# -------------------------------------------------------- 8. forgot-PIN cycle
at = ok(app(forgot=True), "forgot PIN")
at.get("button_group")[1].set_value(AGENT)
at.text_input(key="pin_reset").input(NEW_PIN).run()
btn(at, "Send request").click().run()
ok(at, "reset requested")
assert AGENT in auth.load_requests()
assert not auth.check_agent(AGENT, NEW_PIN), "PIN changed before the admin approved"
step("%s requests a new PIN - nothing changes yet" % AGENT)

at = ok(app(role="admin", admin_pin=C.admin_pin()), "dashboard with request")
assert "PIN reset request(s) waiting" in md(at)
btn(at, "✅ Approve").click().run()
ok(at, "approve")
assert auth.check_agent(AGENT, NEW_PIN) and not auth.check_agent(AGENT, PIN)
step("Admin approves - old PIN dead, new PIN live")

at = app()
at.get("button_group")[1].set_value(AGENT)
at.text_input(key="pin_agent").input(NEW_PIN).run()
btn(at, "Log in").click().run()
ok(at, "login with new PIN")
assert at.session_state.role == "agent"
step("%s logs in with the new PIN" % AGENT)

# ------------------------------------------------------------- 9. offboarding
at = app(role="admin", admin_pin=C.admin_pin())
at.button(key="rm_" + AGENT).click().run()
assert AGENT in auth.load_agents(), "removed without confirming"
at.button(key="rmy_" + AGENT).click().run()
ok(at, "remove agent")
assert AGENT not in auth.load_agents()
assert not auth.check_agent(AGENT, NEW_PIN), "removed agent can still log in"
assert records.load(AGENT, TODAY) is not None, "their report should be kept"
step("%s removed - login revoked, report retained" % AGENT)

at = ok(app(), "login page")
names = [getattr(o, "content", o) for o in at.get("button_group")[1].options]
assert AGENT not in names
step("Gone from the login screen")

# ------------------------------------------------------------- 10. retention
old = records.blank("Alpha", "2024-01-01")
old["status"] = "completed"
get_store().put_entry(old)
get_store().put_photo("2024-01-01", "Alpha", "start", odometer(1))
assert get_store().get_entry("2024-01-01", "Alpha")
records.all_entries()                      # the admin load performs the purge
assert get_store().get_entry("2024-01-01", "Alpha") is None
assert get_store().get_photo("2024-01-01", "Alpha", "start") is None
step("A record older than %d days is purged, photo and all" % C.RETENTION_DAYS)

print("\n*** END-TO-END JOURNEY PASSED (%d steps) ***" % STEP[0])

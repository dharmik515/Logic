"""Click-through tests: drive the real widgets, not just session_state."""
import os, sys, io
os.environ.setdefault("AGENTS", "Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliet, Kilo")
os.environ.setdefault("QUICK_REMARKS", "Client A, Client B")
os.environ["SQLITE_PATH"] = "data/interact.db"
try: os.remove("data/interact.db")
except OSError: pass
sys.path.insert(0, ".")

# --- work around an AppTest bug: for selection_mode="single" button groups
# (st.pills / st.segmented_control) `value` is a plain string, but indices()
# iterates it as a list, and options are protos rather than strings.
from streamlit.testing.v1.element_tree import ButtonGroup
def _indices(self):
    v = self.value
    if v is None: return []
    if not isinstance(v, (list, tuple)): v = [v]
    norm = lambda o: getattr(o, "content", o)
    opts = [norm(o) for o in self.options]
    return [opts.index(norm(self.format_func(x))) for x in v]
ButtonGroup.indices = property(_indices)
def _set(self, val):
    self._value = val; return self
ButtonGroup.set_value = _set

from streamlit.testing.v1 import AppTest
from lib import config as C, auth, records, images
from PIL import Image

def fresh(**state):
    at = AppTest.from_file("app.py", default_timeout=60)
    for k, v in state.items(): at.session_state[k] = v
    return at.run()

def check(at, label):
    if at.exception:
        print("!! EXCEPTION in", label)
        for ex in at.exception: print("   ", ex.value)
        sys.exit(1)
    print("OK ", label)

def btn(at, text):
    for b in at.button:
        if text in b.label: return b
    raise AssertionError("no button %r in %s" % (text, [b.label for b in at.button]))

buf = io.BytesIO(); Image.new("RGB", (900, 700), (20, 90, 170)).save(buf, "JPEG")
URL = images.to_data_url(buf.getvalue())
d = C.today_str()

# ---- 1. wrong admin PIN is refused ------------------------------------
at = fresh(login_mode="Admin")
at.text_input(key="pin_admin").input("00000").run()
btn(at, "Open dashboard").click().run(); check(at, "admin login - wrong PIN refused")
assert at.session_state.role is None
assert any("Wrong admin PIN" in e.value for e in at.error), [e.value for e in at.error]

# ---- 2. correct admin PIN gets in -------------------------------------
at = fresh(login_mode="Admin")
at.text_input(key="pin_admin").input(C.admin_pin()).run()
btn(at, "Open dashboard").click().run(); check(at, "admin login - correct PIN")
assert at.session_state.role == "admin", at.session_state.role
assert "Admin dashboard" in " ".join(m.value for m in at.markdown)

# ---- 3. agent login: wrong then right ---------------------------------
at = fresh()
at.get("button_group")[1].set_value("Alpha")          # the name pills
at.text_input(key="pin_agent").input("99999").run()
btn(at, "Log in").click().run(); check(at, "agent login - wrong PIN refused")
assert at.session_state.role is None
assert any("does not match" in e.value for e in at.error)

at = fresh()
at.get("button_group")[1].set_value("Alpha")
at.text_input(key="pin_agent").input(C.default_agent_pin()).run()
btn(at, "Log in").click().run(); check(at, "agent login - correct PIN")
assert at.session_state.role == "agent" and at.session_state.agent == "Alpha"

# ---- 4. start of day is blocked until all three are present -----------
at = fresh(role="agent", agent="Alpha")
at.number_input(key="in_start_km").set_value(45231).run()
assert btn(at, "Save start of day").disabled, "save enabled without balance or photo!"
check(at, "start of day - blocked until photo taken")

at = fresh(role="agent", agent="Alpha", ph_start=URL, day_key="Alpha|" + d)
at.number_input(key="in_start_km").set_value(45231).run()
assert btn(at, "Save start of day").disabled, "save enabled without an opening balance!"
check(at, "start of day - blocked without opening balance")

# ---- 5. balance + KM + photo all present -> it saves -------------------
at = fresh(role="agent", agent="Alpha", ph_start=URL, day_key="Alpha|" + d)
at.number_input(key="in_opening").set_value(5000.0).run()
at.number_input(key="in_start_km").set_value(45231).run()
assert not btn(at, "Save start of day").disabled
btn(at, "Save start of day").click().run(); check(at, "start of day - saved")
e = records.load("Alpha", d)
assert e and e["startKm"] == 45231 and e["status"] == "started" and e["hasStartPhoto"]
assert e["openingBalance"] == 5000.0, e["openingBalance"]
assert records.photo("Alpha", d, "start"), "photo not stored"

# ---- 6. evening submit --------------------------------------------------
at = fresh(role="agent", agent="Alpha", ph_end=URL, day_key="Alpha|" + d)
at.number_input(key="in_end_km").set_value(45298).run()
at.number_input(key="in_deals").set_value(4).run()
at.number_input(key="in_spent").set_value(3500).run()
at.number_input(key="in_opening_eve").set_value(5000.0).run()
at.get("button_group")[-1].set_value("＋ Client A")
at.run(); check(at, "differential row added")
at.number_input(key="d_amt_0").set_value(500.0).run()
btn(at, "Submit final report").click().run(); check(at, "final report submitted")
e = records.load("Alpha", d)
assert e["status"] == "completed" and e["distance"] == 67, e
assert e["totalDeals"] == 4 and e["spentAmount"] == 3500
assert e["remainingBalance"] == 1500.0, e["remainingBalance"]
assert e["diffTotal"] == 500 and e["diffs"][0]["remark"] == "Client A", e["diffs"]
assert e["hasStartPhoto"] and e["hasEndPhoto"], "morning photo lost on submit!"
print("     -> dist %s km, deals %s, diff Rs%s, photos start+end kept"
      % (e["distance"], e["totalDeals"], e["diffTotal"]))

# ---- 7. removing a differential row ------------------------------------
at = fresh(role="agent", agent="Alpha", day_key="Alpha|" + d, edit_mode=True,
           diffs=[{"amount": 500.0, "remark": "Client A"}, {"amount": 300.0, "remark": "Client B"}])
before = len(at.number_input)
btn(at, "🗑 Remove").click().run(); check(at, "differential row removed")
assert len(at.number_input) == before - 1, (before, len(at.number_input))

# ---- 8. forgot-PIN, end to end, through the UI -------------------------
at = fresh(forgot=True)
at.get("button_group")[1].set_value("Delta")
at.text_input(key="pin_reset").input("7788").run()
btn(at, "Send request").click().run(); check(at, "PIN reset requested")
assert "Delta" in auth.load_requests()
assert not auth.check_agent("Delta", "7788"), "PIN changed before approval!"

at = fresh(role="admin", admin_pin=C.admin_pin())
assert "PIN reset request(s) waiting" in " ".join(m.value for m in at.markdown)
btn(at, "✅ Approve").click().run(); check(at, "admin approved the request")
assert auth.check_agent("Delta", "7788"), "approval did not apply the PIN"
assert auth.load_requests() == {}
print("     -> Delta can now log in with 7788")

# ---- 9. admin sets a PIN directly --------------------------------------
at = fresh(role="admin", admin_pin=C.admin_pin())
at.text_input(key="pin_Foxtrot").input("4242").run()
at.button(key="sv_Foxtrot").click().run(); check(at, "admin set a PIN directly")
assert auth.check_agent("Foxtrot", "4242")

# ---- 10. logout clears the session -------------------------------------
at = fresh(role="agent", agent="Alpha", day_key="Alpha|" + d)
btn(at, "Log out").click().run(); check(at, "logout")
assert at.session_state.role is None
assert "agent" not in at.session_state or at.session_state["agent"] is None
assert "day_key" not in at.session_state, "stale day state survived logout"

print("\n*** ALL INTERACTION TESTS PASSED ***")

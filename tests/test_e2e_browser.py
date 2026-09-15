"""End to end in a real browser, at phone size.

The AppTest suite calls Streamlit's callbacks directly, so it can never catch a
button that renders but cannot be *pressed* - which is exactly how the Log out
button broke (Streamlit's toolbar sat on top of it at z-index 999990). This
test drives actual mouse clicks and keystrokes in headless Chrome at 390x844,
so a covered, mis-sized or off-screen control fails the run.

Chrome is launched with a synthetic camera (--use-fake-device-for-media-stream),
so st.camera_input really captures and the photo really uploads - no seam.

Needs Chrome. Run from the project root:

    python tests/test_e2e_browser.py
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

os.environ.setdefault("ADMIN_PIN", "246810")
os.environ.setdefault("AGENT_PIN", "123456")
os.environ.setdefault("AGENTS", "Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel, India, Juliet, Kilo")
os.environ.setdefault("QUICK_REMARKS", "Client A, Client B")
os.environ["SQLITE_PATH"] = "data/e2e_browser.db"
sys.path.insert(0, ".")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

from tornado.ioloop import IOLoop
from tornado.websocket import websocket_connect

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
PORT, CDP_PORT = 8733, 9455
PROFILE = os.path.join(tempfile.gettempdir(), "dar_e2e_profile")
WIDTH, HEIGHT = 390, 844          # iPhone-ish portrait

STEP = [0]


def step(msg):
    STEP[0] += 1
    print("%2d. %s" % (STEP[0], msg))


class Page:
    """Just enough of a browser driver for this one journey."""

    def __init__(self, conn):
        self.conn, self.n = conn, 0

    async def cmd(self, method, **params):
        self.n += 1
        await self.conn.write_message(json.dumps(
            {"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.conn.read_message())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError("%s -> %s" % (method, msg["error"]))
                return msg.get("result", {})

    async def js(self, expression):
        r = await self.cmd("Runtime.evaluate", expression=expression,
                           returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(r["exceptionDetails"].get("text"))
        return r["result"].get("value")

    async def until(self, expression, what, timeout=25):
        """Poll a JS predicate until it is true."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if await self.js("!!(%s)" % expression):
                return True
            await asyncio.sleep(0.4)
        body = (await self.text() or "").replace("\n", " | ")[:700]
        raise AssertionError("timed out waiting for %s\n    page said: %s" % (what, body))

    async def text(self):
        return await self.js("document.body.innerText")

    # -- interaction -------------------------------------------------------
    async def _rect(self, js_element):
        """Scroll an element into view and return its viewport-centre point."""
        return await self.js("""(() => {
          const el = %s;
          if (!el) return null;
          el.scrollIntoView({block: 'center', inline: 'center'});
          const r = el.getBoundingClientRect();
          if (r.width < 1 || r.height < 1) return null;
          const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
          const hit = document.elementFromPoint(cx, cy);
          const reachable = !!(hit && (hit === el || el.contains(hit)));
          let blocker = null;
          if (!reachable && hit) {
            // walk up to whatever is actually positioned, so the report names
            // the element whose CSS needs changing
            let n = hit, pos = null;
            while (n && getComputedStyle(n).position === 'static') n = n.parentElement;
            const hr = (n || hit).getBoundingClientRect();
            blocker = {
              testid: (n || hit).getAttribute('data-testid') || (n || hit).tagName,
              cls: ((n || hit).className || '').toString().slice(0, 50),
              position: n ? getComputedStyle(n).position : 'static',
              top: Math.round(hr.top), bottom: Math.round(hr.bottom),
              left: Math.round(hr.left), right: Math.round(hr.right),
              z: n ? getComputedStyle(n).zIndex : 'auto'
            };
          }
          return {x: cx, y: cy, reachable: reachable,
                  by: hit ? (hit.getAttribute('data-testid') || hit.tagName) : 'nothing',
                  target: {top: Math.round(r.top), bottom: Math.round(r.bottom)},
                  blocker: blocker};
        })()""" % js_element)

    async def settle(self, timeout=7):
        """Let any toast expire before hit-testing.

        A toast is meant to be transient, so waiting for it mirrors what a user
        does. If one never clears, the reachability check below still fails -
        which is the case we actually care about.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not await self.js("!!document.querySelector('[data-testid=\"stToast\"]')"):
                return
            await asyncio.sleep(0.4)

    async def click(self, js_element, label, timeout=15):
        """Wait for the control to exist, then click it for real."""
        await self.settle()
        deadline = time.time() + timeout
        box = None
        while time.time() < deadline:
            box = await self._rect(js_element)
            if box:
                break
            await asyncio.sleep(0.4)
        if not box:
            raise AssertionError("cannot find %s after %ds" % (label, timeout))

        # The whole point of this suite: a control that renders but is covered
        # is a failure, not something to work around.
        assert box["reachable"], \
            "%s is covered by <%s> - a real tap would not reach it" % (label, box["by"])

        for kind in ("mousePressed", "mouseReleased"):
            await self.cmd("Input.dispatchMouseEvent", type=kind, x=box["x"], y=box["y"],
                           button="left", clickCount=1)
        await asyncio.sleep(1.4)          # let Streamlit rerun

    async def click_button(self, text, label=None):
        await self.click(
            "[...document.querySelectorAll('button')].find(b => (b.textContent||'').includes(%s))"
            % json.dumps(text), label or "button %r" % text)

    async def press_enter(self):
        # text="\r" matters: without it React never sees a keypress and the
        # widget sits on "Press Enter to apply" forever.
        for kind in ("keyDown", "char", "keyUp"):
            args = dict(type=kind, key="Enter", code="Enter",
                        windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)
            if kind in ("keyDown", "char"):
                args["text"] = "\r"
            await self.cmd("Input.dispatchKeyEvent", **args)

    async def fill(self, key, value):
        """Type into the input Streamlit rendered for `key`, and make sure the
        value is actually committed - not left pending on 'Press Enter'."""
        sel = json.dumps(".st-key-%s input" % key)
        container = json.dumps(".st-key-%s" % key)
        await self.click("document.querySelector(%s)" % sel, "field %r" % key)
        await self.js("(() => { const el = document.querySelector(%s); el.focus(); el.select(); })()" % sel)
        await self.cmd("Input.insertText", text=str(value))
        await self.press_enter()
        await asyncio.sleep(1.2)

        pending = "(document.querySelector(%s)||{innerText:''}).innerText.includes('Press Enter')" % container
        if await self.js(pending):
            # Fall back to a blur, which Streamlit also treats as a commit.
            await self.js("(() => { const el = document.querySelector(%s); el && el.blur(); })()" % sel)
            await asyncio.sleep(1.2)
        assert not await self.js(pending), \
            "%r would not commit - it is still showing 'Press Enter to apply'" % key


async def connect():
    for _ in range(50):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json" % CDP_PORT, timeout=2) as r:
                for t in json.load(r):
                    if t.get("type") == "page":
                        return Page(await websocket_connect(t["webSocketDebuggerUrl"]))
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("Chrome did not come up")


async def journey():
    from lib import config as C, records

    agent, today = "Alpha", C.today_str()
    p = await connect()
    await p.cmd("Page.enable")
    await p.cmd("Emulation.setDeviceMetricsOverride", width=WIDTH, height=HEIGHT,
                deviceScaleFactor=2, mobile=True)
    await p.cmd("Page.navigate", url="http://localhost:%d/" % PORT)
    await p.until("document.body.innerText.includes('Daily Agent Report')", "the login screen")
    step("Login screen loads at %dx%d" % (WIDTH, HEIGHT))

    # ---------------------------------------------------------------- login
    await p.click(
        "[...document.querySelectorAll('.st-key-pick_agent button')]"
        ".find(b => b.textContent.trim() === 'Alpha')", "the name chip 'Alpha'")
    await p.fill("pin_agent", C.default_agent_pin())
    await p.click_button("Log in")
    await p.until("document.body.innerText.includes('Start of day')", "the morning form")
    step("Tapped the name chip, typed the PIN, logged in")

    # -------------------------------------------------------------- morning
    body = await p.text()
    assert "Opening balance" in body and "Submit final report" not in body
    step("Morning form only - no evening fields on screen")

    await p.fill("in_opening", "5000")
    await p.fill("in_start_km", "41000")
    assert await p.js(
        "[...document.querySelectorAll('button')]"
        ".find(b => b.textContent.includes('Save start of day')).disabled"), \
        "save was enabled before the photo was taken"
    step("Typed ₹5,000 opening and 41,000 km - save still blocked, no photo yet")

    await p.until("document.querySelector('[data-testid=\"stCameraInput\"] video')",
                  "the camera preview")
    await p.click_button("Take Photo")
    await p.until("document.body.innerText.includes('Photo ready')", "the captured photo")
    step("Camera captured a real photo through the browser")

    await p.click_button("Save start of day")
    await p.until("document.body.innerText.includes('End of day')", "the evening form")
    e = records.load(agent, today)
    assert e and e["startKm"] == 41000 and e["openingBalance"] == 5000.0
    assert e["hasStartPhoto"] and records.photo(agent, today, "start")
    step("Morning saved - 41,000 km, ₹5,000, photo stored in the database")

    # -------------------------------------------------------------- evening
    await p.fill("in_end_km", "41155")
    await p.until("document.body.innerText.includes('155 km')", "the live distance")
    step("Distance computed live on screen: 155 km")

    await p.fill("in_deals", "4")
    await p.fill("in_opening_eve", "5000")
    await p.fill("in_spent", "1250")
    await p.until("document.body.innerText.includes('3,750')", "the remaining balance")
    step("Remaining balance computed live on screen: ₹3,750")

    await p.fill("in_fuel", "0")
    await p.click(
        "[...document.querySelectorAll('button')].find(b => b.textContent.includes('Client A'))",
        "the '+ Client A' chip")
    await p.fill("d_amt_0", "900")
    await p.fill("d_id_0", "ORD-55012")
    await p.until("document.body.innerText.includes('900')", "the differential total")
    step("Added a differential from the chip: ₹900, ORD-55012")

    await p.until("document.querySelector('[data-testid=\"stCameraInput\"] video')",
                  "the end-odometer camera")
    await p.click_button("Take Photo")
    await p.until("document.body.innerText.includes('Photo ready')", "the second photo")

    # If anything is still outstanding the button is disabled and the page says
    # so - surface that instead of silently clicking a dead control.
    still_needed = await p.js(
        "(document.body.innerText.match(/Still needed:[^\\n]*/) || [''])[0]")
    values = await p.js("""(() => {
      const out = {};
      document.querySelectorAll('[class*="st-key-in_"], [class*="st-key-d_"]').forEach(c => {
        const k = [...c.classList].find(x => x.startsWith('st-key-'));
        const i = c.querySelector('input');
        if (k && i) out[k.replace('st-key-', '')] = i.value;
      });
      return out;
    })()""")
    # Regression guard: taking this photo used to wipe the fields below it.
    assert not still_needed, (
        "form still incomplete after the photo: %s\n    values on screen: %s\n"
        "    (a mid-script st.rerun() in the photo widget once discarded these)"
        % (still_needed, values))

    await p.click_button("Submit final report")
    await p.until("document.body.innerText.includes('is submitted at')", "the summary screen")
    step("Second photo captured, report submitted")

    e = records.load(agent, today)
    assert e["status"] == "completed" and e["distance"] == 155
    assert e["totalDeals"] == 4 and e["remainingBalance"] == 3750.0
    assert e["diffTotal"] == 900.0 and e["diffs"][0]["dealId"] == "ORD-55012"
    assert e["hasStartPhoto"] and e["hasEndPhoto"], "a photo was lost"
    step("Record verified end to end, both photos on file")

    # --------------------------------------------------------- LOG OUT (!)
    # The regression this suite exists for.
    await p.click_button("Log out")
    await p.until("document.body.innerText.includes('Who is reporting')",
                  "the login screen after logging out")
    step("Log out works at phone width and returns to the login screen")

    # ----------------------------------------------------------------- admin
    await p.click(
        "[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Admin')",
        "the Admin toggle")
    await p.fill("pin_admin", C.admin_pin())
    await p.click_button("Open dashboard")
    await p.until("document.body.innerText.includes('Admin dashboard')", "the dashboard")
    # CSS uppercases the tile labels, and innerText returns the transformed
    # text - so compare case-insensitively.
    await p.until("document.body.innerText.toLowerCase().includes('total deals executed')",
                  "the dashboard summary tiles")
    step("Admin logged in on the same phone screen")

    # The per-agent cards paint after the tiles and charts, so wait for the
    # last thing to arrive rather than reading the page mid-render.
    await p.until("document.body.innerText.toLowerCase().includes('ord-55012')",
                  "the agent card with the deal ID")
    body = (await p.text() or "").lower()
    for needle in ("total deals executed", "cash remaining", "3,750", "ord-55012"):
        assert needle in body, "dashboard is missing %r" % needle
    step("Dashboard shows the day, the cash position and the deal ID")

    await p.click_button("Log out")
    await p.until("document.body.innerText.includes('Who is reporting')", "the login screen")
    step("Admin log out works too")

    print("\n*** BROWSER END-TO-END PASSED (%d steps, %dx%d) ***" % (STEP[0], WIDTH, HEIGHT))


if __name__ == "__main__":
    chrome = next((c for c in CHROME_CANDIDATES if os.path.exists(c)), None)
    if not chrome:
        print("Chrome/Edge not found - install one or edit CHROME_CANDIDATES.")
        sys.exit(2)

    for f in ("data/e2e_browser.db",):
        try: os.remove(f)
        except OSError: pass

    server = browser = None
    try:
        env = dict(os.environ, SQLITE_PATH="data/e2e_browser.db")
        server = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py",
             "--server.headless", "true", "--server.port", str(PORT),
             "--browser.gatherUsageStats", "false"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(90):
            try:
                if urllib.request.urlopen("http://localhost:%d/" % PORT, timeout=2).status == 200:
                    break
            except Exception:
                time.sleep(0.5)
        else:
            print("the app did not start"); sys.exit(2)

        browser = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--use-fake-device-for-media-stream",   # a synthetic camera...
             "--use-fake-ui-for-media-stream",       # ...auto-granted
             "--autoplay-policy=no-user-gesture-required",
             "--remote-debugging-port=%d" % CDP_PORT,
             "--user-data-dir=%s" % PROFILE, "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print("\n=== BROWSER END TO END (%dx%d, synthetic camera) ===\n" % (WIDTH, HEIGHT))
        IOLoop.current().run_sync(journey)
    finally:
        if server: server.terminate()
        if browser: browser.terminate()
        time.sleep(1)
        try: os.remove("data/e2e_browser.db")
        except OSError: pass
        shutil.rmtree(PROFILE, ignore_errors=True)

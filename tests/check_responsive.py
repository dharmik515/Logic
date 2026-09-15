"""Measured responsiveness check - a real browser at real widths.

Loads each screen in headless Chrome and, at every width, measures:

  * horizontal overflow  - does the page scroll sideways? (hard fail)
  * overflowing elements - anything sticking out past the right edge
  * tap targets          - buttons under 40px tall (hard fail on phones)
  * input font size      - under 16px makes iOS zoom on focus (hard fail)
  * hit testing          - is each button actually reachable, or is an overlay
                           swallowing the click? (hard fail)

Needs Chrome installed. Run from the project root:

    python tests/check_responsive.py

It starts its own Streamlit servers and its own Chrome, seeds a throwaway
database, and cleans all of it up afterwards.
"""
import asyncio
import io
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
os.environ["SQLITE_PATH"] = "data/responsive.db"
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

# (label, width, is_phone)
WIDTHS = [
    ("phone-small  320", 320, True),
    ("phone        390", 390, True),
    ("phone-large  430", 430, True),
    ("tablet       768", 768, False),
    ("tablet-land 1024", 1024, False),
    ("laptop      1440", 1440, False),
]

CDP_PORT = 9444
PROFILE = os.path.join(tempfile.gettempdir(), "dar_resp_profile")

MEASURE_JS = r"""
(() => {
  const vw = window.innerWidth;
  const de = document.documentElement;
  const scrollable = el => {
    for (let n = el; n; n = n.parentElement) {
      const o = getComputedStyle(n).overflowX;
      if (o === 'auto' || o === 'scroll') return true;
    }
    return false;
  };
  const offenders = [];
  document.querySelectorAll('body *').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    if (r.right > vw + 1.5 && !scrollable(el)) {
      offenders.push({
        tag: el.tagName,
        testid: el.getAttribute('data-testid') || '',
        right: Math.round(r.right),
        width: Math.round(r.width),
        text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 34)
      });
    }
  });
  // Only the app's own controls. Streamlit's internal chrome - the header
  // button and the hover toolbars on charts/dataframes (Fullscreen, Search,
  // Download) - is 22-28px by design and not ours to size.
  const CHROME = ['elementToolbar', 'headerNoPadding'];
  const small = [];
  document.querySelectorAll('button').forEach(b => {
    const r = b.getBoundingClientRect();
    if (r.height < 1) return;
    if (CHROME.includes(b.getAttribute('kind'))) return;
    if (b.closest('[data-testid="stHeader"]')) return;
    if (r.height < 44) {
      small.push({
        text: (b.textContent || '').trim().slice(0, 20) || (b.getAttribute('aria-label') || '?'),
        kind: b.getAttribute('kind') || '',
        h: Math.round(r.height)
      });
    }
  });
  const tiny = [];
  document.querySelectorAll('input').forEach(i => {
    if (i.type === 'hidden' || i.offsetParent === null) return;
    const fs = parseFloat(getComputedStyle(i).fontSize);
    if (fs < 16) tiny.push({ type: i.type, fs: fs });
  });
  // Is each button actually reachable, or is an overlay eating the click?
  // Streamlit's toolbar sits at z-index 999990 and once swallowed Log out.
  const blocked = [];
  document.querySelectorAll('button').forEach(b => {
    if (CHROME.includes(b.getAttribute('kind'))) return;
    if (b.closest('[data-testid="stHeader"]')) return;
    const r = b.getBoundingClientRect();
    if (r.height < 1 || r.width < 1) return;
    if (r.top < 0 || r.bottom > window.innerHeight) return;   // off-screen: can't hit-test
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!hit || !(hit === b || b.contains(hit))) {
      blocked.push({
        text: (b.textContent || '').trim().slice(0, 20) || (b.getAttribute('aria-label') || '?'),
        by: hit ? (hit.getAttribute('data-testid') || hit.tagName) : 'nothing'
      });
    }
  });
  return {
    vw: vw,
    scrollW: de.scrollWidth,
    overflow: de.scrollWidth > vw + 1,
    offenders: offenders.slice(0, 6),
    small: small.slice(0, 4),
    tiny: tiny.slice(0, 4),
    blocked: blocked.slice(0, 4),
    widgets: document.querySelectorAll('[data-testid="stButton"], input').length
  };
})()
"""


# ----------------------------------------------------------------- CDP client
class Chrome:
    def __init__(self, conn):
        self.conn = conn
        self.n = 0

    async def cmd(self, method, **params):
        self.n += 1
        await self.conn.write_message(json.dumps(
            {"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.conn.read_message())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})


async def connect():
    for _ in range(40):
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % CDP_PORT, timeout=2) as r:
                for t in json.load(r):
                    if t.get("type") == "page":
                        return Chrome(await websocket_connect(t["webSocketDebuggerUrl"]))
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("could not reach Chrome on port %d" % CDP_PORT)


# --------------------------------------------------------------------- seeding
def seed():
    from PIL import Image, ImageDraw
    from lib import auth, config as C, images, records

    def shot(km):
        im = Image.new("RGB", (800, 320), (26, 30, 42))
        ImageDraw.Draw(im).text((110, 150), "  %s km" % format(km, ","), fill=(130, 220, 255))
        b = io.BytesIO(); im.save(b, "JPEG")
        return images.to_data_url(b.getvalue())

    d = C.today_str()
    auth.load_pins()
    roster = auth.load_agents()
    long_name = "Hotel"                      # longest default name
    for i, a in enumerate(roster[:6]):
        records.save_start(a, d, 40000 + i * 900, shot(40000 + i * 900),
                           opening_balance=5000 + i * 250)
        if i < 4:
            records.save_final(
                a, d, end_km=40000 + i * 900 + 120, total_deals=3 + i,
                fuel_amount=0 if i % 2 else 900, spent_amount=1200 + i * 310,
                opening_balance=5000 + i * 250, photo_end=shot(40000 + i * 900 + 120),
                diffs=[{"amount": 1250, "dealId": "ORD-635269", "remark": "Client A"},
                       {"amount": 480, "dealId": "ORD-123456-894983", "remark": "Client B"}])
    auth.request_reset(long_name, "7788")
    return roster


# ------------------------------------------------------------------ orchestrate
def start_server(port, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    env["SQLITE_PATH"] = "data/responsive.db"
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "tests/_harness_app.py",
         "--server.headless", "true", "--server.port", str(port),
         "--browser.gatherUsageStats", "false"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_http(port, timeout=45):
    for _ in range(timeout * 2):
        try:
            with urllib.request.urlopen("http://localhost:%d/" % port, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


async def audit(chrome, url, label, results):
    await chrome.cmd("Page.enable")
    await chrome.cmd("Emulation.setDeviceMetricsOverride",
                     width=1440, height=900, deviceScaleFactor=1, mobile=False)
    await chrome.cmd("Page.navigate", url=url)
    await asyncio.sleep(11)          # let the websocket paint the page

    print("\n%s" % label)
    print("   %-18s %-9s %-10s %-11s %-9s"
          % ("width", "overflow", "tap<44px", "input<16px", "clickable"))
    for wlabel, width, is_phone in WIDTHS:
        await chrome.cmd("Emulation.setDeviceMetricsOverride",
                         width=width, height=900, deviceScaleFactor=1, mobile=is_phone)
        await asyncio.sleep(1.4)
        r = (await chrome.cmd("Runtime.evaluate", expression=MEASURE_JS,
                              returnByValue=True))["result"]["value"]

        problems = []
        if r["overflow"]:
            problems.append("page scrolls sideways (%dpx > %dpx)" % (r["scrollW"], r["vw"]))
            for o in r["offenders"]:
                problems.append("   overflows: <%s %s> w=%d right=%d  %r"
                                % (o["tag"], o["testid"], o["width"], o["right"], o["text"]))
        if r["small"]:
            problems.append("tap targets under 44px: %s" % r["small"])
        if r["tiny"]:
            problems.append("inputs under 16px (iOS will zoom): %s" % r["tiny"])
        if r["blocked"]:
            for b in r["blocked"]:
                problems.append("button %r is covered by <%s> - the click will not land"
                                % (b["text"], b["by"]))

        print("   %-18s %-9s %-10s %-11s %-9s %s"
              % (wlabel,
                 "FAIL" if r["overflow"] else "ok",
                 "FAIL" if r["small"] else "ok",
                 "FAIL" if r["tiny"] else "ok",
                 "FAIL" if r["blocked"] else "ok",
                 "" if not problems else "<-- see below"))
        for p in problems:
            print("        %s" % p)
        results.append((label, wlabel, not problems))


async def main(urls):
    chrome = await connect()
    results = []
    for label, url in urls:
        await audit(chrome, url, label, results)
    return results


if __name__ == "__main__":
    chrome_exe = next((p for p in CHROME_CANDIDATES if os.path.exists(p)), None)
    if not chrome_exe:
        print("Chrome/Edge not found - install one or edit CHROME_CANDIDATES.")
        sys.exit(2)

    for f in ("data/responsive.db",):
        try: os.remove(f)
        except OSError: pass

    print("seeding a throwaway database ...")
    roster = seed()
    started, procs = [], []
    browser = None
    try:
        screens = [
            ("LOGIN", 8701, {"SHOT_ROLE": ""}),
            ("AGENT - morning (nothing filed yet)", 8702,
             {"SHOT_ROLE": "agent", "SHOT_AGENT": roster[8]}),
            ("AGENT - evening (morning on file)", 8703,
             {"SHOT_ROLE": "agent", "SHOT_AGENT": roster[4]}),
            ("AGENT - submitted summary", 8704,
             {"SHOT_ROLE": "agent", "SHOT_AGENT": roster[0]}),
            ("ADMIN - dashboard", 8705, {"SHOT_ROLE": "admin"}),
        ]
        for label, port, env in screens:
            procs.append(start_server(port, env))
        print("starting %d servers ..." % len(screens))
        for label, port, _ in screens:
            if not wait_http(port):
                print("server for %s did not start" % label)
                sys.exit(2)

        browser = subprocess.Popen(
            [chrome_exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--remote-debugging-port=%d" % CDP_PORT,
             "--user-data-dir=%s" % PROFILE, "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        urls = [(label, "http://localhost:%d/" % port) for label, port, _ in screens]
        results = IOLoop.current().run_sync(lambda: main(urls))

        bad = [(s, w) for s, w, good in results if not good]
        print("\n" + "=" * 68)
        if bad:
            print("RESPONSIVE CHECK FAILED - %d of %d combinations"
                  % (len(bad), len(results)))
            for s, w in bad:
                print("   %s @ %s" % (s, w))
            sys.exit(1)
        print("RESPONSIVE CHECK PASSED - %d screens x %d widths: no overflow, no "
              "small tap targets, no zooming inputs, every button clickable"
              % (len(urls), len(WIDTHS)))
    finally:
        for p in procs:
            p.terminate()
        if browser:
            browser.terminate()
        time.sleep(1)
        for f in ("data/responsive.db",):
            try: os.remove(f)
            except OSError: pass
        shutil.rmtree(PROFILE, ignore_errors=True)

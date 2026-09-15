# Daily Agent Report

A field team's daily log, built as a Streamlit app. Eleven agents file one report
a day from their phones — odometer readings (typed **and** photographed), deals
done, fuel, cash spent and any differential collected. An admin reviews
everything, views the photos and downloads a CSV. No accounts: access is by name
+ PIN. Data is kept for a rolling 30 days.

---

## Quick start (local)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501.

**There is no PIN anywhere in this repository.** The source is public, so a PIN
in it would be a published password. Until you set `ADMIN_PIN` in secrets the
dashboard cannot be opened by anyone, and agents who have not been given a PIN
get a random one that only the admin can see.

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, set
`ADMIN_PIN`, and you are running. The roster is in
[`lib/config.py`](lib/config.py); PINs are in secrets, never here.

---

## The two-stage day

| When | The agent does | Stored as |
|---|---|---|
| Morning | Enters the **opening balance** (cash in hand), then **Starting KM** and a photo of the odometer. Nothing else is shown. | `status: "started"` |
| Evening | **Ending KM** + photo, deals done, fuel (+ receipt), cash spent, differential rows. | `status: "completed"` |

### Cash

The morning captures the **opening balance**; the evening captures **total spent**.
**Remaining balance is derived, never typed** — `opening − spent`, shown live as the
agent types and recomputed on save. It is allowed to go negative: an agent who
spent more than their float used their own money, and the dashboard flags that
rather than hiding it. The opening balance stays editable in the evening in case
it was entered wrong.

Each **differential** row carries an amount, a **Deal / Order ID** and a remark,
with quick-add chips for the common sources.

### Every field is mandatory - and 0 counts

The evening form will not submit until every box has a value. **0 is a perfectly
good answer**; what is not allowed is leaving a box blank, because then nobody
can tell whether the agent meant zero or simply skipped it. The button stays
disabled and lists exactly what is still missing. A fuel amount above 0 also
requires the receipt photo, and a differential row must have all three of its
parts filled in.

Both KM readings need **a typed number and a photo** — the number is what gets
reported, the photo is the proof behind it. Distance is computed as
`max(0, endKm − startKm)`; nothing is ever read out of a photo.

**Photos must be taken in the app.** There is no upload option anywhere: the
only way to attach a photo is the live camera, so what is stored is the
odometer as it was at that moment rather than a file that could have come from
anywhere, been reused from another day, or been taken by someone else. The
practical consequence is that an agent who blocks camera permission cannot
file a report — see Known limitations.

Agents can reopen and edit their own report for the same day.

### Forgot a PIN

The agent taps **Forgot my PIN**, picks their name and the new PIN they want, and
sends the request. **Nothing changes until the admin approves it** in
*Agent PINs & reset requests*. The admin can also set any PIN directly.

---

## What you still need to do

Ordered by how much it matters.

### 1. Give it a real database — required before real use

Out of the box the app writes to a local SQLite file (`data/reports.db`). That is
perfect on a laptop or a VM, **but Streamlit Community Cloud wipes the container
disk whenever the app sleeps, reboots or is redeployed** — you would lose the
month's reports and every photo. The admin dashboard shows a warning banner
whenever the app is running this way.

**The fix takes about three minutes and costs nothing:**

1. Create a free Postgres — [Neon](https://neon.tech),
   [Supabase](https://supabase.com) or [Railway](https://railway.app) all work.
2. Copy the connection string it gives you. It looks like
   `postgresql://user:password@host/dbname?sslmode=require`.
3. Paste it into the app's secrets as `DATABASE_URL` and reboot.

That is the whole setup — **the app creates its own tables on first connect**, so
there is no SQL to run by hand. The warning banner disappears once it is live,
and the dashboard header tells you which backend is in use.

A free tier is far more than this app needs: photos are ~100–250 KB each and
only 30 days are ever kept, so a full team of 11 sits comfortably inside a
500 MB allowance.

> The connection string is a credential — it belongs only in Streamlit secrets,
> never in the repo. `.gitignore` already excludes `.streamlit/secrets.toml`.

<details>
<summary>Using Supabase's REST API instead of a direct connection</summary>

If your network blocks direct Postgres connections, the app can talk to
Supabase over HTTPS instead. Set `SUPABASE_URL` and `SUPABASE_KEY`
(service_role) rather than `DATABASE_URL`, and create the tables yourself in
the Supabase SQL editor:

```sql
create table entries (
  date text not null, agent text not null, payload jsonb not null,
  primary key (date, agent));
create table photos (
  date text not null, agent text not null, which text not null,
  payload text not null, primary key (date, agent, which));
create table config (key text primary key, payload jsonb not null);
```
</details>

### 2. Set the admin PIN

`ADMIN_PIN` is required — there is no fallback in the source, so the dashboard
refuses every login until you set one.

For the strongest setup, store a *hash* instead, so not even your secrets hold
the password:

```bash
python tools/make_pin_hash.py      # prompts, echoes nothing, prints a hash
```

Paste the result as `ADMIN_PIN_HASH` and drop the `ADMIN_PIN` line.

**Agent PINs need no configuration at all.** Each agent gets a random one on
first run; add someone from the dashboard and you see their PIN once, as you
type it. `AGENT_PINS = "Sultan:1111, Ifham:2222"` is there if you want to
pre-set them, and can be deleted once the app has started.

### 3. Check the roster

The starting team is the list in [`lib/config.py`](lib/config.py) — names only,
no PINs. After first run the team is managed from the dashboard: **Team, PINs & reset requests** →
**Add an agent** (name + starting PIN), or **Remove** next to anyone who has
left. Removing takes a second confirming click, revokes their login and clears
their PIN - but **their reports from the last 30 days are deliberately kept**,
because they are part of the record.

`DEFAULT_AGENTS` in [`lib/config.py`](lib/config.py) is only the seed used on
first run. After that the live roster lives in the store, so editing that list
later changes nothing - use the dashboard.

### 4. Confirm the timezone

`APP_TIMEZONE` defaults to `Asia/Kolkata`. It decides when "today" rolls over,
which is what separates one day's report from the next.

### 5. Decide about data residency

Reports and photos live wherever you host them (Streamlit Community Cloud, or
your Supabase project's region). Keep the form to **operational numbers only** —
no customer names, phone numbers, IDs, IMEIs or payment details. If your
organisation has a DPO, route the hosting region past them before rollout.

### Optional

* **A real domain.** Community Cloud gives you `*.streamlit.app`, which is fine
  to share.
* **Odometer OCR.** Deliberately not included: agents type the KM, so reading the
  photo automatically would add an API bill and a new failure mode for no gain.
  The data model has room for it if you ever want it.
* **Hashed PINs / rate limiting.** See [Security](#security).

---

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repo (public or private).
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**, pick the
   repo, set the main file to `app.py`, deploy.
3. Open **App settings → Secrets** and paste:

   ```toml
   ADMIN_PIN = "your-admin-pin"
   AGENT_PIN = "seed-pin-for-new-agents"
   APP_TIMEZONE = "Asia/Kolkata"

   DATABASE_URL = "postgresql://user:password@host/dbname?sslmode=require"
   ```
4. Reboot the app, then share the URL with the team.

The camera needs HTTPS, which Community Cloud provides. On the first photo each
agent's browser asks for camera permission — they must tap **Allow**. Since
uploads are disabled, **camera permission is not optional**: an agent who
denies it cannot file a report until they re-enable it in their browser's site
settings. Worth saying once in the rollout message.

---

## Configuration

Every setting reads from **secrets first, then environment variables, then a
built-in default**, so nothing has to be edited in code.

| Key | Purpose | Default |
|---|---|---|
| `ADMIN_PIN` | Admin dashboard PIN — **required**, nothing works without it | none |
| `AGENT_PINS` | Per-agent PINs: `"Sultan:1111, Ifham:2222"` | none |
| `AGENT_PIN` | One shared starting PIN instead of the above | none → random per agent |
| `AGENTS` | Override the roster, comma separated | the list in `lib/config.py` |
| `QUICK_REMARKS` | Override the differential quick-picks | `Samsung, Amazon` |
| `APP_TIMEZONE` | Decides when "today" rolls over | `Asia/Kolkata` |
| `DATABASE_URL` | Postgres connection string — **the recommended storage** | unset (SQLite) |
| `SUPABASE_URL` / `SUPABASE_KEY` | Supabase over REST, as an alternative | unset |
| `SQLITE_PATH` | Where the local SQLite file lives | `data/reports.db` |

`.streamlit/secrets.toml.example` is a copy-paste starting point.

> **Gotcha:** `AGENT_PIN` only fills in agents who have *no* PIN yet. Changing it
> later will not rewrite agents who already have one — change those in the
> **Team, PINs & reset requests** panel.

> **Gotcha:** `AGENTS` seeds the roster on the *first run only*. After that the
> admin panel owns it, and editing the secret changes nothing. Leaving `AGENTS`
> unset and adding the team from the dashboard is the recommended setup — it
> keeps your colleagues' names out of both the repo and the config.

---

## Responsiveness

Built mobile-first and checked at phone, tablet and laptop widths:

* Stat tiles and the hero are CSS grid with `auto-fit`, so they reflow from five
  across to two across to one without any breakpoint juggling.
* Streamlit columns are allowed to **wrap** below 760px and stack fully below
  420px, so two short fields stay side by side on a mid-size phone but never get
  squeezed on a small one.
* All inputs are 16px, which stops iOS zooming in when a field is focused; every
  tap target is at least 44–48px tall.
* The name picker and the differential quick-adds are wrapping chips, not
  fixed-width column grids.
* Safe-area padding for notched phones; `prefers-reduced-motion` is respected.

All of this is measured, not assumed: `python tests/check_responsive.py` loads
every screen at 320, 390, 430, 768, 1024 and 1440px in a real browser and fails
on sideways scrolling, small tap targets or zoom-triggering inputs. Currently
30/30 clean.

The theme is pinned to light in `.streamlit/config.toml` so the custom CSS and
Streamlit's own widgets can never disagree — a field app also reads better in
sunlight. To go dark, change `base` there and swap the token block at the top of
[`lib/ui.py`](lib/ui.py).

---

## Project layout

```
app.py                  entry point, session, routing, top bar
lib/
  config.py             roster, PINs, retention, timezone helpers
  storage.py            SQLite and Supabase backends behind one interface
  records.py            the day record: shape, save/load, roll-ups
  auth.py               login, PIN map, forgot-PIN approvals
  images.py             accept-any-image -> compressed base64 data URL
  ui.py                 the stylesheet and the small HTML components
  charts.py             admin charts (Altair)
  export.py             CSV builder
  view_login.py         login / admin / forgot-PIN screens
  view_agent.py         the two-stage agent form
  view_admin.py         dashboard, per-agent cards, PIN panel
tests/                  see below
.streamlit/config.toml  pinned theme
```

### Data model

Three backends sit behind one interface — SQLite (local), Postgres
(`DATABASE_URL`) and Supabase-over-REST — all storing the same three tables:

| Table | Key | Value |
|---|---|---|
| `entries` | `(date, agent)` | the day record, as JSON |
| `photos` | `(date, agent, which)` | one base64 data URL; `which` is `start`/`end`/`fuel` |
| `config` | `key` | `roster`, `agentpins`, `resetrequests` |

A record carries the numbers plus `startKmAt`, `endKmAt`, `fuelAt`, `dayStartAt`
and `submittedAt` timestamps, the differential rows
(`{amount, dealId, remark}`), the cash fields (`openingBalance`, `spentAmount`
and the derived `remainingBalance`), and `hasStartPhoto` / `hasEndPhoto` /
`hasFuelPhoto` flags.

Records written by an earlier version simply lack the newer keys and load as
`None` — there is no migration step.

Photos come from the browser's camera, are downscaled to 1400px on the long edge
and saved as quality-72 JPEG — roughly 100–250 KB each, so a full 30-day window
for 11 agents stays well inside Supabase's free tier. Anything the decoder
cannot open is stored byte-for-byte instead: **a real photo is never rejected.**

### CSV shape

One **Day** row per agent per day with that day's numbers, then one
**Differential** row beneath it for each differential collected - so every
amount, deal ID and remark gets its own cells instead of being joined into one
by ` + `. The `Row Type` column tells the two apart, and a TOTAL row closes the
file. A UTF-8 BOM is prepended so Excel opens it correctly on a double-click.

### Retention

Every admin dashboard load purges entries and photos older than 30 days, so the
store trims itself without a scheduler. Change `RETENTION_DAYS` in
`lib/config.py` if you need a different window.

---

## Tests

Three suites, no pytest needed. Run them from the project root:

```bash
python tests/test_logic.py          # storage, PINs, records, retention, CSV, charts
python tests/test_screens.py        # every screen renders without an exception
python tests/test_interactions.py   # real clicks: login, save, submit, approve
python tests/test_differentials.py  # differential rows + Deal/Order ID
python tests/test_balance.py        # opening balance -> spent -> remaining
python tests/test_roster_and_csv.py # mandatory fields, CSV shape, add/remove agent
python tests/test_end_to_end.py     # the whole journey, admin onboard -> offboard
python tests/test_fresh_deploy.py   # a brand-new deploy: no secrets, no roster
python tests/test_e2e_browser.py    # real clicks + real camera at 390px (needs Chrome)
python tests/check_responsive.py    # real browser at 6 widths (needs Chrome)
python tests/test_postgres.py       # the Postgres backend (skips without DATABASE_URL)
python tests/test_no_pin_leakage.py # no PIN in the repo, the database or the UI
```

`test_end_to_end.py` walks one full journey through real widgets and clicks:
admin logs in and adds an agent, that agent is refused a wrong PIN, files the
morning, returns for the evening (watching distance and remaining balance
compute live), adds two differentials from the chips, submits, then the admin
reads the dashboard and CSV, approves a PIN reset, and finally offboards them -
23 asserted steps. The one seam is the camera: `st.camera_input` cannot be
driven from AppTest, so the photo is placed in the session slot the widget
itself fills.

`test_e2e_browser.py` runs the same journey again, but in headless Chrome at
390×844 with real mouse clicks, real keystrokes and a synthetic camera — so
`st.camera_input` genuinely captures and uploads. AppTest calls Streamlit's
callbacks directly and therefore cannot catch a control that renders but cannot
be *pressed*; this one asserts every control is actually hit-testable before
clicking it. It found two such bugs: Streamlit's toolbar and header overlay were
swallowing taps on **Log out**, and a mid-script `st.rerun()` in the photo widget
was silently wiping every field below it.

`check_responsive.py` is not a unit test - it starts its own Streamlit servers
and headless Chrome, then loads 5 screens at 6 widths (320 → 1440px) and
measures three things that actually break on phones: horizontal overflow, tap
targets under 44px, and inputs under 16px (which make iOS zoom on focus). It
ignores Streamlit's own chrome - the header button and the hover toolbars on
charts and dataframes - since those are 22-28px by design and not ours to size.

Each uses its own throwaway SQLite file and never touches `data/reports.db`.
`test_interactions.py` patches one bug in Streamlit's own `AppTest` harness
(single-select button groups), which is why the patch at the top exists.

---

## Security

**No PIN is stored anywhere, by anyone.** Not in this repository, not in the
database, not on the admin's screen. What is stored is a salted PBKDF2-SHA256
hash, which cannot be turned back into the PIN — so a leaked database, a stolen
`DATABASE_URL` or a photograph of the dashboard yields nothing you could log in
with.

| Exposure | What protects it |
|---|---|
| The repo is public | No PIN in the source; the app fails closed without `ADMIN_PIN` |
| A database dump | Only hashes are stored — the PINs are not recoverable |
| The admin's screen | The Team panel shows no PINs; a new one is shown once, as it is typed |
| The secrets store | `ADMIN_PIN_HASH` means even that holds only a hash |
| Guessing a PIN online | 5 wrong tries locks that name out for 15 minutes |
| Someone at the admin screen | `LOCK_PIN_CHANGES = true` — PINs and roster come only from secrets |

The cost of this is honest and worth stating: **the admin can no longer read an
agent's PIN back to them**, because nobody can. The forgot-PIN flow covers it —
the agent picks the new PIN they want, and the admin approves the request
without ever seeing it. If someone is simply stuck, the admin sets them a new
PIN and reads it off the screen as they type it.

### Locking the team to the backend

`LOCK_PIN_CHANGES = true` makes `AGENTS` and `AGENT_PINS` the only way to change
who is on the team and what their PINs are. They are re-applied on every start,
and the dashboard offers no add, remove or set-PIN control at all — so whoever
reaches the admin screen cannot alter anybody's access, only read reports.

Fill in `AGENT_PINS` for everyone *before* turning it on: an agent with no PIN
listed then has no route to getting one.

### How long would an attacker need?

Measured on this codebase, against a PBKDF2 hash at 120,000 iterations:

| Admin secret | Guessing via the login form | If the whole database leaks |
|---|---|---|
| 4 digits | ~10 days | seconds on a GPU |
| 6 digits | ~3 years | ~9 seconds on a GPU |
| 8 digits | ~285 years | **~15 minutes** on a GPU |
| 10 chars, letters + digits | longer than the universe | ~1,000 GPU-years |

The lockout makes any of these safe against someone poking at your login page.
Only the last row is safe against someone who has stolen your database — which
is why the admin field accepts up to 10 characters, and why a passphrase beats
a longer number. Digits alone are a small keyspace no matter how many you use.

Remaining limits, stated plainly:

* Agent PINs are 4–6 digits because agents type them on a phone twice a day.
  That is a deliberate usability trade; the lockout is what protects them.
* Anyone with the link and a valid PIN can file a report. This is a field log,
  not a bank.
* One shared admin credential means no individual accountability — you cannot
  tell *which* manager viewed a photo. Proper SSO would fix that; the storage
  interface would not have to change.
* Community Cloud apps are not indexed by default, but do not post the link
  publicly.

---

## Known limitations

* Photos are base64 in the database. Simple and portable; an object store with
  signed URLs would scale better past a few thousand records.
* Retention runs opportunistically on admin load, not on a schedule — if nobody
  opens the dashboard for a week, nothing is purged until they do.
* One record per agent per day, last write wins. Two devices editing the same
  agent's day at once will clobber each other.
* Camera-only capture means a denied camera permission, a broken camera or a
  browser without `getUserMedia` blocks that agent entirely — there is no
  fallback by design. If a phone in the field turns out to be incapable, the
  admin has no way to file on the agent's behalf.
* The admin dashboard loads every entry in the window on each rerun. Fine for 11
  agents × 30 days; revisit if the team grows a lot.

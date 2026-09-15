"""Look and feel: one stylesheet plus the small HTML components the views use.

The app pins Streamlit's light theme (.streamlit/config.toml) so these tokens
and Streamlit's own widgets can never disagree. Everything sizes with clamp()
and CSS grid, so the same markup works on a 360px phone, a tablet and a laptop.
"""
from __future__ import annotations

import html as _html
from typing import Optional

import streamlit as st

# Chart-surface and ink values match lib/charts.py so cards and plots agree.
CSS = """
<style>
:root{
  --ink:#0b1020; --ink-2:#4b5566; --muted:#8a91a0;
  --line:#e4e8f0; --surface:#ffffff; --plane:#f4f6fb; --soft:#eef2fc;
  --brand:#2a78d6; --brand-2:#5b3ee8; --brand-3:#12b6cf;
  --good:#0ca30c; --good-soft:#e6f7e6;
  --warn:#fab219; --warn-soft:#fff6e2;
  --crit:#d03b3b; --crit-soft:#fdecec;
  --r:16px;
  --shadow:0 1px 2px rgba(11,16,32,.05), 0 10px 30px rgba(11,16,32,.07);
  --shadow-lg:0 20px 50px rgba(11,16,32,.14);
}

/* ---------------------------------------------------- streamlit furniture */
/* The header and its toolbar are transparent overlays sitting at z-index
   999990. With the header collapsed to zero height our own top row renders
   underneath them, and their empty areas swallowed the clicks on Log out -
   invisibly, and only at some widths. Let clicks fall straight through the
   empty parts, while their real controls stay clickable. */
[data-testid="stHeader"]{background:transparent; height:0; pointer-events:none}
[data-testid="stToolbar"]{right:8px; top:6px; pointer-events:none}
[data-testid="stHeader"] button,
[data-testid="stHeader"] a,
[data-testid="stToolbar"] > *{pointer-events:auto}
/* Toasts land where our top bar lives, so on a phone one can sit on top of the
   Log out button for its whole lifetime. Park them at the bottom instead. */
[data-testid="stToast"]{
  top:auto !important; bottom:calc(env(safe-area-inset-bottom) + 18px) !important;
}
footer, #MainMenu{visibility:hidden}
[data-testid="stDecoration"]{display:none}
[data-testid="stAppViewContainer"]{background:var(--plane)}
.block-container{
  padding-top:clamp(12px,3vw,26px) !important;
  padding-bottom:88px !important;
  padding-left:clamp(12px,4vw,40px) !important;
  padding-right:clamp(12px,4vw,40px) !important;
  max-width:1180px;
}
/* Set the face on the document only. Do NOT use a catch-all like
   [class*="st-"]: it also matches Streamlit's Material icon spans, whose
   glyphs are ligatures - overriding their font makes the expander chevron
   render as the literal text "keyboard_arrow_down" on top of the label. */
html, body{
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
body{color:var(--ink)}
/* Belt and braces: keep the icon font on the icon spans whatever else changes. */
[data-testid="stIconMaterial"], span[class*="material-symbols"]{
  font-family:"Material Symbols Rounded" !important;
}

/* ------------------------------------------------------------------- hero */
.hero{
  position:relative; overflow:hidden; border-radius:22px; color:#fff;
  padding:clamp(18px,4vw,30px) clamp(18px,4vw,32px);
  background:linear-gradient(120deg,#2a78d6 0%,#5b3ee8 45%,#12b6cf 100%);
  background-size:220% 220%; animation:drift 18s ease infinite;
  box-shadow:var(--shadow-lg);
}
@keyframes drift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
.hero::after{
  content:""; position:absolute; right:-70px; top:-90px;
  width:260px; height:260px; border-radius:50%;
  background:rgba(255,255,255,.13);
}
.hero h1{
  margin:0; font-size:clamp(21px,5.2vw,32px); font-weight:800; letter-spacing:-.02em;
  line-height:1.15; position:relative;
}
.hero p{margin:6px 0 0; font-size:clamp(13px,3.4vw,15px); opacity:.93; position:relative}
.hero .crumbs{
  display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; position:relative;
}
.hero .crumb{
  background:rgba(255,255,255,.18); border:1px solid rgba(255,255,255,.28);
  padding:5px 12px; border-radius:999px; font-size:12.5px; font-weight:650;
  backdrop-filter:blur(6px); white-space:nowrap;
}

/* ------------------------------------------------------------ stat tiles */
.tiles{display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(158px,1fr)); margin:4px 0 2px}
.tile{
  background:var(--surface); border:1px solid var(--line); border-radius:var(--r);
  padding:15px 16px; box-shadow:var(--shadow); position:relative; overflow:hidden;
  transition:transform .18s ease, box-shadow .18s ease;
}
.tile:hover{transform:translateY(-3px); box-shadow:var(--shadow-lg)}
.tile::before{content:""; position:absolute; inset:0 auto 0 0; width:4px; background:var(--brand)}
.tile.v2::before{background:var(--brand-2)} .tile.v3::before{background:var(--brand-3)}
.tile.v4::before{background:var(--good)}    .tile.v5::before{background:var(--warn)}
.tile .k{font-size:11.5px; font-weight:750; color:var(--muted); text-transform:uppercase; letter-spacing:.06em}
.tile .v{font-size:clamp(22px,5.6vw,30px); font-weight:800; letter-spacing:-.02em; margin-top:5px; line-height:1.1}
.tile .n{font-size:12px; color:var(--ink-2); margin-top:3px}

/* ----------------------------------------------------------------- cards */
.panel{
  background:var(--surface); border:1px solid var(--line); border-radius:var(--r);
  padding:clamp(14px,3.2vw,20px); box-shadow:var(--shadow); margin-bottom:14px;
}
.sec{display:flex; align-items:center; gap:10px; margin:22px 0 10px; flex-wrap:wrap}
.sec .ico{
  width:34px; height:34px; border-radius:11px; display:grid; place-items:center; font-size:17px;
  background:linear-gradient(135deg,var(--soft),#fff); border:1px solid var(--line); flex:none;
}
/* keep the icon and the text on one line however long the subtitle is */
.sec > div:last-child{flex:1 1 0; min-width:0}
.sec h3{margin:0; font-size:clamp(15px,3.8vw,18px); font-weight:750; letter-spacing:-.01em}
.sec .sub{font-size:12.5px; color:var(--muted); margin:1px 0 0}

/* ----------------------------------------------------------------- pills */
.pill{
  display:inline-flex; align-items:center; gap:5px; font-size:11.5px; font-weight:750;
  padding:4px 10px; border-radius:999px; white-space:nowrap;
  background:var(--soft); color:var(--brand); border:1px solid transparent;
}
.pill.good{background:var(--good-soft); color:#0a7a0a}
.pill.warn{background:var(--warn-soft); color:#8a6100}
.pill.crit{background:var(--crit-soft); color:var(--crit)}
.pill.flat{background:#f1f3f8; color:var(--ink-2)}

/* ---------------------------------------------------------------- stepper */
.steps{display:flex; align-items:center; gap:6px; margin:2px 0 4px; flex-wrap:wrap}
.step{
  display:flex; align-items:center; gap:7px; padding:7px 13px; border-radius:999px;
  background:#f1f3f8; color:var(--muted); font-size:12.5px; font-weight:700; white-space:nowrap;
}
.step .dot{
  width:19px; height:19px; border-radius:50%; display:grid; place-items:center;
  background:#dfe3ec; color:#fff; font-size:11px; flex:none;
}
.step.on{background:linear-gradient(135deg,var(--brand),var(--brand-2)); color:#fff}
.step.on .dot{background:rgba(255,255,255,.3)}
.step.done{background:var(--good-soft); color:#0a7a0a}
.step.done .dot{background:var(--good)}
.steps .bar{flex:1 1 14px; height:2px; background:#e2e6ef; min-width:10px; border-radius:2px}

/* --------------------------------------------------------- agent day row */
.drow{
  display:grid; gap:2px 14px; grid-template-columns:repeat(auto-fit,minmax(118px,1fr));
  margin-top:4px;
}
.drow .c .k{font-size:11px; color:var(--muted); font-weight:700; text-transform:uppercase; letter-spacing:.05em}
.drow .c .v{font-size:15px; font-weight:700; font-variant-numeric:tabular-nums}
.drow .c .t{font-size:11.5px; color:var(--muted)}

/* ----------------------------------------------------------------- notes */
.note{border-radius:12px; padding:12px 14px; font-size:13.5px; line-height:1.5}
.note.info{background:var(--soft); color:#1c5cab}
.note.good{background:var(--good-soft); color:#0a7a0a}
.note.warn{background:var(--warn-soft); color:#8a6100}
.note.crit{background:var(--crit-soft); color:var(--crit)}

/* -------------------------------------------------------------- widgets */
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
  border-radius:12px; font-weight:700; min-height:46px; font-size:15px;
  border:1.5px solid var(--line); transition:transform .07s ease, box-shadow .2s ease;
  width:100%;
}
.stButton>button:hover, .stDownloadButton>button:hover, .stFormSubmitButton>button:hover{
  box-shadow:0 6px 18px rgba(11,16,32,.12); transform:translateY(-1px);
}
.stButton>button:active{transform:translateY(0) scale(.99)}
button[kind="primary"], .stFormSubmitButton>button[kind="primaryFormSubmit"]{
  background:linear-gradient(135deg,var(--brand),var(--brand-2)) !important;
  border:none !important; color:#fff !important;
  box-shadow:0 8px 22px rgba(42,120,214,.34) !important;
}
/* A disabled primary must not look pressable - it is the app's main signal
   that something is still missing above it. */
button[kind="primary"]:disabled, button[kind="primary"][disabled]{
  background:#c9d2e2 !important; color:#7b869a !important;
  box-shadow:none !important; opacity:1 !important; cursor:not-allowed;
}
.stButton>button:disabled:hover{transform:none; box-shadow:none}
.stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea{
  border-radius:12px !important; min-height:46px; font-size:16px !important;  /* 16px = no iOS zoom */
  background:transparent !important;
}
/* The show/hide-PIN eye lives inside the field and ships at 38px; agents do
   tap it, so bring it up to a 44px target. */
.stTextInput [data-baseweb="input"] button{
  min-height:44px !important; min-width:44px !important;
}
/* Cards are white, so a white field would vanish into them - tint the field
   itself and let the card stay the lighter surface. */
[data-testid="stNumberInputContainer"],
.stTextInput [data-baseweb="input"],
.stDateInput [data-baseweb="input"],
.stTextArea [data-baseweb="textarea"]{
  background:var(--plane) !important;
  border-radius:12px !important;
  border:1.5px solid var(--line) !important;
}
[data-testid="stNumberInputContainer"]:focus-within,
.stTextInput [data-baseweb="input"]:focus-within,
.stDateInput [data-baseweb="input"]:focus-within{
  border-color:var(--brand) !important; background:var(--surface) !important;
}
[data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"]{display:none}
[data-testid="stMetricValue"]{font-size:26px}
[data-baseweb="tab-list"]{gap:4px}
[data-baseweb="tab"]{border-radius:10px 10px 0 0; font-weight:650}
[data-testid="stExpander"] details{
  border-radius:var(--r); border:1px solid var(--line); background:var(--surface); box-shadow:var(--shadow);
}
[data-testid="stCameraInput"] video, [data-testid="stCameraInput"] img{border-radius:12px}
/* Streamlit's own shutter button is ~39px; this is the control agents press
   twice a day, often one-handed, so give it a proper 48px target. */
[data-testid="stCameraInput"] button, [data-testid="stCameraInputButton"]{
  min-height:48px !important; font-weight:700; border-radius:12px !important;
}
/* st.container(border=True) should read as a real card, like .panel.
   Streamlit >=1.49 renders it as stLayoutWrapper > stVerticalBlock (a bordered
   block); older versions wrapped it in stVerticalBlockBorderWrapper. Both are
   matched so the cards look right either way. Column rows are the other child
   of stLayoutWrapper (stHorizontalBlock) and are deliberately left alone. */
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"],
[data-testid="stVerticalBlockBorderWrapper"] > div > [data-testid="stVerticalBlock"]{
  background:var(--surface) !important;
  border-color:var(--line) !important;
  border-radius:var(--r) !important;
  box-shadow:var(--shadow);
  padding:clamp(12px,3vw,18px) !important;
}

/* pills widget (name picker) - big tappable targets */
[data-testid="stButtonGroup"] button{border-radius:999px !important; font-weight:700; min-height:44px; padding:0 16px}

/* ------------------------------------------------------------- responsive */
@media (max-width:760px){
  .block-container{padding-bottom:64px !important}
  .hero{border-radius:18px}
  .hero::after{display:none}
  .sec{margin-top:16px}
  /* Let columns wrap instead of squeezing: two narrow fields still sit side by
     side on a 360px screen, a third drops to the next line by itself. */
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap !important; gap:.45rem !important}
  [data-testid="stColumn"]{
    flex:1 1 132px !important; min-width:132px !important; width:auto !important;
  }
}
@media (max-width:420px){
  /* Phones this narrow get one field per line - two would be unreadable. */
  [data-testid="stColumn"]{flex:1 1 100% !important; min-width:100% !important}
}
@media (prefers-reduced-motion:reduce){
  .hero{animation:none}
  *{transition:none !important}
}
.fade{animation:fade .34s ease both}
@keyframes fade{from{opacity:0; transform:translateY(6px)}to{opacity:1; transform:none}}
</style>
"""


def inject_css() -> None:
    """Called once per rerun, at the top of the page."""
    st.markdown(CSS, unsafe_allow_html=True)


def e(s) -> str:
    return _html.escape(str(s if s is not None else ""))


# ---------------------------------------------------------------- components
def hero(title: str, subtitle: str = "", crumbs: Optional[list] = None) -> None:
    chips = "".join('<span class="crumb">{}</span>'.format(e(c)) for c in (crumbs or []))
    st.markdown(
        '<div class="hero fade"><h1>{}</h1><p>{}</p><div class="crumbs">{}</div></div>'.format(
            e(title), e(subtitle), chips
        ),
        unsafe_allow_html=True,
    )


def section(icon: str, title: str, sub: str = "") -> None:
    st.markdown(
        '<div class="sec"><div class="ico">{}</div><div><h3>{}</h3>'
        '<p class="sub">{}</p></div></div>'.format(e(icon), e(title), e(sub)),
        unsafe_allow_html=True,
    )


def tiles(items) -> None:
    """items: list of (label, value, note). Wraps to any screen width."""
    cells = []
    for i, (k, v, n) in enumerate(items):
        cells.append(
            '<div class="tile v{}"><div class="k">{}</div><div class="v">{}</div>'
            '<div class="n">{}</div></div>'.format((i % 5) + 1, e(k), e(v), e(n))
        )
    st.markdown('<div class="tiles fade">{}</div>'.format("".join(cells)), unsafe_allow_html=True)


def pill(text: str, kind: str = "") -> str:
    return '<span class="pill {}">{}</span>'.format(e(kind), e(text))


def note(text: str, kind: str = "info") -> None:
    st.markdown('<div class="note {}">{}</div>'.format(e(kind), e(text)), unsafe_allow_html=True)


def stepper(active: int, done_final: bool = False) -> None:
    """1 = start of day, 2 = end of day, 3 = submitted."""
    labels = [("1", "Start of day"), ("2", "End of day"), ("✓", "Submitted")]
    out = []
    for i, (dot, label) in enumerate(labels, start=1):
        if done_final and i <= 3:
            cls = "done"
        elif i < active:
            cls = "done"
        elif i == active:
            cls = "on"
        else:
            cls = ""
        out.append(
            '<div class="step {}"><span class="dot">{}</span>{}</div>'.format(cls, e(dot), e(label))
        )
        if i < len(labels):
            out.append('<div class="bar"></div>')
    st.markdown('<div class="steps">{}</div>'.format("".join(out)), unsafe_allow_html=True)


def spacer(px: int = 8) -> None:
    st.markdown('<div style="height:{}px"></div>'.format(int(px)), unsafe_allow_html=True)

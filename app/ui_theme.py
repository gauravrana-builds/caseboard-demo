"""Look and feel for the review UI.

Visual language borrowed from the "Stripe design system analysis" on getdesign.md (an independent,
inspired interpretation): electric indigo CTA, deep-navy ink, cool off-white surfaces, a pastel gradient-mesh
hero, thin weight-300 display type with negative tracking, tabular figures for numbers, pill buttons and tags.
Not affiliated with Stripe; no Stripe name, logo or marks are used.

All text that comes from data (complaints, drafts, records) must go through esc() before it is placed in HTML.
"""

import html

# --- design tokens (hex values from the spec) -----------------------------------------------------------------
INDIGO, INDIGO_DEEP, INDIGO_PRESS, INDIGO_SOFT, INDIGO_SUBDUED = "#533afd", "#4434d4", "#2e2b8c", "#665efd", "#b9b9f9"
NAVY, INK, INK_2, MUTE = "#1c1e54", "#0d253d", "#273951", "#64748d"
CANVAS, SOFT, CREAM, HAIRLINE, HAIRLINE_INPUT = "#ffffff", "#f6f9fc", "#f5e9d4", "#e3e8ee", "#a8c3de"
RUBY, LEMON = "#ea2261", "#9b6829"


def logo_svg(size: int = 30) -> str:
    """The Caseboard mark: a rounded square with three board columns and a small 'needs review' dot."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="{size}" height="{size}" role="img" aria-label="Caseboard">'
            '<defs><linearGradient id="cbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7a6bff"/><stop offset="1" stop-color="#533afd"/></linearGradient></defs>'
            '<rect width="32" height="32" rx="9" fill="url(#cbg)"/>'
            '<rect x="6.5" y="7.5" width="5.5" height="7" rx="1.7" fill="#fff"/>'
            '<rect x="6.5" y="16.5" width="5.5" height="8" rx="1.7" fill="#fff" fill-opacity=".62"/>'
            '<rect x="13.25" y="7.5" width="5.5" height="11" rx="1.7" fill="#fff"/>'
            '<rect x="20" y="7.5" width="5.5" height="5" rx="1.7" fill="#fff" fill-opacity=".62"/>'
            '<rect x="20" y="14.5" width="5.5" height="10" rx="1.7" fill="#fff"/>'
            '<circle cx="25.2" cy="7.2" r="2.7" fill="#ea2261" stroke="#533afd" stroke-width="1.2"/></svg>')


def esc(value) -> str:
    """Escape untrusted text for inclusion in HTML; newlines become <br> so no blank lines break the markup."""
    return html.escape("" if value is None else str(value)).replace("\r\n", "\n").replace("\n", "<br>")


def pill(text: str, kind: str = "indigo") -> str:
    return f'<span class="pill pill-{kind}">{esc(text)}</span>'


TIER_KIND = {"Low": "calm", "Medium": "amber", "High": "ruby"}
VERDICT_LABEL = {
    "confirmed_true": "Confirmed true", "confirmed_false": "Confirmed false",
    "partially_true": "Partially true", "unverifiable": "Unverifiable",
}


def tier_pill(tier: str) -> str:
    return pill(f"{tier} risk" if tier else "Unrated", TIER_KIND.get(tier, "calm"))


def verdict_pill(verdict: str) -> str:
    return pill(VERDICT_LABEL.get(verdict, verdict or "Not assessed"), "indigo")


THEME_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
:root {{
  --primary:{INDIGO}; --primary-deep:{INDIGO_DEEP}; --primary-press:{INDIGO_PRESS}; --primary-soft:{INDIGO_SOFT};
  --primary-subdued:{INDIGO_SUBDUED}; --navy:{NAVY}; --ink:{INK}; --ink-2:{INK_2}; --mute:{MUTE};
  --canvas:{CANVAS}; --soft:{SOFT}; --cream:{CREAM}; --hair:{HAIRLINE}; --hair-input:{HAIRLINE_INPUT};
  --ruby:{RUBY}; --lemon:{LEMON};
  --shadow-1:0 1px 3px rgba(0,55,112,.08);
  --shadow-2:0 8px 24px rgba(0,55,112,.08),0 2px 6px rgba(0,55,112,.04);
  --font:'Inter','SF Pro Display',system-ui,-apple-system,'Segoe UI',sans-serif;
}}

/* base */
html, body, .stApp {{ background:var(--canvas); color:var(--ink); }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp textarea, .stApp td, .stApp th, .stApp [data-testid="stMarkdownContainer"] {{
  font-family:var(--font); font-weight:300; font-feature-settings:"ss01"; color:var(--ink);
}}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {{ display:none !important; }}
.block-container {{ max-width:1180px; padding-top:0 !important; padding-bottom:64px; }}
.tnum {{ font-feature-settings:"tnum"; letter-spacing:-.02em; }}
a {{ color:var(--primary); text-decoration:none; }}

/* sidebar */
[data-testid="stSidebar"] {{ background:var(--soft); border-right:1px solid var(--hair); }}
[data-testid="stSidebar"] .block-container {{ padding-top:24px !important; }}
.brand {{ display:flex; align-items:center; gap:10px; margin-bottom:6px; }}
.brand-mark {{ width:30px; height:30px; border-radius:9px;
  background:radial-gradient(circle at 25% 20%, #ffb88c 0, transparent 55%), radial-gradient(circle at 80% 85%, #ea2261 0, transparent 55%), linear-gradient(135deg,#665efd,#533afd); box-shadow:var(--shadow-1); }}
.brand-name {{ font-weight:500; font-size:16px; letter-spacing:-.2px; }}
.side-note {{ color:var(--mute); font-size:12.5px; line-height:1.5; margin:4px 0 18px; }}
.side-label {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--mute); margin:18px 0 6px; }}

/* hero: pastel gradient mesh across the upper third */
.hero {{ margin:0 -4rem 18px; padding:34px 4rem 22px; position:relative; overflow:hidden;
  background:
    radial-gradient(620px 300px at 6% -10%, {CREAM} 0%, rgba(245,233,212,0) 70%),
    radial-gradient(560px 300px at 34% 0%, rgba(255,184,140,.75) 0%, rgba(255,184,140,0) 70%),
    radial-gradient(620px 320px at 60% -8%, rgba(201,196,255,.95) 0%, rgba(201,196,255,0) 70%),
    radial-gradient(560px 300px at 86% 0%, rgba(122,107,255,.85) 0%, rgba(122,107,255,0) 70%),
    radial-gradient(420px 260px at 100% 10%, rgba(255,122,168,.8) 0%, rgba(255,122,168,0) 70%),
    linear-gradient(180deg, rgba(255,255,255,0) 60%, #ffffff 100%), #ffffff; }}
.eyebrow {{ display:inline-block; font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase;
  background:rgba(255,255,255,.75); color:var(--primary-deep); border-radius:9999px; padding:4px 10px; margin-bottom:16px; backdrop-filter:blur(6px); }}
.hero h1 {{ font-size:40px; font-weight:300; line-height:1.1; letter-spacing:-.8px; margin:0 0 10px; max-width:760px; }}
.hero p.lead {{ font-size:15px; color:var(--ink-2); line-height:1.5; max-width:620px; margin:0 0 18px; }}
.stats {{ display:flex; gap:14px; flex-wrap:wrap; }}
.stat {{ background:rgba(255,255,255,.88); border:1px solid rgba(227,232,238,.9); border-radius:12px; padding:10px 16px; min-width:130px; box-shadow:var(--shadow-1); backdrop-filter:blur(6px); }}
.stat .n {{ font-size:24px; font-weight:300; letter-spacing:-.4px; font-feature-settings:"tnum"; line-height:1.1; }}
.stat .l {{ font-size:12px; color:var(--mute); margin-top:2px; }}

/* section headings and cards */
.section-title {{ font-size:22px; font-weight:300; letter-spacing:-.22px; margin:30px 0 4px; }}
.section-sub {{ color:var(--mute); font-size:14px; margin-bottom:14px; }}
.card {{ background:var(--canvas); border:1px solid var(--hair); border-radius:12px; padding:24px 26px; box-shadow:var(--shadow-1); margin-bottom:16px; }}
.card h4 {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--mute); margin:0 0 10px; }}
.card p, .card li {{ font-size:15px; line-height:1.55; }}
.card ul {{ margin:0; padding-left:18px; }}
.card.soft {{ background:var(--soft); box-shadow:none; }}
.card.cream {{ background:var(--cream); border-color:#ecdcc0; box-shadow:none; }}
.card.ruby {{ background:#fff5f8; border-color:#f7c3d4; }}
.muted {{ color:var(--mute); }}
.small {{ font-size:13px; }}

/* packet header */
.packet-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:24px; flex-wrap:wrap; margin:6px 0 4px; }}
.packet-id {{ font-size:13px; color:var(--mute); letter-spacing:-.02em; font-feature-settings:"tnum"; margin-bottom:6px; }}
.packet-title {{ font-size:32px; font-weight:300; letter-spacing:-.64px; line-height:1.12; margin:0 0 10px; max-width:720px; }}
.metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:14px 0 18px; }}
.metric {{ border:1px solid var(--hair); border-radius:12px; padding:16px 18px; background:var(--canvas); box-shadow:var(--shadow-1); }}
.metric .k {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--mute); margin-bottom:8px; }}
.metric .sub {{ font-size:13px; color:var(--mute); margin-top:8px; line-height:1.4; }}

/* pills and tags */
.pill {{ display:inline-block; border-radius:9999px; padding:4px 11px; font-size:12px; font-weight:500; line-height:1.3; white-space:nowrap; }}
.pill-indigo {{ background:rgba(185,185,249,.45); color:var(--primary-deep); }}
.pill-calm {{ background:#eef2f7; color:var(--ink-2); }}
.pill-amber {{ background:#fbf0dc; color:var(--lemon); }}
.pill-ruby {{ background:#fde6ee; color:var(--ruby); }}
.pill-navy {{ background:var(--navy); color:#fff; }}
.pill-ok {{ background:rgba(185,185,249,.45); color:var(--primary-deep); }}

/* stop banner (escalation view) */
.banner {{ border-radius:12px; padding:22px 26px; margin:6px 0 18px; border:1px solid #f7c3d4;
  background:linear-gradient(120deg,#fff5f8 0%,#ffe8f0 60%,#fde0eb 100%); box-shadow:var(--shadow-1); }}
.banner .k {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--ruby); margin-bottom:8px; }}
.banner .t {{ font-size:22px; font-weight:300; letter-spacing:-.22px; line-height:1.3; margin:0; }}
.banner .why {{ font-size:15px; color:var(--ink-2); margin-top:10px; line-height:1.5; }}

/* the draft: formatted like the message that would be sent */
.paper {{ background:var(--canvas); border:1px solid var(--hair); border-radius:12px; box-shadow:var(--shadow-2); overflow:hidden; margin-bottom:16px; }}
.paper-head {{ background:var(--soft); border-bottom:1px solid var(--hair); padding:12px 22px; display:flex; justify-content:space-between; align-items:center; gap:10px; }}
.paper-head .meta {{ font-size:12.5px; color:var(--mute); }}
.paper-body {{ padding:22px 26px 24px; font-size:15px; line-height:1.65; color:var(--ink); }}

/* verifier checks */
.check {{ display:flex; align-items:flex-start; gap:10px; padding:9px 0; border-bottom:1px solid var(--hair); font-size:14px; }}
.check:last-child {{ border-bottom:0; }}
.dot {{ width:18px; height:18px; border-radius:50%; flex:0 0 18px; margin-top:1px; font-size:11px; font-weight:600; display:flex; align-items:center; justify-content:center; }}
.dot-ok {{ background:rgba(185,185,249,.55); color:var(--primary-deep); }}
.dot-bad {{ background:#fde6ee; color:var(--ruby); }}

/* streamlit widgets */
div[data-testid="stBaseButton-primary"] button, button[data-testid="stBaseButton-primary"] {{
  background:var(--primary); color:#fff; border:1px solid var(--primary); border-radius:9999px; padding:.5rem 1.1rem; font-weight:400; font-size:15px; box-shadow:none; }}
button[data-testid="stBaseButton-primary"]:hover {{ background:var(--primary-deep); border-color:var(--primary-deep); color:#fff; }}
button[data-testid="stBaseButton-primary"]:active {{ background:var(--primary-press); }}
button[data-testid="stBaseButton-secondary"] {{
  background:var(--canvas); color:var(--primary); border:1px solid var(--primary); border-radius:9999px; padding:.5rem 1.1rem; font-weight:400; font-size:15px; }}
button[data-testid="stBaseButton-secondary"]:hover {{ background:rgba(185,185,249,.25); color:var(--primary-deep); border-color:var(--primary-deep); }}
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primary"] * {{ color:#fff !important; font-weight:400; }}
button[data-testid="stBaseButton-secondary"], button[data-testid="stBaseButton-secondary"] * {{ color:var(--primary) !important; font-weight:400; }}
button[data-testid="stBaseButton-secondary"]:hover, button[data-testid="stBaseButton-secondary"]:hover * {{ color:var(--primary-deep) !important; }}
button[data-testid="stBaseButton-primary"]:disabled, button[data-testid="stBaseButton-secondary"]:disabled {{ opacity:.45; }}
.stTextArea textarea, .stTextInput input {{ border:1px solid var(--hair-input); border-radius:6px; background:#fff; font-size:15px; }}
.stTextArea textarea:focus, .stTextInput input:focus {{ border-color:var(--primary); box-shadow:0 0 0 1px var(--primary); }}
[data-testid="stExpander"] {{ border:1px solid var(--hair); border-radius:12px; background:#fff; box-shadow:var(--shadow-1); }}
[data-testid="stExpander"] summary {{ font-weight:400; }}
[data-testid="stDataFrame"] {{ border:1px solid var(--hair); border-radius:12px; overflow:hidden; box-shadow:var(--shadow-1); }}
[data-testid="stAlert"] {{ border-radius:12px; }}

/* decision panel: the dark-app tier, like the featured card */
.st-key-back_queue_top button, .st-key-back_queue_bottom button, .st-key-next_attention_top button, .st-key-next_attention_bottom button {{ white-space:nowrap; min-width:max-content; padding-left:18px; padding-right:18px; }}
.st-key-back_queue_top, .st-key-back_queue_bottom, .st-key-next_attention_top, .st-key-next_attention_bottom {{ width:auto !important; }}
.st-key-decision {{ background:var(--navy); border-radius:12px; padding:24px 26px; box-shadow:var(--shadow-2); }}
.st-key-decision, .st-key-decision p, .st-key-decision label, .st-key-decision span, .st-key-decision [data-testid="stMarkdownContainer"] {{ color:#fff !important; }}
.st-key-decision .dk {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:#b9b9f9; margin-bottom:6px; }}
.st-key-decision .dt {{ font-size:20px; font-weight:300; letter-spacing:-.2px; margin-bottom:6px; }}
.st-key-decision .ds {{ font-size:13.5px; color:#d6d6f7; line-height:1.5; margin-bottom:12px; }}
.st-key-decision button[data-testid="stBaseButton-primary"] {{ background:#fff; color:var(--navy); border-color:#fff; }}
.st-key-decision button[data-testid="stBaseButton-primary"]:hover {{ background:#e9e9ff; }}
.st-key-decision button[data-testid="stBaseButton-secondary"] {{ background:transparent; color:#fff; border-color:rgba(255,255,255,.55); }}
.st-key-decision button[data-testid="stBaseButton-secondary"]:hover {{ background:rgba(255,255,255,.12); border-color:#fff; color:#fff; }}
.st-key-decision button[data-testid="stBaseButton-primary"], .st-key-decision button[data-testid="stBaseButton-primary"] * {{ color:var(--navy) !important; }}
.st-key-decision button[data-testid="stBaseButton-secondary"], .st-key-decision button[data-testid="stBaseButton-secondary"] * {{ color:#fff !important; }}
.st-key-decision .stTextArea textarea, .st-key-decision .stTextInput input {{ background:#fff; color:var(--ink) !important; }}
.st-key-decision .stTextArea textarea *, .st-key-decision .stTextInput input * {{ color:var(--ink) !important; }}
.recorded {{ background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.25); border-radius:10px; padding:14px 16px; font-size:14px; line-height:1.5; }}

.empty {{ text-align:center; padding:54px 24px; border:1px dashed var(--hair-input); border-radius:12px; background:var(--soft); }}
.empty .t {{ font-size:22px; font-weight:300; letter-spacing:-.22px; margin-bottom:6px; }}
.footer {{ color:var(--mute); font-size:12.5px; text-align:center; margin-top:48px; padding-top:20px; border-top:1px solid var(--hair); }}
@media (max-width:900px) {{ .metrics {{ grid-template-columns:1fr; }} .hero {{ margin:0 -1rem 20px; padding:36px 1rem 24px; }} .hero h1 {{ font-size:34px; }} }}

/* top-level and detail tabs */
[data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid var(--hair); }}
button[role="tab"] {{ font-weight:400; color:var(--mute); padding:10px 14px; }}
button[role="tab"][aria-selected="true"] {{ color:var(--primary); }}
[data-baseweb="tab-highlight"] {{ background:var(--primary) !important; height:2px; }}
[data-baseweb="tab-border"] {{ background:transparent !important; }}

/* guided demo */
[class*="st-key-chip"] button {{ font-size:13px; padding:.4rem .4rem; }}
.notice {{ background:rgba(185,185,249,.16); border-left:3px solid var(--primary); border-radius:8px; padding:12px 18px; margin:10px 0 6px; font-size:14.5px; line-height:1.55; }}
.notice b {{ font-weight:500; color:var(--primary-deep); }}
.demo-label {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--mute); margin:6px 0 6px; }}

/* plain-language headline */
.headline {{ font-size:26px; font-weight:300; letter-spacing:-.26px; line-height:1.25; margin:2px 0 10px; max-width:880px; }}
.headline.stop {{ color:#a3123f; }}
.headline.warn {{ color:var(--lemon); }}

/* agent steps strip */
.steps {{ display:flex; gap:0; margin:6px 0 20px; background:var(--soft); border:1px solid var(--hair); border-radius:12px; padding:14px 10px; }}
.step {{ flex:1; text-align:center; position:relative; padding:0 6px; }}
.step:not(:last-child)::after {{ content:""; position:absolute; top:13px; left:calc(50% + 18px); right:calc(-50% + 18px); height:2px; background:var(--hair-input); }}
.step.done-next:not(:last-child)::after, .step-ok:not(:last-child)::after {{ background:var(--primary-subdued); }}
.sc {{ width:26px; height:26px; border-radius:50%; margin:0 auto 6px; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:600; position:relative; z-index:1; }}
.step-ok .sc {{ background:var(--primary); color:#fff; }}
.step-stop .sc {{ background:var(--ruby); color:#fff; box-shadow:0 0 0 5px rgba(234,34,97,.15); }}
.step-bad .sc {{ background:var(--lemon); color:#fff; }}
.step-skip .sc {{ background:#e8edf3; color:var(--mute); }}
.sl {{ font-size:13px; font-weight:400; line-height:1.3; }}
.ss {{ font-size:12px; color:var(--mute); margin-top:2px; line-height:1.3; }}
.step-stop .sl, .step-stop .ss {{ color:#a3123f; }}
.step-skip .sl {{ color:var(--mute); }}

/* scorecard */
.score-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:16px; margin:12px 0 8px; }}
.score {{ border:1px solid var(--hair); border-radius:12px; padding:22px 24px; background:var(--canvas); box-shadow:var(--shadow-1); }}
.score .st {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--mute); margin-bottom:8px; }}
.score .big {{ font-size:38px; font-weight:300; letter-spacing:-.76px; font-feature-settings:"tnum"; line-height:1.05; }}
.score .big small {{ font-size:15px; color:var(--mute); letter-spacing:0; margin-left:6px; }}
.score .what {{ font-size:14px; color:var(--ink-2); margin:10px 0 14px; line-height:1.5; }}
.bar {{ height:10px; background:#eef2f7; border-radius:9999px; position:relative; margin:4px 0 14px; }}
.bar i {{ display:block; height:100%; border-radius:9999px; background:linear-gradient(90deg,#665efd,#533afd); }}
.bar .line {{ position:absolute; top:-5px; bottom:-5px; width:2px; background:var(--ink); }}
.bar-note {{ font-size:12px; color:var(--mute); }}
.mini-seg {{ display:flex; height:12px; border-radius:9999px; overflow:hidden; margin:6px 0 12px; }}
.mini-seg span {{ display:block; height:100%; }}
@media (max-width:900px) {{ .score-grid {{ grid-template-columns:1fr; }} .steps {{ flex-wrap:wrap; row-gap:14px; }} .step {{ flex:0 0 33%; }} .step::after {{ display:none; }} }}

/* slim hero for the queue-first layout */
.hero.slim {{ padding:22px 4rem 14px; margin-bottom:14px; }}
.hero.slim h1 {{ font-size:30px; margin-bottom:6px; }}
.hero.slim p.lead {{ font-size:14.5px; margin:0; }}
.hero.slim .eyebrow {{ margin-bottom:10px; }}

/* disposition tracker */
.pill-green {{ background:#dff5ea; color:#13694a; }}
.tracker {{ border:1px solid var(--hair); border-radius:12px; padding:18px 20px 16px; background:var(--canvas); box-shadow:var(--shadow-1); margin:4px 0 14px; }}
.tracker-top {{ display:flex; justify-content:space-between; align-items:baseline; gap:16px; flex-wrap:wrap; margin-bottom:10px; }}
.tracker-title {{ font-size:18px; font-weight:300; letter-spacing:-.18px; }}
.tracker-sub {{ font-size:13px; color:var(--mute); }}
.seg {{ display:flex; height:12px; border-radius:9999px; overflow:hidden; background:#eef2f7; margin-bottom:14px; }}
.seg span {{ display:block; height:100%; }}
.tiles {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
.tile {{ border:1px solid var(--hair); border-radius:10px; padding:12px 14px; border-top-width:3px; background:var(--canvas); min-width:0; }}
.tile .tn {{ font-size:28px; font-weight:300; letter-spacing:-.4px; font-feature-settings:"tnum"; line-height:1.1; }}
.tile .tl {{ font-size:13px; font-weight:500; margin-top:2px; }}
.tile .th {{ font-size:12px; color:var(--mute); margin-top:3px; line-height:1.35; }}
.focus {{ background:rgba(185,185,249,.16); border-left:3px solid var(--primary); border-radius:8px; padding:12px 18px; font-size:14.5px; line-height:1.55; margin-bottom:10px; }}
.focus b {{ font-weight:500; color:var(--primary-deep); }}
.filters-label {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--mute); margin:12px 0 4px; }}
.crumb {{ font-size:13px; color:var(--mute); }}
@media (max-width:900px) {{ .tiles {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .hero.slim {{ margin:0 -1rem 12px; padding:18px 1rem 10px; }} }}

/* app bar: logo on the left, the signed-in analyst on the right */
.topbar {{ display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:18px; }}
.tb-brand {{ display:flex; align-items:center; gap:10px; }}
.tb-brand svg {{ display:block; filter:drop-shadow(0 2px 6px rgba(83,58,253,.28)); }}
.tb-name {{ font-size:21px; font-weight:500; letter-spacing:-.4px; }}
.tb-tag {{ font-size:12px; color:var(--ink-2); border-left:1px solid rgba(13,37,61,.2); padding-left:10px; margin-left:2px; }}
.tb-user {{ display:flex; align-items:center; gap:10px; background:rgba(255,255,255,.82); border:1px solid rgba(227,232,238,.95); border-radius:9999px; padding:5px 6px 5px 16px; backdrop-filter:blur(6px); box-shadow:var(--shadow-1); }}
.tb-who {{ text-align:right; line-height:1.2; }}
.tb-n {{ font-size:14px; font-weight:500; }}
.tb-r {{ font-size:11.5px; color:var(--mute); }}
.avatar {{ width:34px; height:34px; border-radius:50%; background:linear-gradient(135deg,#7a6bff,#533afd); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:500; font-size:15px; }}

/* complaint first, then the takeaway */
.said {{ background:var(--soft); border:1px solid var(--hair); border-left:4px solid var(--primary); border-radius:12px; padding:20px 24px; margin:6px 0 18px; }}
.said .sl2 {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--mute); margin-bottom:8px; }}
.said .q {{ font-size:18px; line-height:1.6; font-weight:300; letter-spacing:-.1px; margin:0; }}
.said .meta2 {{ font-size:12.5px; color:var(--mute); margin-top:10px; }}
.section-label {{ font-size:10px; font-weight:500; letter-spacing:.1px; text-transform:uppercase; color:var(--mute); margin:4px 0 8px; }}
@media (max-width:640px) {{ .tb-tag {{ display:none; }} .tb-who {{ display:none; }} .tb-user {{ padding-left:6px; }} }}
</style>



"""

"""
app.py

Simple internal SEO keyword research tool.

Flow:
1. User enters a seed keyword and picks a location + language in a single
   top search bar.
2. DataForSEO returns top organic results, People Also Ask, related keywords,
   and keyword-level metrics (search volume, CPC, competition, difficulty,
   monthly trend).
3. Gemini turns that raw data into NLP keyword ideas and fan-out query ideas,
   each scored 0-100 for relevance, and also scores the People Also Ask
   questions for relevance.
4. Real DataForSEO search volume is shown only for the primary keyword and
   secondary (related) keywords. NLP keywords, fan-out queries, and People
   Also Ask show Gemini's relevance score instead.
5. Everything is displayed in a light, Ahrefs-style keyword-overview layout:
   a keyword-difficulty gauge, search volume with trend, a 2x2 keyword-ideas
   grid, and the top 10 organic results.

No export, no database, no login. Run with: streamlit run app.py
"""

import html
import os
from urllib.parse import urlparse

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from dataforseo_client import fetch_serp_data, fetch_keyword_overview, DataForSEOError
from gemini_client import generate_keyword_insights, GeminiError

load_dotenv()

# When deployed on Streamlit Community Cloud, credentials are set via the
# app's "Secrets" panel (st.secrets) instead of a local .env file. Bridge
# them into os.environ so dataforseo_client.py / gemini_client.py - which
# only know about os.getenv() - work unchanged in both environments.
for _key in ("DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD", "GEMINI_API_KEY", "GEMINI_MODEL"):
    if not os.getenv(_key):
        try:
            if _key in st.secrets:
                os.environ[_key] = st.secrets[_key]
        except Exception:
            pass  # no secrets.toml present (e.g. running locally) - fine, .env covers it

# How many secondary (related) keywords get their own search-volume lookup.
MAX_SECONDARY_TO_ENRICH = 12

# location name -> DataForSEO location_code (used for the SERP call)
LOCATIONS = {
    "United States": 2840,
    "United Arab Emirates": 2784,
    "Saudi Arabia": 2682,
    "Oman": 2512,
    "Qatar": 2634,
    "Iraq": 2368,
}

# language name -> DataForSEO language_code
LANGUAGES = {
    "English": "en",
    "Arabic": "ar",
}

st.set_page_config(page_title="SEO Keyword Research Tool", page_icon="\U0001F4C8", layout="wide")

CUSTOM_CSS = """<style>
#MainMenu, footer, header[data-testid="stHeader"], [data-testid="stToolbar"] { visibility: hidden; height: 0; }
.block-container { padding-top: 0rem; padding-bottom: 2rem; max-width: 1300px; }
body, .stApp { background-color: #f3f5f9; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 10px !important; }

.topbar { background: #14213d; padding: 14px 26px; margin: 0 0 18px 0; display: flex; align-items: center; justify-content: space-between; border-radius: 0 0 10px 10px; }
.topbar-left { display: flex; align-items: center; gap: 10px; }
.topbar-title { color: #ffffff; font-size: 1.15rem; font-weight: 800; }
.topbar-sub { color: #93a3c4; font-size: 12px; }

.search-bar-form .stButton button, .search-bar-form button[kind="formSubmit"] { background: #ff6c37; color: white; border: none; border-radius: 8px; font-weight: 700; height: 42px; margin-top: 1.6rem; }
.search-bar-form .stButton button:hover { background: #e85a2a; }

.breadcrumb { color: #6b7280; font-size: 12.5px; margin-bottom: 2px; }
.page-title { font-size: 1.6rem; font-weight: 800; color: #111827; margin-bottom: 2px; }
.page-sub { color: #6b7280; font-size: 13px; margin-bottom: 1.1rem; }

.card-label { color: #6b7280; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em; margin-bottom: 6px; }
.card-value { color: #111827; font-size: 26px; font-weight: 800; line-height: 1.15; }
.card-sub { color: #6b7280; font-size: 11.5px; margin-top: 4px; }

.kd-wrap { text-align: center; }
.kd-label { text-align: center; margin-top: 8px; font-size: 12.5px; font-weight: 700; }

.trend-up { color: #16a34a; } .trend-down { color: #dc2626; } .trend-flat { color: #9ca3af; }

.band { display: flex; justify-content: space-around; align-items: center; text-align: center; }
.band-item { padding: 0 12px; }
.band-label { color: #6b7280; font-size: 12px; margin-bottom: 4px; }
.band-value { color: #111827; font-size: 18px; font-weight: 800; }

.section-title { font-size: 14.5px; font-weight: 700; color: #111827; margin-bottom: 14px; }

.idea-header-row { display: flex; justify-content: space-between; align-items: center; padding: 0 2px 8px 2px; border-bottom: 2px solid #e5e7eb; margin-bottom: 4px; }
.idea-header-label { color: #9ca3af; font-size: 10.5px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.03em; }

.idea-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 2px; border-bottom: 1px solid #f0f1f4; font-size: 13.5px; }
.idea-row:last-child { border-bottom: none; }
.idea-kw { color: #2f6fed; }
.idea-plain { color: #1f2937; }
.idea-meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.idea-vol { color: #111827; font-weight: 600; white-space: nowrap; font-size: 12.5px; }
.idea-vol-empty { color: #c1c5cc; white-space: nowrap; font-size: 12.5px; }

.rel-chip { font-size: 10.5px; font-weight: 800; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
.rel-high { background: rgba(22,163,74,0.12); color: #16a34a; }
.rel-med { background: rgba(245,158,11,0.16); color: #b45309; }
.rel-low { background: rgba(107,114,128,0.14); color: #6b7280; }

.paa-item { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 2px; border-bottom: 1px solid #f0f1f4; color: #1f2937; font-size: 13.5px; }
.paa-item:last-child { border-bottom: none; }

.result-card { display: flex; gap: 12px; align-items: flex-start; padding: 14px; border: 1px solid #edeef2; border-radius: 10px; margin-bottom: 10px; background: #fdfdfe; transition: background 0.15s ease, border-color 0.15s ease; }
.result-card:last-child { margin-bottom: 0; }
.result-card:hover { background: #f5f8ff; border-color: #c7d7fe; }
.result-badge { min-width: 26px; height: 26px; border-radius: 50%; background: #eef2ff; color: #2f6fed; font-weight: 800; font-size: 12px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px; }
.result-body { flex: 1; min-width: 0; }
.result-title-link { color: #111827; font-weight: 700; font-size: 14px; text-decoration: none; }
.result-title-link:hover { color: #2f6fed; text-decoration: underline; }
.result-display-url { color: #16a34a; font-size: 12px; margin-top: 3px; word-break: break-all; }
.result-desc { color: #6b7280; font-size: 12.5px; margin-top: 5px; line-height: 1.45; }

.footer-note { text-align: center; color: #9ca3af; font-size: 12px; margin-top: 1.5rem; }
</style>"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text)) if text is not None else ""


def format_number(n):
    if n is None:
        return None
    try:
        n = float(n)
    except (TypeError, ValueError):
        return None
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}K".replace(".0K", "K")
    return str(int(n))


def format_trend(pct):
    if pct is None:
        return '<span class="trend-flat">—</span>'
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return '<span class="trend-flat">—</span>'
    if pct > 0:
        return f'<span class="trend-up">&#9650; {pct:.0f}%</span>'
    if pct < 0:
        return f'<span class="trend-down">&#9660; {abs(pct):.0f}%</span>'
    return '<span class="trend-flat">– 0%</span>'


def kd_band(score):
    if score is None:
        return "#9ca3af", "No data"
    if score < 30:
        return "#16a34a", "Easy"
    if score < 60:
        return "#f59e0b", "Medium"
    if score < 80:
        return "#f97316", "Hard"
    return "#dc2626", "Very Hard"


def render_kd_gauge(container, score):
    color, label = kd_band(score)
    display_score = score if score is not None else 0
    angle = max(0, min(360, display_score / 100 * 360))
    score_text = str(int(score)) if score is not None else "—"
    inner = (
        '<div class="card-label" style="text-align:center;">Keyword Difficulty</div>'
        '<div class="kd-wrap">'
        f'<div style="position:relative;width:96px;height:96px;margin:4px auto 0 auto;'
        f'border-radius:50%;background:conic-gradient({color} 0deg {angle}deg,#e5e7eb {angle}deg 360deg);'
        'display:flex;align-items:center;justify-content:center;">'
        '<div style="width:72px;height:72px;background:#ffffff;border-radius:50%;'
        'display:flex;align-items:center;justify-content:center;">'
        f'<div style="font-size:24px;font-weight:800;color:{color};">{score_text}</div>'
        '</div></div>'
        f'<div class="kd-label" style="color:{color};">{label}</div>'
        '</div>'
    )
    with container:
        with st.container(border=True):
            st.markdown(inner, unsafe_allow_html=True)


def simple_card(container, label, value_html, sub_html=""):
    inner = (
        f'<div class="card-label">{esc(label)}</div>'
        f'<div class="card-value">{value_html}</div>'
        f'{sub_html}'
    )
    with container:
        with st.container(border=True):
            st.markdown(inner, unsafe_allow_html=True)


def display_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc.replace("www.", "") or url
    except Exception:
        return url


def relevance_chip(score):
    if score is None:
        return ""
    try:
        score = int(score)
    except (TypeError, ValueError):
        return ""
    if score >= 70:
        cls = "rel-high"
    elif score >= 40:
        cls = "rel-med"
    else:
        cls = "rel-low"
    return f'<span class="rel-chip {cls}">{score}</span>'


def volume_html(keyword: str, overview: dict) -> str:
    kw_overview = overview.get(keyword.lower())
    vol = format_number(kw_overview["search_volume"]) if kw_overview else None
    if vol is not None:
        return f'<span class="idea-vol">{vol}</span>'
    return '<span class="idea-vol-empty">—</span>'


def idea_header_row(right_label: str) -> str:
    return (
        '<div class="idea-header-row">'
        '<span class="idea-header-label">Keyword</span>'
        f'<span class="idea-header-label">{esc(right_label)}</span>'
        '</div>'
    )


def render_relevance_list(items, text_key):
    """Renders a list of {text_key: str, "relevance": int|None} as idea rows,
    each showing only a relevance chip (no search volume)."""
    rows = []
    for item in items:
        text = item.get(text_key, "")
        rows.append(
            '<div class="idea-row">'
            f'<span class="idea-plain">{esc(text)}</span>'
            f'<div class="idea-meta">{relevance_chip(item.get("relevance"))}</div>'
            '</div>'
        )
    return "".join(rows)


# ---------------- Top bar ----------------
st.markdown(
    '<div class="topbar"><div class="topbar-left">'
    '<span style="font-size:22px;">\U0001F4C8</span>'
    '<div><div class="topbar-title">SEO Keyword Research</div>'
    '<div class="topbar-sub">Powered by DataForSEO + Gemini</div></div>'
    '</div></div>',
    unsafe_allow_html=True,
)

# ---------------- Top search bar ----------------
st.markdown('<div class="search-bar-form">', unsafe_allow_html=True)
with st.form("keyword_form"):
    s1, s2, s3, s4 = st.columns([3, 1, 1, 0.7])
    with s1:
        seed_keyword = st.text_input(
            "Primary Keyword", placeholder="e.g. air compressor", label_visibility="collapsed"
        )
    with s2:
        location_name = st.selectbox("Location", list(LOCATIONS.keys()), label_visibility="collapsed")
    with s3:
        language_name = st.selectbox("Language", list(LANGUAGES.keys()), label_visibility="collapsed")
    with s4:
        submitted = st.form_submit_button("\U0001F50E Search")
st.markdown('</div>', unsafe_allow_html=True)

if not submitted:
    st.info("Enter a seed keyword above and click **Search** to get started.")
    st.stop()

if not seed_keyword.strip():
    st.warning("Please enter a seed keyword.")
    st.stop()

seed_keyword = seed_keyword.strip()
location_code = LOCATIONS[location_name]
language_code = LANGUAGES[language_name]

with st.spinner("Fetching SERP data from DataForSEO..."):
    try:
        serp_data = fetch_serp_data(seed_keyword, location_code, language_code)
    except DataForSEOError as exc:
        st.error(f"DataForSEO error: {exc}")
        st.stop()

secondary_keywords = serp_data.get("related_keywords", [])
paa = serp_data.get("people_also_ask", [])
organic_results = serp_data.get("organic_results", [])

with st.spinner("Generating keyword insights with Gemini..."):
    try:
        insights = generate_keyword_insights(seed_keyword, serp_data)
    except GeminiError as exc:
        st.error(f"Gemini error: {exc}")
        st.stop()

nlp_keywords = insights.get("nlp_keywords", [])
fan_out_queries = insights.get("fan_out_queries", [])
paa_relevance = insights.get("paa_relevance", [])

# Align PAA relevance scores with the PAA list by position (Gemini is asked
# to preserve order/count; if it didn't, fall back to no score rather than
# risk pairing a score with the wrong question).
if len(paa_relevance) == len(paa):
    paa_scores = [entry.get("relevance") for entry in paa_relevance]
else:
    paa_scores = [None] * len(paa)

# Search volume is only shown for the primary keyword and secondary
# (related) keywords - NLP keywords, fan-out queries, and PAA use Gemini's
# relevance score instead, so they don't need a DataForSEO lookup.
keywords_to_enrich = [seed_keyword] + secondary_keywords[:MAX_SECONDARY_TO_ENRICH]

with st.spinner("Fetching search volume, CPC, and trend data..."):
    try:
        overview = fetch_keyword_overview(keywords_to_enrich, location_name, language_code)
    except DataForSEOError as exc:
        st.error(f"DataForSEO error (keyword overview): {exc}")
        overview = {}

primary_overview = overview.get(seed_keyword.lower(), {})

# ---------------- Page header ----------------
st.markdown('<div class="breadcrumb">Keyword Research &rsaquo; Overview</div>', unsafe_allow_html=True)
st.markdown(f'<div class="page-title">Overview: {esc(seed_keyword)}</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="page-sub">{esc(location_name)} &middot; {esc(language_name)}</div>',
    unsafe_allow_html=True,
)

# ---------------- Row 1: KD gauge, Search volume, CPC, Competition ----------------
r1c1, r1c2, r1c3, r1c4 = st.columns(4)

render_kd_gauge(r1c1, primary_overview.get("keyword_difficulty"))

volume = primary_overview.get("search_volume")
volume_display = format_number(volume) or "—"
monthly = primary_overview.get("monthly_searches") or {}
with r1c2:
    with st.container(border=True):
        st.markdown(
            f'<div class="card-label">Search Volume</div>'
            f'<div class="card-value">{volume_display}</div>'
            f'<div class="card-sub">monthly avg. searches</div>',
            unsafe_allow_html=True,
        )
        if monthly:
            trend_df = (
                pd.DataFrame([{"Month": m, "Vol": v} for m, v in monthly.items()])
                .sort_values("Month")
                .set_index("Month")
            )
            st.bar_chart(trend_df, height=90)

cpc = primary_overview.get("cpc")
simple_card(
    r1c3, "CPC",
    f"${cpc:.2f}" if cpc is not None else "—",
    '<div class="card-sub">avg. cost per click</div>',
)

competition = primary_overview.get("competition_level")
competition_display = competition.title() if isinstance(competition, str) else "—"
trend = primary_overview.get("search_volume_trend") or {}
simple_card(
    r1c4, "Competition",
    esc(competition_display),
    f'<div class="card-sub">{format_trend(trend.get("yearly"))} year over year</div>',
)

# ---------------- Row 2: quick facts band ----------------
with st.container(border=True):
    st.markdown(
        '<div class="band">'
        '<div class="band-item"><div class="band-label">Primary Keyword</div>'
        f'<div class="band-value">{esc(seed_keyword)}</div></div>'
        '<div class="band-item"><div class="band-label">Secondary Keywords</div>'
        f'<div class="band-value">{len(secondary_keywords)}</div></div>'
        '<div class="band-item"><div class="band-label">People Also Ask</div>'
        f'<div class="band-value">{len(paa)}</div></div>'
        '<div class="band-item"><div class="band-label">Top Results</div>'
        f'<div class="band-value">{len(organic_results)}</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )

st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

# ---------------- Row 3: Keyword ideas grid (2x2) ----------------
st.markdown('<div class="section-title">Keyword Ideas</div>', unsafe_allow_html=True)

ideas_row1 = st.columns(2)
ideas_row2 = st.columns(2)

with ideas_row1[0]:
    with st.container(border=True):
        st.markdown('<div class="section-title">Secondary Keywords</div>', unsafe_allow_html=True)
        if secondary_keywords:
            st.markdown(idea_header_row("Search Volume"), unsafe_allow_html=True)
            rows = []
            for kw in secondary_keywords:
                rows.append(
                    '<div class="idea-row">'
                    f'<span class="idea-kw">{esc(kw)}</span>'
                    f'<div class="idea-meta">{volume_html(kw, overview)}</div>'
                    '</div>'
                )
            st.markdown("".join(rows), unsafe_allow_html=True)
        else:
            st.caption("No secondary keywords found.")

with ideas_row1[1]:
    with st.container(border=True):
        st.markdown('<div class="section-title">NLP / Semantic Keywords</div>', unsafe_allow_html=True)
        if nlp_keywords:
            st.markdown(idea_header_row("Relevance"), unsafe_allow_html=True)
            st.markdown(render_relevance_list(nlp_keywords, "keyword"), unsafe_allow_html=True)
        else:
            st.caption("No NLP keywords returned.")

st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

with ideas_row2[0]:
    with st.container(border=True):
        st.markdown('<div class="section-title">Fan-out Queries</div>', unsafe_allow_html=True)
        if fan_out_queries:
            st.markdown(idea_header_row("Relevance"), unsafe_allow_html=True)
            st.markdown(render_relevance_list(fan_out_queries, "query"), unsafe_allow_html=True)
        else:
            st.caption("No fan-out queries returned.")

with ideas_row2[1]:
    with st.container(border=True):
        st.markdown('<div class="section-title">People Also Ask</div>', unsafe_allow_html=True)
        if paa:
            st.markdown(idea_header_row("Relevance"), unsafe_allow_html=True)
            rows = []
            for question, score in zip(paa, paa_scores):
                rows.append(
                    '<div class="paa-item">'
                    f'<span>{esc(question)}</span>'
                    f'<div class="idea-meta">{relevance_chip(score)}</div>'
                    '</div>'
                )
            st.markdown("".join(rows), unsafe_allow_html=True)
        else:
            st.caption("No People Also Ask questions found.")

st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

# ---------------- Row 4: Top 10 Google Results ----------------
with st.container(border=True):
    st.markdown('<div class="section-title">Top 10 Google Results</div>', unsafe_allow_html=True)
    if organic_results:
        cards = []
        for r in organic_results:
            title = esc(r.get("title") or "(no title)")
            url = esc(r.get("url") or "")
            domain = esc(display_domain(r.get("url") or ""))
            desc = esc(r.get("description") or "")
            cards.append(
                f'<div class="result-card">'
                f'<div class="result-badge">{r.get("position")}</div>'
                f'<div class="result-body">'
                f'<a class="result-title-link" href="{url}" target="_blank">{title}</a>'
                f'<div class="result-display-url">{domain}</div>'
                f'<div class="result-desc">{desc}</div>'
                f'</div>'
                f'</div>'
            )
        st.markdown("".join(cards), unsafe_allow_html=True)
    else:
        st.caption("No organic results found for this query.")

st.markdown(
    '<div class="footer-note">Built with Streamlit &middot; Data provided by DataForSEO &middot; Insights by Gemini</div>',
    unsafe_allow_html=True,
)

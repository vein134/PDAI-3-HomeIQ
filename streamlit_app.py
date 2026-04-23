"""
HomeIQ v3 - Smart Relocation Advisor
Run: streamlit run streamlit_app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import json
import openai
from fpdf import FPDF
from datetime import date

from core.regions import REGIONS, QOL_DIMS, QOL_LABELS, COMMUTE_COSTS, HMRC_MILEAGE_RATE, refresh_live_prices
from core.ons_hpi import get_live_prices
from core.tax import compute_uk_tax, compute_stamp_duty
from core.scoring import compute_monthly_budget, compute_regional_score, compute_affordability, rank_all_regions
from core.monte_carlo import run_regional_monte_carlo
from core.live_data import fetch_live_data
from api.database import (
    init_db, get_or_create_user, save_profile, get_active_profile,
    get_all_profiles, set_active_profile, delete_profile,
    save_search, get_search_history, save_comparison, get_saved_comparisons, delete_comparison,
    save_chat_session, update_chat_session, get_chat_sessions, get_chat_session,
)
from rag.engine import RAGEngine
from core.careers import INDUSTRIES, REGION_INDUSTRY_SCORES, get_career_score, get_salary_projection, get_region_career_summary, compute_career_adjusted_score
from core.adzuna import fetch_all_job_stats
from app.theme import GLOBAL_CSS, PLOT_THEME, C, REGION_COLORS, hex_to_rgba
from api.client import (
    is_api_available, api_get_live_data, api_rank_regions,
    api_affordability, api_monte_carlo, api_chat, api_rag_stats,
)

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="HomeIQ v3 - Smart Relocation Advisor", page_icon="🏠", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Init DB ──────────────────────────────────────────────────────────────
init_db()

# ── API key ──────────────────────────────────────────────────────────────
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "") or st.secrets.get("OPENAI_API_KEY", "")

# ── API backend detection ───────────────────────────────────────────────
USE_API = is_api_available()

# ── Session defaults ─────────────────────────────────────────────────────
if "user_id" not in st.session_state:
    st.session_state.user_id = get_or_create_user("default")
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = None

# ── Live data ────────────────────────────────────────────────────────────
refresh_live_prices()
if USE_API:
    live = api_get_live_data()
else:
    live = fetch_live_data()

# ── RAG engine ───────────────────────────────────────────────────────────
@st.cache_resource
def get_rag_engine():
    if OPENAI_KEY:
        engine = RAGEngine(OPENAI_KEY)
        engine.build_index()
        return engine
    return None

rag_engine = get_rag_engine()

# ── LLM: Life Brief Parser ──────────────────────────────────────────────
def parse_life_brief(text, api_key):
    client = openai.OpenAI(api_key=api_key)
    system = """Extract structured data from a user's relocation brief. Return JSON with these fields:
    - salary (int, annual GBP, default 50000)
    - partner_salary (int, default 0)
    - budget (int or null, property budget)
    - deposit_pct (int, 5-50, default 15)
    - job_type (string: "remote", "hybrid", "office", default "hybrid")
    - priorities (list of strings from: green_space, schools, safety, culture, healthcare, commute, family_friendly, affordability)
    - current_savings (int, default 0)
    Return ONLY valid JSON, no markdown."""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": text}],
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


# ── LLM: Neighbourhood Finder ───────────────────────────────────────────
def find_neighbourhoods(region, profile, budget, live_data, api_key):
    client = openai.OpenAI(api_key=api_key)
    priorities_str = ", ".join(profile.get("priorities", [])) or "general quality of life"
    job_type = profile.get("job_type", "hybrid")
    system = f"""You are a UK property expert. Find 5 specific neighbourhoods/towns in {region} that match:
- Budget: ~£{budget:,}
- Priorities: {priorities_str}
- Work style: {job_type}
Return JSON: {{"neighbourhoods": [
  {{"name": "...", "postcode_area": "...", "avg_property_price": int,
    "price_range": "£X - £Y", "school_rating": "...", "transport": "...",
    "description": "2 sentences", "match_score": int (0-100)}}
]}}
Prices must be realistic for {date.today().year}. Return ONLY valid JSON."""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": f"Find neighbourhoods in {region}"}],
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


# ── PDF Report ───────────────────────────────────────────────────────────
def generate_pdf(profile, rankings, live_data):
    NAVY = (10, 14, 26)
    NAVY2 = (17, 24, 39)
    NAVY3 = (26, 34, 53)
    NAVY4 = (36, 48, 72)
    GOLD = (201, 168, 76)
    CREAM = (245, 240, 232)
    WHITE = (255, 255, 255)
    MUTED = (136, 153, 170)
    GREEN = (45, 212, 160)
    RED = (248, 113, 113)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Full-page navy background
    pdf.set_fill_color(*NAVY)
    pdf.rect(0, 0, 210, 297, "F")

    # Header bar
    pdf.set_fill_color(*NAVY3)
    pdf.rect(0, 0, 210, 45, "F")
    pdf.set_fill_color(*GOLD)
    pdf.rect(0, 45, 210, 1, "F")

    # Title
    pdf.set_y(10)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 12, "HomeIQ v3", ln=True, align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 7, "Smart Relocation Advisor - Report", ln=True, align="C")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    gen_text = "Generated: {} | BoE Rate: {}% | 5yr Fixed: {}% | CPI: {}%".format(
        date.today().isoformat(), live_data["base_rate_current"],
        live_data["rate_5yr_current"], live_data["cpi_current"])
    pdf.cell(0, 6, gen_text, ln=True, align="C")

    pdf.ln(8)

    # Profile section
    pdf.set_fill_color(*NAVY3)
    pdf.set_draw_color(*NAVY4)
    pdf.rect(15, pdf.get_y(), 180, 32, "DF")
    pdf.set_x(20)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, "YOUR PROFILE", ln=True)
    pdf.set_x(20)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*CREAM)
    sal = profile.get("salary", 50000)
    psal = profile.get("partner_salary", 0)
    dep = profile.get("deposit_pct", 15)
    pdf.cell(60, 6, "Salary: GBP {:,}".format(int(sal)))
    pdf.cell(60, 6, "Partner: GBP {:,}".format(int(psal)))
    pdf.cell(60, 6, "Deposit: {}%".format(dep), ln=True)
    pdf.set_x(20)
    prios = ", ".join(profile.get("priorities", [])) or "None set"
    job = profile.get("job_type", "hybrid")
    pdf.cell(90, 6, "Priorities: {}".format(prios))
    pdf.cell(90, 6, "Work style: {}".format(job), ln=True)

    pdf.ln(8)

    # Rankings table
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*GOLD)
    pdf.set_x(15)
    pdf.cell(0, 8, "REGIONAL RANKINGS", ln=True)

    # Table header
    col_widths = [8, 34, 16, 18, 14, 14, 22, 24, 24]
    headers = ["#", "Region", "Score", "Financial", "QoL", "Career", "Mortgage/mo", "Disposable/mo", "Avg Price"]
    pdf.set_fill_color(*NAVY4)
    pdf.set_text_color(*GOLD)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_x(15)
    for j, h in enumerate(headers):
        pdf.cell(col_widths[j], 7, h, border=0, fill=True, align="C")
    pdf.ln()

    # Table rows
    pdf.set_font("Helvetica", "", 8)
    for i, r in enumerate(rankings[:12], 1):
        if i % 2 == 0:
            pdf.set_fill_color(*NAVY3)
        else:
            pdf.set_fill_color(*NAVY2)
        pdf.set_text_color(*CREAM)
        pdf.set_x(15)
        pdf.cell(col_widths[0], 6, str(i), border=0, fill=True, align="C")
        pdf.set_font("Helvetica", "B" if i <= 3 else "", 8)
        if i <= 3:
            pdf.set_text_color(*GOLD)
        else:
            pdf.set_text_color(*CREAM)
        pdf.cell(col_widths[1], 6, r["region"], border=0, fill=True)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*CREAM)
        pdf.cell(col_widths[2], 6, str(r["composite"]), border=0, fill=True, align="C")
        pdf.cell(col_widths[3], 6, str(r["financial_score"]), border=0, fill=True, align="C")
        pdf.cell(col_widths[4], 6, str(r["qol_score"]), border=0, fill=True, align="C")
        pdf.cell(col_widths[5], 6, str(r["career_score"]), border=0, fill=True, align="C")
        pdf.cell(col_widths[6], 6, "GBP {:,}".format(r["monthly_mortgage"]), border=0, fill=True, align="R")
        disp = r["disposable_monthly"]
        if disp >= 0:
            pdf.set_text_color(*GREEN)
        else:
            pdf.set_text_color(*RED)
        pdf.cell(col_widths[7], 6, "GBP {:,}".format(disp), border=0, fill=True, align="R")
        pdf.set_text_color(*CREAM)
        pdf.cell(col_widths[8], 6, "GBP {:,}".format(r["price"]), border=0, fill=True, align="R")
        pdf.ln()

    pdf.ln(6)

    # Top recommendation
    top = rankings[0]
    pdf.set_fill_color(*NAVY3)
    pdf.set_draw_color(*GOLD)
    pdf.rect(15, pdf.get_y(), 180, 22, "DF")
    pdf.set_x(20)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 7, "TOP RECOMMENDATION", ln=True)
    pdf.set_x(20)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*WHITE)
    rec_text = "{} - Score: {} | Affordability: {}x income | Monthly mortgage: GBP {:,} | Disposable: GBP {:,}/mo".format(
        top["region"], top["composite"], top["affordability_ratio"],
        top["monthly_mortgage"], top["disposable_monthly"])
    pdf.cell(0, 6, rec_text, ln=True)

    pdf.ln(6)

    # Affordability quick check for top 3
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*GOLD)
    pdf.set_x(15)
    pdf.cell(0, 8, "TOP 3 AFFORDABILITY SNAPSHOT", ln=True)

    for r in rankings[:3]:
        region_data = REGIONS[r["region"]]
        af = compute_affordability(sal, psal, r["region"], dep, int(profile.get("current_savings", 0)))
        pdf.set_fill_color(*NAVY3)
        pdf.set_x(15)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*WHITE)
        pdf.cell(180, 6, r["region"], border=0, fill=True, ln=True)
        pdf.set_x(15)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*CREAM)
        pdf.set_fill_color(*NAVY2)
        detail = "Max borrow: GBP {:,} | Loan needed: GBP {:,} | {} | Upfront: GBP {:,} | Shortfall: GBP {:,}".format(
            af["max_borrowing"], af["loan_needed"],
            "APPROVED" if af["can_borrow"] else "EXCEEDS LIMIT",
            af["total_upfront"], af["shortfall"])
        pdf.cell(180, 5, detail, border=0, fill=True, ln=True)

    # Footer
    pdf.set_y(-20)
    pdf.set_fill_color(*NAVY4)
    pdf.rect(0, pdf.get_y(), 210, 20, "F")
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, "HomeIQ v3 | Smart Relocation Advisor | RAG-Powered | API-Driven | Not financial advice", ln=True, align="C")
    pdf.cell(0, 5, "Data: Bank of England IADB | ONS API | HM Land Registry HPI | Adzuna Jobs API", align="C")

    return bytes(pdf.output())


# ── Analysis settings (session state defaults) ───────────────────────────
financial_weight = st.session_state.get("financial_weight", 50)
deposit_pct = st.session_state.get("deposit_pct", 15)
horizon = st.session_state.get("horizon", 10)


def get_active_profile_data():
    db_profile = get_active_profile(st.session_state.user_id)
    if db_profile:
        return db_profile
    return {
        "salary": st.session_state.get("salary", 50000),
        "partner_salary": st.session_state.get("partner_salary", 0),
        "budget": st.session_state.get("budget"),
        "deposit_pct": deposit_pct,
        "job_type": st.session_state.get("job_type", "hybrid"),
        "priorities": st.session_state.get("priorities", []),
        "current_savings": st.session_state.get("current_savings", 0),
    }


profile = get_active_profile_data()
if USE_API:
    rankings = api_rank_regions(profile, financial_weight, deposit_pct)
else:
    rankings = rank_all_regions(profile, live, financial_weight, deposit_pct)
top_region = rankings[0]["region"]

# ── Hero header ──────────────────────────────────────────────────────────
sources = live.get("_sources", {})
live_count = sum(1 for v in sources.values() if v == "live")
hpi_prices_hero, _ = get_live_prices()
if hpi_prices_hero:
    live_count += 1
api_dot = "#2dd4a0" if USE_API else "#fb923c"
api_label = "API Connected" if USE_API else "Direct Mode"

st.markdown("""
<div style="text-align:center;padding:24px 0 20px;border-bottom:1px solid #243048;margin-bottom:16px;">
    <div style="display:flex;align-items:center;justify-content:center;gap:14px;">
        <svg width="44" height="44" viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="2" y="2" width="40" height="40" rx="10" fill="#1a2235" stroke="#c9a84c" stroke-width="2"/>
            <path d="M22 12L10 22h4v10h6v-6h4v6h6V22h4L22 12z" fill="#c9a84c"/>
            <circle cx="32" cy="14" r="6" fill="#2dd4a0" stroke="#1a2235" stroke-width="2"/>
            <path d="M30 14h4M32 12v4" stroke="#1a2235" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <div style="font-family:'Playfair Display',serif;font-size:48px;font-weight:900;color:#fff;letter-spacing:-0.02em;">
            Home<span style="color:#c9a84c;">IQ</span>
        </div>
    </div>
    <div style="color:#8899aa;font-size:14px;margin-top:6px;font-family:'DM Sans',sans-serif;letter-spacing:0.08em;text-transform:uppercase;">
        Smart Relocation Advisor
    </div>
    <div style="display:flex;justify-content:center;gap:20px;margin-top:16px;font-family:'DM Sans',sans-serif;font-size:13px;">
        <span style="display:inline-flex;align-items:center;gap:6px;background:#1a2235;border:1px solid #243048;
               border-radius:20px;padding:5px 14px;color:#f5f0e8;">
            <span style="width:8px;height:8px;border-radius:50%;background:{api_dot};"></span>{api_label}
        </span>
        <span style="display:inline-flex;align-items:center;gap:6px;background:#1a2235;border:1px solid #243048;
               border-radius:20px;padding:5px 14px;color:#f5f0e8;">
            <span style="width:8px;height:8px;border-radius:50%;background:#2dd4a0;"></span>{live_count} Live Feeds
        </span>
    </div>
</div>
""".format(api_dot=api_dot, api_label=api_label, live_count=live_count), unsafe_allow_html=True)

# ── Key metrics ──────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Top Region", top_region, "Score {}".format(rankings[0]['composite']))
m2.metric("BoE Base Rate", "{}%".format(live['base_rate_current']))
m3.metric("2yr Fixed", "{}%".format(live['rate_2yr_current']))
m4.metric("5yr Fixed", "{}%".format(live['rate_5yr_current']))
m5.metric("CPI Inflation", "{}%".format(live['cpi_current']))

# ── Tabs ─────────────────────────────────────────────────────────────────
tab_brief, tab_ranking, tab_career, tab_mc, tab_afford, tab_areas, tab_advisor, tab_profile, tab_about = st.tabs([
    "Your Brief", "Rankings", "Career & Jobs", "Monte Carlo", "Affordability",
    "Neighbourhoods", "AI Advisor", "Profiles & History", "About",
])

# ══════════════════════════════════════════════════════════════════════════
# TAB 0: ABOUT
# ══════════════════════════════════════════════════════════════════════════
with tab_about:
    st.markdown("""
    <div style="text-align:center;padding:16px 0 8px;">
        <div class="section-header" style="font-size:28px;">What is HomeIQ?</div>
        <div class="section-sub" style="max-width:700px;margin:0 auto;line-height:1.7;font-size:14px;">
            HomeIQ is a data-driven relocation advisor that helps UK home buyers find the best region
            to live in based on their financial profile, lifestyle priorities, and career goals.
            It combines <strong style="color:#c9a84c;">live economic data</strong>,
            <strong style="color:#c9a84c;">Monte Carlo simulations</strong>, and a
            <strong style="color:#c9a84c;">RAG-powered AI advisor</strong> into a single analytical platform.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Feature cards ──
    st.markdown('<div class="section-header" style="font-size:20px;margin-bottom:16px;">Core Features</div>', unsafe_allow_html=True)
    fc1, fc2, fc3, fc4 = st.columns(4)
    features = [
        (fc1, "📊", "Regional Scoring", "Ranks all 12 UK regions using a composite of financial affordability, quality-of-life metrics, and career opportunity scores — personalised to your profile."),
        (fc2, "🤖", "RAG AI Advisor", "Chat with an AI advisor backed by a Retrieval-Augmented Generation knowledge base covering UK housing guides, mortgage strategies, and government schemes."),
        (fc3, "📈", "Monte Carlo Engine", "Runs thousands of probabilistic simulations to compare the long-term financial outcome of buying vs renting across different regions."),
        (fc4, "💼", "Live Job Market", "Integrates real-time job listings and salary data from the Adzuna API, blending live market signals into career-adjusted region scores."),
    ]
    for col, icon, title, desc in features:
        with col:
            st.markdown(
                '<div class="feature-card">'
                '<span class="fc-icon">{}</span>'
                '<div class="fc-title">{}</div>'
                '<div class="fc-desc">{}</div>'
                '</div>'.format(icon, title, desc),
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    fc5, fc6, fc7, fc8 = st.columns(4)
    features2 = [
        (fc5, "🏘️", "Neighbourhood Finder", "Uses GPT-4o to suggest specific towns and neighbourhoods within a region that match your budget, priorities, and work style."),
        (fc6, "🏦", "Affordability Engine", "Full mortgage stress-test with stamp duty, solicitor fees, and a rate sensitivity chart showing danger zones across interest rate scenarios."),
        (fc7, "📄", "PDF Reports", "Generate a styled PDF report of your personalised rankings, affordability snapshots, and live market conditions — ready to share."),
        (fc8, "👤", "Persistent Profiles", "All profiles, searches, comparisons, and chat sessions are stored in a SQLite database — persistent across browser sessions."),
    ]
    for col, icon, title, desc in features2:
        with col:
            st.markdown(
                '<div class="feature-card">'
                '<span class="fc-icon">{}</span>'
                '<div class="fc-title">{}</div>'
                '<div class="fc-desc">{}</div>'
                '</div>'.format(icon, title, desc),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Architecture ──
    st.markdown('<div class="section-header" style="font-size:20px;margin-bottom:16px;">Architecture</div>', unsafe_allow_html=True)
    ac1, ac2, ac3, ac4, ac5 = st.columns(5)
    arch_items = [
        (ac1, "Streamlit Frontend", "Interactive UI, charts,\nchat interface"),
        (ac2, "FastAPI Backend", "28 REST endpoints,\nOpenAPI docs at /docs"),
        (ac3, "Core Engine", "Scoring, Monte Carlo,\ntax calculations"),
        (ac4, "RAG Pipeline", "ChromaDB vector store,\nOpenAI embeddings"),
        (ac5, "SQLite Database", "Profiles, history,\nchat sessions"),
    ]
    for col, label, desc in arch_items:
        with col:
            st.markdown(
                '<div class="arch-box">'
                '<div class="ab-label">{}</div>'
                '<div style="color:#8899aa;font-size:12px;white-space:pre-line;">{}</div>'
                '</div>'.format(label, desc),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Live Data Sources ──
    st.markdown('<div class="section-header" style="font-size:20px;margin-bottom:16px;">Live Data Sources</div>', unsafe_allow_html=True)
    about_sources = live.get("_sources", {})
    hpi_p_about, hpi_m_about = get_live_prices()
    ds1, ds2 = st.columns(2)
    data_sources = [
        ("Bank of England IADB", "Base rate, 2yr and 5yr fixed mortgage rates", about_sources.get("base_rate", "fallback") == "live"),
        ("ONS Timeseries", "CPI inflation and average earnings growth", about_sources.get("cpi", "fallback") == "live"),
        ("HM Land Registry HPI", "Average house prices for all 12 UK regions via SPARQL", bool(hpi_p_about)),
        ("Adzuna Jobs API", "Live job listings and average salaries by region and industry", True),
    ]
    for i, (name, desc, is_live) in enumerate(data_sources):
        col = ds1 if i < 2 else ds2
        dot_color = "#2dd4a0" if is_live else "#f87171"
        status_text = "LIVE" if is_live else "FALLBACK"
        with col:
            st.markdown(
                '<div class="source-badge">'
                '<span class="sb-status" style="background:{};"></span>'
                '<div>'
                '<div class="sb-name">{} <span style="color:{};font-size:11px;font-weight:600;margin-left:6px;">{}</span></div>'
                '<div class="sb-desc">{}</div>'
                '</div>'
                '</div>'.format(dot_color, name, dot_color, status_text, desc),
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Tech Stack ──
    st.markdown('<div class="section-header" style="font-size:20px;margin-bottom:16px;">Tech Stack</div>', unsafe_allow_html=True)
    ts1, ts2, ts3 = st.columns(3)
    with ts1:
        st.markdown("""
        <div class="arch-box" style="text-align:left;">
            <div class="ab-label" style="margin-bottom:8px;">Frontend</div>
            <div style="color:#f5f0e8;font-size:13px;line-height:1.8;">
                Streamlit (Python)<br>
                Plotly (interactive charts)<br>
                Custom CSS theme<br>
                fpdf2 (PDF generation)
            </div>
        </div>
        """, unsafe_allow_html=True)
    with ts2:
        st.markdown("""
        <div class="arch-box" style="text-align:left;">
            <div class="ab-label" style="margin-bottom:8px;">Backend</div>
            <div style="color:#f5f0e8;font-size:13px;line-height:1.8;">
                FastAPI + Uvicorn<br>
                SQLite + raw SQL<br>
                ChromaDB (vector DB)<br>
                OpenAI GPT-4o + Embeddings
            </div>
        </div>
        """, unsafe_allow_html=True)
    with ts3:
        st.markdown("""
        <div class="arch-box" style="text-align:left;">
            <div class="ab-label" style="margin-bottom:8px;">Infrastructure</div>
            <div style="color:#f5f0e8;font-size:13px;line-height:1.8;">
                Docker (multi-service)<br>
                Streamlit Cloud (deploy)<br>
                REST API (28 endpoints)<br>
                SPARQL queries (Land Registry)
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── How to use ──
    st.markdown('<div class="section-header" style="font-size:20px;margin-bottom:16px;">How to Use</div>', unsafe_allow_html=True)
    steps = [
        ("1", "Set your profile", "Go to <strong>Your Brief</strong> and either describe your situation in plain English (AI parses it) or fill in the manual form. Set your salary, budget, priorities, and work style."),
        ("2", "Explore rankings", "The <strong>Rankings</strong> tab shows all 12 UK regions scored and ranked for your profile. Compare regions side-by-side with radar charts and download a PDF report."),
        ("3", "Run simulations", "Use <strong>Monte Carlo</strong> to simulate thousands of buy-vs-rent scenarios. The <strong>Affordability</strong> tab stress-tests your mortgage at different interest rates."),
        ("4", "Ask the advisor", "The <strong>AI Advisor</strong> can answer questions, run comparisons, check affordability, and search the knowledge base — all through natural conversation."),
    ]
    step_cols = st.columns(4)
    for col, (num, title, desc) in zip(step_cols, steps):
        with col:
            st.markdown(
                '<div class="feature-card">'
                '<span style="display:inline-block;background:#c9a84c;color:#0a0e1a;width:28px;height:28px;'
                'border-radius:50%;text-align:center;line-height:28px;font-weight:700;font-size:14px;margin-bottom:10px;">{}</span>'
                '<div class="fc-title">{}</div>'
                '<div class="fc-desc">{}</div>'
                '</div>'.format(num, title, desc),
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align:center;color:#8899aa;font-size:13px;padding:8px 0;">
        Built with Python &middot; PDAI Assignment 3 &middot; ESADE Business School &middot; {} &middot; Not financial advice
    </div>
    """.format(date.today().year), unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TAB 1: YOUR BRIEF
# ══════════════════════════════════════════════════════════════════════════
with tab_brief:
    st.markdown('<div class="section-header">Tell Us About Your Situation</div><div class="section-sub">Describe your circumstances or fill in the form — HomeIQ will personalise everything to you.</div>', unsafe_allow_html=True)

    col_ai, col_form = st.columns([1, 1])

    with col_ai:
        st.markdown("##### AI Brief Parser")
        st.caption("Describe your situation in plain English and our AI will extract your profile.")
        brief_text = st.text_area(
            "Your situation",
            placeholder="e.g. I earn £55k as a software engineer working hybrid in London. My partner earns £30k. We have £40k saved and want somewhere with good schools and green space, budget around £350k...",
            height=150,
            key="brief_input",
        )
        if st.button("Parse with AI", key="parse_brief"):
            if brief_text and OPENAI_KEY:
                with st.spinner("Parsing your brief..."):
                    parsed = parse_life_brief(brief_text, OPENAI_KEY)
                    st.session_state.salary = parsed.get("salary", 50000)
                    st.session_state.partner_salary = parsed.get("partner_salary", 0)
                    st.session_state.budget = parsed.get("budget")
                    st.session_state.deposit_pct = parsed.get("deposit_pct", 15)
                    st.session_state.job_type = parsed.get("job_type", "hybrid")
                    st.session_state.priorities = parsed.get("priorities", [])
                    st.session_state.current_savings = parsed.get("current_savings", 0)
                    save_profile(st.session_state.user_id, {
                        "name": "AI Parsed",
                        "salary": parsed.get("salary", 50000),
                        "partner_salary": parsed.get("partner_salary", 0),
                        "budget": parsed.get("budget"),
                        "deposit_pct": parsed.get("deposit_pct", 15),
                        "job_type": parsed.get("job_type", "hybrid"),
                        "priorities": parsed.get("priorities", []),
                        "current_savings": parsed.get("current_savings", 0),
                    })
                    st.success("Profile parsed and saved to database!")
                    st.json(parsed)
                    st.rerun()
            elif not OPENAI_KEY:
                st.error("Set OPENAI_API_KEY in environment or .streamlit/secrets.toml")

    with col_form:
        st.markdown("##### Manual Profile")
        salary = st.number_input("Annual Salary (£)", value=int(profile.get("salary", 50000)), step=5000, key="form_salary")
        partner_salary = st.number_input("Partner Salary (£)", value=int(profile.get("partner_salary", 0)), step=5000, key="form_partner")
        budget = st.number_input("Property Budget (£)", value=int(profile.get("budget") or 0), step=25000, key="form_budget")
        job_type = st.selectbox("Work Style", ["hybrid", "remote", "office"], index=["hybrid", "remote", "office"].index(profile.get("job_type", "hybrid")), key="form_job")
        industry_options = [""] + list(INDUSTRIES.keys())
        industry_labels = ["None (skip career scoring)"] + [INDUSTRIES[k]["label"] for k in INDUSTRIES]
        current_industry = profile.get("industry", "")
        ind_idx = industry_options.index(current_industry) if current_industry in industry_options else 0
        industry = st.selectbox("Your Industry", industry_options, index=ind_idx, format_func=lambda x: industry_labels[industry_options.index(x)], key="form_industry")
        priorities = st.multiselect("Priorities", ["green_space", "schools", "safety", "culture", "healthcare", "commute", "family_friendly", "affordability"], default=profile.get("priorities", []), key="form_priorities")
        current_savings = st.number_input("Current Savings (£)", value=int(profile.get("current_savings", 0)), step=5000, key="form_savings")

        if st.button("Save Profile", key="save_manual"):
            p = {
                "name": "Manual",
                "salary": salary, "partner_salary": partner_salary,
                "budget": budget if budget > 0 else None,
                "deposit_pct": deposit_pct, "job_type": job_type,
                "industry": industry if industry else None,
                "priorities": priorities, "current_savings": current_savings,
            }
            st.session_state.update(p)
            save_profile(st.session_state.user_id, p)
            st.success("Profile saved to database!")
            st.rerun()

    st.markdown("---")

    st.markdown("##### Analysis Settings")
    c1, c2, c3 = st.columns(3)
    with c1:
        fw = st.slider("Financial vs QoL Weight", 0, 100, financial_weight, key="fw_slider")
        st.session_state.financial_weight = fw
    with c2:
        dp = st.slider("Deposit %", 5, 50, deposit_pct, key="dp_slider")
        st.session_state.deposit_pct = dp
    with c3:
        hz = st.slider("Investment Horizon (years)", 3, 25, horizon, key="hz_slider")
        st.session_state.horizon = hz

    st.markdown("---")
    st.markdown("##### Live Market Data")
    hpi_prices, hpi_month = get_live_prices()
    sources = live.get("_sources", {})
    lc1, lc2, lc3, lc4, lc5 = st.columns(5)
    lc1.metric("Base Rate", "{}%".format(live["base_rate_current"]))
    lc2.metric("2yr Fixed", "{}%".format(live["rate_2yr_current"]))
    lc3.metric("5yr Fixed", "{}%".format(live["rate_5yr_current"]))
    lc4.metric("Earnings Growth", "{}%".format(live["earnings_growth_current"]))
    if hpi_prices:
        lc5.metric("HPI Data", hpi_month)

    live_count = sum(1 for v in sources.values() if v == "live")
    total_count = len(sources)
    if hpi_prices:
        live_count += 1
        total_count += 1

    if live_count == total_count and total_count > 0:
        st.success("All market data is LIVE ({}/{}) - BoE IADB, ONS, HM Land Registry HPI".format(live_count, total_count))
    elif live_count > 0:
        fallback_items = [k for k, v in sources.items() if v == "fallback"]
        st.warning("{}/{} data sources live. Fallback: {}".format(live_count, total_count, ", ".join(fallback_items)))

# ══════════════════════════════════════════════════════════════════════════
# TAB 2: REGIONAL RANKINGS
# ══════════════════════════════════════════════════════════════════════════
with tab_ranking:
    st.markdown('<div class="section-header">Regional Rankings</div><div class="section-sub">All 12 UK regions scored and ranked based on your financial profile and priorities.</div>', unsafe_allow_html=True)

    df_rank = pd.DataFrame(rankings)
    display_cols = ["region", "composite", "financial_score", "qol_score", "career_score", "affordability_ratio", "monthly_mortgage", "monthly_rent", "disposable_monthly", "price"]
    df_display = df_rank[display_cols].copy()
    df_display["monthly_mortgage"] = df_display["monthly_mortgage"].apply(lambda x: "£{:,}".format(x))
    df_display["monthly_rent"] = df_display["monthly_rent"].apply(lambda x: "£{:,}".format(x))
    df_display["disposable_monthly"] = df_display["disposable_monthly"].apply(lambda x: "£{:,}".format(x))
    df_display["price"] = df_display["price"].apply(lambda x: "£{:,}".format(x))
    df_display.columns = ["Region", "Score", "Financial", "QoL", "Career", "Afford. Ratio", "Mortgage/mo", "Rent/mo", "Disposable/mo", "Avg Price"]
    df_display.index = range(1, len(df_display) + 1)
    st.dataframe(df_display, use_container_width=True)

    if st.button("Save this comparison", key="save_ranking_comp"):
        save_comparison(
            st.session_state.user_id,
            None,
            list(REGIONS.keys()),
            rankings,
            f"Full ranking | FW={financial_weight}% | Dep={deposit_pct}%",
        )
        st.success("Comparison saved to history!")

    st.markdown("---")

    compare_regions = st.multiselect("Select regions to compare", list(REGIONS.keys()), default=[rankings[0]["region"], rankings[1]["region"]], key="compare_select")

    if len(compare_regions) >= 2:
        cols = st.columns(len(compare_regions))
        for i, rname in enumerate(compare_regions):
            r = REGIONS[rname]
            score = next((s for s in rankings if s["region"] == rname), None)
            with cols[i]:
                st.markdown(f"**{rname}**")
                st.metric("Score", score["composite"])
                st.metric("Avg Price", f"£{r['avg_price']:,}")
                st.metric("Mortgage/mo", f"£{score['monthly_mortgage']:,}")
                st.metric("Disposable/mo", f"£{score['disposable_monthly']:,}")

        fig_radar = go.Figure()
        for rname in compare_regions:
            r = REGIONS[rname]
            vals = [r[d] for d in QOL_DIMS] + [r[QOL_DIMS[0]]]
            labels = QOL_LABELS + [QOL_LABELS[0]]
            fig_radar.add_trace(go.Scatterpolar(
                r=vals, theta=labels, fill="toself", name=rname,
                line=dict(color=REGION_COLORS.get(rname, C["gold"])),
                fillcolor=hex_to_rgba(REGION_COLORS.get(rname, C["gold"]), 0.15),
            ))
        fig_radar.update_layout(**PLOT_THEME, polar=dict(
            bgcolor="#1a2235",
            radialaxis=dict(gridcolor="#243048", linecolor="#243048", range=[0, 100]),
            angularaxis=dict(gridcolor="#243048", linecolor="#243048"),
        ), showlegend=True, height=450, title="Quality of Life Comparison")
        st.plotly_chart(fig_radar, use_container_width=True)

    st.markdown("---")
    st.markdown("##### Score Breakdown")
    fig_bar = go.Figure()
    regions_sorted = [r["region"] for r in rankings]
    fig_bar.add_trace(go.Bar(
        x=regions_sorted, y=[r["financial_score"] for r in rankings],
        name="Financial", marker_color=C["gold"],
    ))
    fig_bar.add_trace(go.Bar(
        x=regions_sorted, y=[r["qol_score"] for r in rankings],
        name="Quality of Life", marker_color=C["blue"],
    ))
    fig_bar.update_layout(**PLOT_THEME, barmode="group", height=400, title="Financial vs QoL Scores")
    st.plotly_chart(fig_bar, use_container_width=True)

    pdf_bytes = generate_pdf(profile, rankings, live)
    st.download_button("Download PDF Report", pdf_bytes, "homeiq_report.pdf", "application/pdf")

# ══════════════════════════════════════════════════════════════════════════
# TAB 3: CAREER & JOBS
# ══════════════════════════════════════════════════════════════════════════
with tab_career:
    st.markdown('<div class="section-header">Career & Job Market</div><div class="section-sub">Industry-specific job availability, salary projections, and live market data from Adzuna.</div>', unsafe_allow_html=True)

    career_c1, career_c2 = st.columns(2)
    with career_c1:
        career_industry_opts = list(INDUSTRIES.keys())
        career_industry_labels = [INDUSTRIES[k]["label"] for k in career_industry_opts]
        default_ind = profile.get("industry", "technology") or "technology"
        if default_ind not in career_industry_opts:
            default_ind = "technology"
        career_industry = st.selectbox(
            "Select your industry",
            career_industry_opts,
            index=career_industry_opts.index(default_ind),
            format_func=lambda x: INDUSTRIES[x]["label"],
            key="career_industry",
        )
    with career_c2:
        career_job_type = st.selectbox(
            "Work style",
            ["hybrid", "remote", "office"],
            index=["hybrid", "remote", "office"].index(profile.get("job_type", "hybrid")),
            key="career_job_type",
        )

    ind_info = INDUSTRIES[career_industry]

    with st.spinner("Fetching live job market data from Adzuna..."):
        adzuna_stats = fetch_all_job_stats(career_industry)
    has_live = bool(adzuna_stats)

    total_live_jobs = sum(s["count"] for s in adzuna_stats.values()) if has_live else 0
    avg_live_salary = round(sum(s["mean_salary"] for s in adzuna_stats.values() if s["mean_salary"] > 0) / max(1, len([s for s in adzuna_stats.values() if s["mean_salary"] > 0]))) if has_live else 0

    ci1, ci2, ci3, ci4, ci5 = st.columns(5)
    ci1.metric("UK Avg Salary", "GBP {:,}".format(ind_info["avg_uk_salary"]))
    ci2.metric("Sector Growth", "{}%/yr".format(ind_info["growth_rate"]))
    ci3.metric("Remote Friendly", "{}%".format(int(ind_info["remote_friendly"] * 100)))
    if has_live:
        ci4.metric("Live Job Listings", "{:,}".format(total_live_jobs))
        ci5.metric("Live Avg Salary", "GBP {:,}".format(avg_live_salary))
    else:
        ci4.metric("Your Salary", "GBP {:,}".format(int(profile.get("salary", 50000))))

    if has_live:
        st.success("Live data powered by Adzuna Jobs API - {:,} jobs found across {} regions".format(total_live_jobs, len(adzuna_stats)))

    st.markdown("---")
    st.markdown("##### Career-Adjusted Region Scores")
    if has_live:
        st.caption("Regions re-ranked using LIVE job market data from Adzuna, blended with baseline scores.")
    else:
        st.caption("Regions re-ranked by job availability in your industry, weighted by work style.")

    career_scores = []
    for rname in REGIONS:
        cs = compute_career_adjusted_score(rname, career_industry, career_job_type)
        region_data = REGION_INDUSTRY_SCORES.get(rname, {})
        score_data = next((r for r in rankings if r["region"] == rname), {})
        row = {
            "Region": rname,
            "Career Score": cs,
            "Job Density": region_data.get(career_industry, 0),
            "5yr Job Growth": "{}%".format(region_data.get("job_growth_5yr", 0)),
            "Salary Premium": "x{}".format(region_data.get("salary_premium", 1.0)),
            "Overall Score": score_data.get("composite", 0),
        }
        if has_live and rname in adzuna_stats:
            row["Live Jobs"] = "{:,}".format(adzuna_stats[rname]["count"])
            row["Live Avg Salary"] = "GBP {:,}".format(adzuna_stats[rname]["mean_salary"])
        career_scores.append(row)
    career_scores.sort(key=lambda x: x["Career Score"], reverse=True)
    career_df = pd.DataFrame(career_scores)
    career_df.index = range(1, len(career_df) + 1)
    st.dataframe(career_df, use_container_width=True)

    # Career score bar chart
    fig_career = go.Figure()
    sorted_regions = [c["Region"] for c in career_scores]
    sorted_career = [c["Career Score"] for c in career_scores]
    sorted_density = [c["Job Density"] for c in career_scores]
    fig_career.add_trace(go.Bar(
        x=sorted_regions, y=sorted_career,
        name="Career Score", marker_color=C["gold"],
    ))
    fig_career.add_trace(go.Bar(
        x=sorted_regions, y=sorted_density,
        name="Job Density", marker_color=C["blue"],
    ))
    fig_career.update_layout(**PLOT_THEME, barmode="group", height=400,
                              title="{} - Career Scores by Region".format(ind_info["label"]))
    st.plotly_chart(fig_career, use_container_width=True)

    st.markdown("---")
    st.markdown("##### 10-Year Salary Projection")
    st.caption("Projected salary growth based on regional premium and industry trends.")

    proj_regions = st.multiselect(
        "Compare salary growth across regions",
        list(REGIONS.keys()),
        default=[career_scores[0]["Region"], career_scores[1]["Region"], "London"] if career_scores[0]["Region"] != "London" else [career_scores[0]["Region"], career_scores[1]["Region"], career_scores[2]["Region"]],
        key="proj_regions",
    )

    if proj_regions:
        fig_sal = go.Figure()
        sal_base = profile.get("salary", 50000)
        projection_table = []
        for rname in proj_regions:
            proj = get_salary_projection(sal_base, rname, career_industry, years=10)
            years = [p["year"] for p in proj["projections"]]
            salaries = [p["salary"] for p in proj["projections"]]
            fig_sal.add_trace(go.Scatter(
                x=years, y=salaries, name=rname, mode="lines+markers",
                line=dict(color=REGION_COLORS.get(rname, C["gold"]), width=2),
            ))
            projection_table.append({
                "Region": rname,
                "Starting": "GBP {:,}".format(proj["starting_salary"]),
                "Year 5": "GBP {:,}".format(proj["year_5_salary"]),
                "Year 10": "GBP {:,}".format(proj["year_10_salary"]),
                "10yr Total": "GBP {:,}".format(proj["total_earnings_10yr"]),
            })

        fig_sal.update_layout(**PLOT_THEME, height=400, title="Salary Projection (10yr)",
                               xaxis_title="Year", yaxis_title="Annual Salary (GBP)")
        st.plotly_chart(fig_sal, use_container_width=True)
        st.dataframe(pd.DataFrame(projection_table), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### Regional Job Market Details")

    detail_region = st.selectbox("Select region for details", list(REGIONS.keys()),
                                  index=0, key="career_detail_region")
    summary = get_region_career_summary(detail_region)

    if summary:
        dc1, dc2 = st.columns(2)
        with dc1:
            st.markdown("**Top Industries**")
            for ti in summary["top_industries"]:
                bar_pct = ti["score"]
                color = C["gold"] if bar_pct >= 70 else C["blue"] if bar_pct >= 50 else C["muted"]
                live_label = ""
                if ti.get("live_jobs") is not None:
                    live_label = " - {:,} live jobs".format(ti["live_jobs"])
                if ti.get("live_salary") and ti["live_salary"] > 0:
                    live_label += ", avg GBP {:,}".format(ti["live_salary"])
                st.markdown(
                    '<div style="margin-bottom:6px;">'
                    '<span style="color:#f5f0e8;font-size:13px;">{}{}</span>'
                    '<div style="background:#1a2235;border-radius:4px;height:18px;margin-top:2px;">'
                    '<div style="background:{};width:{}%;height:100%;border-radius:4px;'
                    'display:flex;align-items:center;padding-left:8px;">'
                    '<span style="color:#0a0e1a;font-size:11px;font-weight:600;">{}</span>'
                    '</div></div></div>'.format(ti["label"], live_label, color, bar_pct, bar_pct),
                    unsafe_allow_html=True,
                )

        with dc2:
            st.markdown("**Key Facts**")
            st.write("Salary Premium: x{}".format(summary["salary_premium"]))
            st.write("5yr Job Growth: {}%".format(summary["job_growth_5yr"]))
            if has_live and detail_region in adzuna_stats:
                st.write("Live Job Listings: {:,}".format(adzuna_stats[detail_region]["count"]))
                if adzuna_stats[detail_region]["mean_salary"] > 0:
                    st.write("Live Avg Salary: GBP {:,}".format(adzuna_stats[detail_region]["mean_salary"]))
            st.markdown("**Major Employers**")
            for emp in summary["major_employers"]:
                st.write("- {}".format(emp))
            st.markdown("**Emerging Sectors**")
            for sec in summary["emerging_sectors"]:
                st.write("- {}".format(sec))

# ══════════════════════════════════════════════════════════════════════════
# TAB 4: MONTE CARLO
# ══════════════════════════════════════════════════════════════════════════
with tab_mc:
    st.markdown('<div class="section-header">Monte Carlo Simulation</div><div class="section-sub">Probabilistic comparison of buy-vs-rent outcomes across regions over your investment horizon.</div>', unsafe_allow_html=True)

    mc_regions = st.multiselect("Regions to simulate", list(REGIONS.keys()), default=[rankings[0]["region"], rankings[1]["region"], rankings[2]["region"]], key="mc_regions")
    mc_c1, mc_c2 = st.columns(2)
    n_sims = mc_c1.slider("Simulations", 200, 3000, 1000, 100, key="mc_sims")
    mc_horizon = mc_c2.slider("Horizon (years)", 3, 25, horizon, key="mc_horizon")

    if len(mc_regions) < 2:
        st.warning("Select at least 2 regions to run the simulation.")
    if len(mc_regions) >= 2 and st.button("Run Simulation", key="run_mc"):
        with st.spinner(f"Running {n_sims:,} simulations across {len(mc_regions)} regions..."):
            # Direct call — MC needs full histogram arrays for box plots (API strips them for bandwidth)
            mc_results = run_regional_monte_carlo(mc_regions, profile, live, n_sims, mc_horizon, deposit_pct=deposit_pct)

        mc_df = pd.DataFrame([
            {
                "Region": rname,
                "P(Best)": f"{mc_results[rname]['prob_best']*100:.0f}%",
                "Median": f"£{mc_results[rname]['p50']:,}",
                "P10 (Bear)": f"£{mc_results[rname]['p10']:,}",
                "P90 (Bull)": f"£{mc_results[rname]['p90']:,}",
                "P(Positive)": f"{mc_results[rname]['prob_positive']:.0f}%",
            }
            for rname in mc_regions
        ])
        st.dataframe(mc_df, use_container_width=True)

        fig_box = go.Figure()
        for rname in mc_regions:
            hist = mc_results[rname]["histogram"]
            fig_box.add_trace(go.Box(
                y=hist, name=rname,
                marker_color=REGION_COLORS.get(rname, C["gold"]),
                boxmean=True,
            ))
        fig_box.update_layout(**PLOT_THEME, height=450, title=f"Net Position Distribution ({mc_horizon}yr)")
        st.plotly_chart(fig_box, use_container_width=True)

        if OPENAI_KEY:
            with st.spinner("AI interpreting results..."):
                client = openai.OpenAI(api_key=OPENAI_KEY)
                mc_summary = "\n".join([
                    f"{r}: P(Best)={mc_results[r]['prob_best']*100:.0f}%, Median=£{mc_results[r]['p50']:,}, P10=£{mc_results[r]['p10']:,}, P90=£{mc_results[r]['p90']:,}"
                    for r in mc_regions
                ])
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a financial analyst. Interpret Monte Carlo simulation results for a UK property buyer. Be concise (3-4 sentences)."},
                        {"role": "user", "content": f"Profile: salary £{profile.get('salary',50000):,}, horizon {mc_horizon}yr.\n\nResults:\n{mc_summary}"},
                    ],
                    max_tokens=250,
                )
                st.info(resp.choices[0].message.content)

        save_search(st.session_state.user_id, None, "monte_carlo", {"regions": mc_regions, "n_sims": n_sims, "horizon": mc_horizon}, {r: {k: v for k, v in mc_results[r].items() if k != "histogram"} for r in mc_regions})

# ══════════════════════════════════════════════════════════════════════════
# TAB 4: AFFORDABILITY
# ══════════════════════════════════════════════════════════════════════════
with tab_afford:
    st.markdown('<div class="section-header">Affordability & Stress Test</div><div class="section-sub">Full mortgage breakdown with stamp duty, fees, and rate sensitivity analysis.</div>', unsafe_allow_html=True)

    af_region = st.selectbox("Region", list(REGIONS.keys()), index=list(REGIONS.keys()).index(top_region), key="af_region")
    af_savings = st.number_input("Current Savings (£)", value=int(profile.get("current_savings", 0)), step=5000, key="af_savings")

    if USE_API:
        af = api_affordability(profile.get("salary", 50000), profile.get("partner_salary", 0), af_region, deposit_pct, af_savings)
    else:
        af = compute_affordability(profile.get("salary", 50000), profile.get("partner_salary", 0), af_region, deposit_pct, af_savings)

    ac1, ac2, ac3, ac4 = st.columns(4)
    ac1.metric("Max Borrowing (4.5x)", f"£{af['max_borrowing']:,}")
    ac2.metric("Loan Needed", f"£{af['loan_needed']:,}", "Approved" if af["can_borrow"] else "EXCEEDS LIMIT")
    ac3.metric("Total Upfront", f"£{af['total_upfront']:,}")
    ac4.metric("Savings Shortfall", f"£{af['shortfall']:,}", f"{af['months_to_save']} months to save" if af["shortfall"] > 0 else "Ready!")

    st.markdown("---")

    st.markdown("##### Cost Breakdown")
    cost_df = pd.DataFrame([
        {"Item": "Deposit", "Amount": f"£{af['deposit']:,}"},
        {"Item": "Stamp Duty", "Amount": f"£{af['stamp']:,}"},
        {"Item": "Solicitor", "Amount": f"£{af['solicitor']:,}"},
        {"Item": "Survey", "Amount": f"£{af['survey']:,}"},
        {"Item": "TOTAL", "Amount": f"£{af['total_upfront']:,}"},
    ])
    st.dataframe(cost_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### Mortgage Stress Test")
    st.caption(f"Danger line (35% of net income): £{af['danger_line']:,}/mo")

    fig_stress = go.Figure()
    colors = [C["green"] if p <= af["danger_line"] else C["red"] for p in af["stress_payments"]]
    fig_stress.add_trace(go.Bar(
        x=[f"{r:.1f}%" for r in af["stress_rates"]],
        y=af["stress_payments"],
        marker_color=colors,
    ))
    fig_stress.add_hline(y=af["danger_line"], line_dash="dash", line_color=C["gold"], annotation_text="35% income limit")
    fig_stress.update_layout(**PLOT_THEME, height=400, title="Monthly Payment at Different Rates",
                             xaxis_title="Interest Rate", yaxis_title="Monthly Payment (£)")
    st.plotly_chart(fig_stress, use_container_width=True)

    if st.button("Save this affordability check", key="save_afford"):
        save_search(st.session_state.user_id, None, "affordability", {"region": af_region, "savings": af_savings}, af)
        st.success("Affordability check saved to history!")

# ══════════════════════════════════════════════════════════════════════════
# TAB 5: NEIGHBOURHOOD FINDER
# ══════════════════════════════════════════════════════════════════════════
with tab_areas:
    st.markdown('<div class="section-header">Neighbourhood Finder</div><div class="section-sub">AI-powered search for specific towns and areas within your chosen region.</div>', unsafe_allow_html=True)

    nf_region = st.selectbox("Region to explore", list(REGIONS.keys()), index=list(REGIONS.keys()).index(top_region), key="nf_region")
    nf_budget = st.number_input("Budget (£)", value=int(profile.get("budget") or REGIONS[nf_region]["avg_price"]), step=25000, key="nf_budget")

    if st.button("Find Neighbourhoods", key="find_areas") and OPENAI_KEY:
        with st.spinner("Searching for the best neighbourhoods..."):
            result = find_neighbourhoods(nf_region, profile, nf_budget, live, OPENAI_KEY)
            areas = result.get("neighbourhoods", [])

            if areas:
                for area in areas:
                    match_color = "#2dd4a0" if area.get("match_score", 0) >= 70 else "#c9a84c" if area.get("match_score", 0) >= 50 else "#8899aa"
                    st.markdown(
                        '<div style="background:#1a2235;border:1px solid #243048;border-radius:10px;padding:16px;margin-bottom:10px;">'
                        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                        '<span style="color:#fff;font-size:16px;font-weight:600;">{} <span style="color:#8899aa;font-size:13px;">({})</span></span>'
                        '<span style="background:{};color:#0a0e1a;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;">{}% match</span>'
                        '</div>'
                        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px;">'
                        '<span style="color:#c9a84c;font-size:13px;">Avg Price: GBP {:,}</span>'
                        '<span style="color:#c9a84c;font-size:13px;">Range: {}</span>'
                        '<span style="color:#f5f0e8;font-size:13px;">Schools: {}</span>'
                        '<span style="color:#f5f0e8;font-size:13px;">Transport: {}</span>'
                        '</div>'
                        '<div style="color:#8899aa;font-size:13px;line-height:1.5;">{}</div>'
                        '</div>'.format(
                            area["name"], area.get("postcode_area", ""),
                            match_color, area.get("match_score", 0),
                            area.get("avg_property_price", 0), area.get("price_range", "N/A"),
                            area.get("school_rating", "N/A"), area.get("transport", "N/A"),
                            area.get("description", ""),
                        ),
                        unsafe_allow_html=True,
                    )

                save_search(st.session_state.user_id, None, "neighbourhood", {"region": nf_region, "budget": nf_budget}, result)
            else:
                st.warning("No neighbourhoods found. Try adjusting the budget.")

# ══════════════════════════════════════════════════════════════════════════
# TAB 6: AI ADVISOR (RAG-POWERED)
# ══════════════════════════════════════════════════════════════════════════
with tab_advisor:
    st.markdown('<div class="section-header">AI Relocation Advisor</div><div class="section-sub">RAG-powered chat backed by a UK housing knowledge base — ask anything about regions, mortgages, or schemes.</div>', unsafe_allow_html=True)

    if rag_engine:
        stats = rag_engine.stats
        st.caption(f"Knowledge base: {stats['total_chunks']} chunks from {stats['total_documents']} documents indexed")
    else:
        st.caption("RAG knowledge base unavailable (no API key)")

    st.markdown("""<div style='color:#8899aa;font-size:14px;margin-bottom:16px;'>Try:
        <em style='color:#c9a84c;'>"What government schemes can help me buy?"</em> &middot;
        <em style='color:#c9a84c;'>"Compare Yorkshire vs North West"</em> &middot;
        <em style='color:#c9a84c;'>"Can I afford London on £80k?"</em> &middot;
        <em style='color:#c9a84c;'>"What's shared ownership?"</em> &middot;
        <em style='color:#c9a84c;'>"Run Monte Carlo for Scotland vs Wales"</em>
    </div>""", unsafe_allow_html=True)

    ADVISOR_TOOLS = [
        {"type": "function", "function": {
            "name": "compare_regions",
            "description": "Compare two UK regions with detailed financial and QoL breakdown.",
            "parameters": {"type": "object", "properties": {
                "region1": {"type": "string"}, "region2": {"type": "string"},
            }, "required": ["region1", "region2"]}
        }},
        {"type": "function", "function": {
            "name": "run_scenario",
            "description": "Run financial analysis for a specific region with custom salary/budget.",
            "parameters": {"type": "object", "properties": {
                "region": {"type": "string"},
                "salary": {"type": "number"}, "partner_salary": {"type": "number"},
            }, "required": ["region"]}
        }},
        {"type": "function", "function": {
            "name": "find_best_region",
            "description": "Find the best region for a specific priority.",
            "parameters": {"type": "object", "properties": {
                "priority": {"type": "string"},
            }, "required": ["priority"]}
        }},
        {"type": "function", "function": {
            "name": "run_monte_carlo_tool",
            "description": "Run Monte Carlo simulation for specific regions.",
            "parameters": {"type": "object", "properties": {
                "regions": {"type": "string"}, "n_simulations": {"type": "integer"},
            }, "required": ["regions"]}
        }},
        {"type": "function", "function": {
            "name": "check_affordability",
            "description": "Check mortgage affordability for a region.",
            "parameters": {"type": "object", "properties": {
                "region": {"type": "string"}, "current_savings": {"type": "integer"},
            }, "required": ["region"]}
        }},
        {"type": "function", "function": {
            "name": "estimate_moving_costs",
            "description": "Estimate total relocation costs for a region.",
            "parameters": {"type": "object", "properties": {
                "region": {"type": "string"},
            }, "required": ["region"]}
        }},
        {"type": "function", "function": {
            "name": "find_neighbourhoods_tool",
            "description": "Find neighbourhoods within a region matching user priorities.",
            "parameters": {"type": "object", "properties": {
                "region": {"type": "string"},
                "requirements": {"type": "string"},
            }, "required": ["region"]}
        }},
        {"type": "function", "function": {
            "name": "search_knowledge_base",
            "description": "Search the HomeIQ knowledge base for UK housing info, mortgages, government schemes, regional details, relocation advice.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
            }, "required": ["query"]}
        }},
    ]

    def execute_advisor_tool(name, arguments_json):
        args = json.loads(arguments_json) if arguments_json else {}
        if name == "compare_regions":
            r1, r2 = args.get("region1", "London"), args.get("region2", "Yorkshire")
            results = []
            for rname in [r1, r2]:
                if rname not in REGIONS:
                    return f"Region '{rname}' not found. Available: {', '.join(REGIONS.keys())}"
                s = compute_regional_score(rname, profile, live, financial_weight, deposit_pct)
                b = compute_monthly_budget(profile.get("salary", 50000), profile.get("partner_salary", 0), rname, deposit_pct, live["rate_5yr_current"])
                r = REGIONS[rname]
                results.append(f"{rname}: Score={s['composite']}, Financial={s['financial_score']}, QoL={s['qol_score']}, Price=£{r['avg_price']:,}, Mortgage=£{b['monthly_mortgage']:,}/mo, Disposable=£{b['disposable_buy']:,}/mo")
            return "Region comparison:\n" + "\n".join(results)
        elif name == "run_scenario":
            rname = args.get("region", "London")
            if rname not in REGIONS:
                return f"Region '{rname}' not found."
            sal = args.get("salary", profile.get("salary", 50000))
            psal = args.get("partner_salary", profile.get("partner_salary", 0))
            cp = {**profile, "salary": sal, "partner_salary": psal}
            s = compute_regional_score(rname, cp, live, financial_weight, deposit_pct)
            b = compute_monthly_budget(sal, psal, rname, deposit_pct, live["rate_5yr_current"])
            return f"{rname}: Score={s['composite']}, Mortgage=£{b['monthly_mortgage']:,}/mo, Disposable(buy)=£{b['disposable_buy']:,}/mo, Disposable(rent)=£{b['disposable_rent']:,}/mo"
        elif name == "find_best_region":
            priority = args.get("priority", "overall")
            if priority == "overall":
                return f"Best overall: {rankings[0]['region']} (score {rankings[0]['composite']})"
            elif priority == "affordability":
                best = min(rankings, key=lambda x: x["affordability_ratio"])
                return f"Most affordable: {best['region']} ({best['affordability_ratio']}x income)"
            elif priority == "disposable_income":
                best = max(rankings, key=lambda x: x["disposable_monthly"])
                return f"Best disposable: {best['region']} (£{best['disposable_monthly']:,}/mo)"
            elif priority in QOL_DIMS:
                best_r = max(REGIONS.items(), key=lambda x: x[1].get(priority, 0))
                return f"Best for {priority}: {best_r[0]} (score: {best_r[1][priority]})"
            return f"Unknown priority: {priority}"
        elif name == "run_monte_carlo_tool":
            regs = [r.strip() for r in args.get("regions", "London,Yorkshire").split(",")]
            regs = [r for r in regs if r in REGIONS]
            if len(regs) < 2:
                return "Need at least 2 valid regions."
            n = min(2000, max(100, args.get("n_simulations", 500)))
            mc = run_regional_monte_carlo(regs, profile, live, n, horizon, deposit_pct=deposit_pct)
            lines = [f"Monte Carlo ({n} sims, {horizon}yr):"]
            for rname in sorted(regs, key=lambda r: mc[r]["prob_best"], reverse=True):
                m = mc[rname]
                lines.append(f"- {rname}: P(Wins)={m['prob_best']*100:.0f}%, Median=£{m['p50']:,.0f}, P10=£{m['p10']:,.0f}, P90=£{m['p90']:,.0f}")
            return "\n".join(lines)
        elif name == "check_affordability":
            rname = args.get("region", top_region)
            if rname not in REGIONS:
                return f"Region '{rname}' not found."
            sav = args.get("current_savings", profile.get("current_savings", 20000))
            af = compute_affordability(profile.get("salary", 50000), profile.get("partner_salary", 0), rname, deposit_pct, sav)
            return f"Affordability for {rname}: Max borrow=£{af['max_borrowing']:,}, Loan=£{af['loan_needed']:,} ({'OK' if af['can_borrow'] else 'EXCEEDS'}), Upfront=£{af['total_upfront']:,}, Shortfall=£{af['shortfall']:,}"
        elif name == "estimate_moving_costs":
            rname = args.get("region", top_region)
            if rname not in REGIONS:
                return f"Region '{rname}' not found."
            p = REGIONS[rname]["avg_price"]
            dep = p * deposit_pct / 100
            stamp = compute_stamp_duty(p, True)
            total = dep + stamp + 1500 + 500 + 999 + 1200 + 2000 + 300 + 1200
            return f"Moving costs for {rname} (£{p:,}): Deposit=£{dep:,.0f}, Stamp=£{stamp:,}, Fees=~£4,500, Removal=~£1,200, Total=~£{total:,.0f}"
        elif name == "find_neighbourhoods_tool":
            rname = args.get("region", top_region)
            if rname not in REGIONS:
                return f"Region '{rname}' not found."
            if not OPENAI_KEY:
                return "API key not configured."
            budget_val = int(profile.get("budget") or REGIONS[rname]["avg_price"])
            result = find_neighbourhoods(rname, profile, budget_val, live, OPENAI_KEY)
            areas = result.get("neighbourhoods", [])
            lines = [f"Top neighbourhoods in {rname}:"]
            for a in areas:
                lines.append(f"\n**{a['name']}** ({a.get('postcode_area','')}) - Match: {a.get('match_score',0)}%")
                lines.append(f"  Price: £{a.get('avg_property_price',0):,}, Schools: {a.get('school_rating','N/A')}")
                lines.append(f"  {a.get('description','')}")
            return "\n".join(lines)
        elif name == "search_knowledge_base":
            if not rag_engine:
                return "Knowledge base not available."
            query = args.get("query", "")
            results = rag_engine.query(query, n_results=4)
            if not results:
                return "No relevant information found."
            parts = []
            for r in results:
                parts.append(f"[{r['source']} - {r['section']}] (relevance: {r['similarity']:.2f})\n{r['text']}")
            return "\n\n---\n\n".join(parts)
        return f"Unknown tool: {name}"

    for i, message in enumerate(st.session_state.chat_history):
        if message["role"] in ("user", "assistant"):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message["role"] == "assistant" and i + 1 < len(st.session_state.chat_history):
                    next_msg = st.session_state.chat_history[i + 1]
                    if next_msg.get("role") == "rag_sources":
                        st.caption("Sources: {}".format(next_msg["content"]))

    if user_input := st.chat_input("Ask your relocation advisor..."):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    if USE_API:
                        # Route through FastAPI backend — tool execution happens server-side
                        api_resp = api_chat(
                            user_input,
                            session_id=st.session_state.chat_session_id,
                            user_id=st.session_state.user_id,
                            profile=profile,
                        )
                        reply = api_resp.get("reply", "Analysis complete.")
                        st.session_state.chat_session_id = api_resp.get("session_id")
                        for tc in api_resp.get("tool_calls", []):
                            st.info("Computing: {}...".format(tc["tool"]))
                        rag_sources = api_resp.get("rag_sources", [])
                        if rag_sources:
                            sources_str = " | ".join(set(rag_sources))
                            st.caption("Sources: {}".format(sources_str))
                            st.session_state.chat_history.append({"role": "rag_sources", "content": sources_str})
                    else:
                        # Direct mode — tool execution happens in-process
                        rag_context = ""
                        rag_sources = []
                        if rag_engine:
                            rag_context = rag_engine.get_context_for_chat(user_input, n_results=3)
                            for chunk in rag_engine.query(user_input, n_results=3):
                                rag_sources.append("{} - {}".format(chunk["source"], chunk["section"]))

                        hpi_ctx = ""
                        hpi_p, hpi_m = get_live_prices()
                        if hpi_p:
                            hpi_ctx = "\n\nLIVE HOUSE PRICES (HM Land Registry, {}):".format(hpi_m)
                            for rn in list(REGIONS.keys())[:6]:
                                if rn in hpi_p:
                                    hpi_ctx += "\n- {}: GBP {:,}".format(rn, hpi_p[rn])
                            hpi_ctx += "\n(All 12 regions have live prices)"

                        system_ctx = f"""You are HomeIQ's Smart Relocation Advisor - an expert on UK regions, property, and personal finance.
You have access to a RAG knowledge base with detailed UK housing guides. Use search_knowledge_base for factual questions.
Use computation tools for numerical questions - do NOT guess numbers.
All property prices are LIVE from HM Land Registry UK House Price Index.
Job market data is LIVE from the Adzuna Jobs API.

USER PROFILE: Salary GBP {profile.get('salary', 50000):,}, Partner GBP {profile.get('partner_salary', 0):,},
{profile.get('job_type', 'hybrid')} worker, Priorities: {', '.join(profile.get('priorities', []))},
Deposit: {deposit_pct}%

TOP RANKED REGIONS:
{chr(10).join(f"- {r['region']}: Score {r['composite']}, Avg Price GBP {r['price']:,}" for r in rankings[:5])}

LIVE MARKET: BoE rate {live['base_rate_current']}%, 5yr fixed {live['rate_5yr_current']}%, CPI {live['cpi_current']}%{hpi_ctx}

RELEVANT KNOWLEDGE BASE CONTEXT:
{rag_context if rag_context else 'Use search_knowledge_base tool for detailed information.'}"""

                        client = openai.OpenAI(api_key=OPENAI_KEY)
                        messages = [{"role": "system", "content": system_ctx}] + [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.chat_history if m["role"] in ("user", "assistant")
                        ]
                        response = client.chat.completions.create(
                            model="gpt-4o", messages=messages, tools=ADVISOR_TOOLS,
                            tool_choice="auto", max_tokens=800,
                        )
                        iterations = 0
                        while response.choices[0].message.tool_calls and iterations < 3:
                            tool_calls = response.choices[0].message.tool_calls
                            messages.append(response.choices[0].message)
                            for tc in tool_calls:
                                st.info("Computing: {}...".format(tc.function.name))
                                result = execute_advisor_tool(tc.function.name, tc.function.arguments)
                                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                            response = client.chat.completions.create(
                                model="gpt-4o", messages=messages, tools=ADVISOR_TOOLS,
                                tool_choice="auto", max_tokens=800,
                            )
                            iterations += 1
                        reply = response.choices[0].message.content or "Analysis complete."

                        if rag_sources:
                            sources_str = " | ".join(set(rag_sources))
                            st.caption("Sources: {}".format(sources_str))
                            st.session_state.chat_history.append({"role": "rag_sources", "content": sources_str})

                except Exception as e:
                    reply = "Error: {}".format(str(e))
            st.markdown(reply)
            st.session_state.chat_history.append({"role": "assistant", "content": reply})

            if not USE_API:
                if st.session_state.chat_session_id:
                    update_chat_session(st.session_state.chat_session_id, [m for m in st.session_state.chat_history if m["role"] in ("user", "assistant")])
                else:
                    title = user_input[:50] + ("..." if len(user_input) > 50 else "")
                    st.session_state.chat_session_id = save_chat_session(st.session_state.user_id, title, [m for m in st.session_state.chat_history if m["role"] in ("user", "assistant")])

    if st.session_state.chat_history:
        if st.button("Clear conversation", key="clear_chat"):
            st.session_state.chat_history = []
            st.session_state.chat_session_id = None
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════
# TAB 7: PROFILES & HISTORY
# ══════════════════════════════════════════════════════════════════════════
with tab_profile:
    st.markdown('<div class="section-header">Profiles & History</div><div class="section-sub">Your saved profiles, search history, comparisons, and chat sessions — all persisted in SQLite.</div>', unsafe_allow_html=True)

    st.markdown("##### Saved Profiles")
    profiles = get_all_profiles(st.session_state.user_id)
    if profiles:
        for p in profiles:
            active_badge = '<span style="background:#c9a84c;color:#0a0e1a;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;margin-left:8px;">ACTIVE</span>' if p.get("is_active") else ""
            budget_str = "GBP {:,}".format(int(p["budget"])) if p.get("budget") else "Not set"
            prios = ", ".join(p.get("priorities", [])) or "None"
            st.markdown(
                '<div style="background:#1a2235;border:1px solid #243048;border-radius:10px;padding:16px;margin-bottom:10px;">'
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                '<span style="color:#fff;font-size:15px;font-weight:600;">{}{}</span>'
                '<span style="color:#8899aa;font-size:12px;">{}</span>'
                '</div>'
                '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px;">'
                '<span style="color:#c9a84c;font-size:13px;">Salary: GBP {:,}</span>'
                '<span style="color:#c9a84c;font-size:13px;">Partner: GBP {:,}</span>'
                '<span style="color:#c9a84c;font-size:13px;">Deposit: {}%</span>'
                '</div>'
                '<div style="color:#8899aa;font-size:12px;">Budget: {} | Work: {} | Priorities: {}</div>'
                '</div>'.format(
                    p["name"], active_badge, p["created_at"],
                    int(p["salary"]), int(p["partner_salary"]), int(p["deposit_pct"]),
                    budget_str, p.get("job_type", "hybrid"), prios
                ),
                unsafe_allow_html=True,
            )
            bc1, bc2, bc3 = st.columns([1, 1, 4])
            if not p.get("is_active"):
                if bc1.button("Activate", key="activate_{}".format(p["id"])):
                    set_active_profile(st.session_state.user_id, p["id"])
                    st.rerun()
            if bc2.button("Delete", key="delete_{}".format(p["id"])):
                delete_profile(st.session_state.user_id, p["id"])
                st.rerun()
    else:
        st.info("No saved profiles yet. Use the Brief tab to create one.")

    st.markdown("---")
    sh_col1, sh_col2 = st.columns([3, 1])
    with sh_col1:
        st.markdown("##### Search History")
    with sh_col2:
        if st.button("Clear All History", key="clear_history"):
            from api.database import get_connection
            conn = get_connection()
            conn.execute("DELETE FROM searches WHERE user_id = ?", (st.session_state.user_id,))
            conn.commit()
            conn.close()
            st.rerun()
    history = get_search_history(st.session_state.user_id, limit=10)
    if history:
        history_rows = []
        for h in history:
            params = h.get("query_params", {})
            detail = ""
            if h["search_type"] == "affordability":
                detail = params.get("region", "")
            elif h["search_type"] == "monte_carlo":
                regs = params.get("regions", [])
                detail = ", ".join(regs[:3])
                if len(regs) > 3:
                    detail += "..."
            elif h["search_type"] == "neighbourhood":
                detail = params.get("region", "")
            history_rows.append({
                "Type": h["search_type"].replace("_", " ").title(),
                "Details": detail,
                "Date": h["created_at"],
            })
        st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No search history yet.")

    st.markdown("---")
    st.markdown("##### Saved Comparisons")
    comparisons = get_saved_comparisons(st.session_state.user_id)
    if comparisons:
        for comp in comparisons:
            regions_str = ", ".join(comp["regions"][:5])
            if len(comp["regions"]) > 5:
                regions_str += "..."
            top3_str = " | ".join(["{}: {}".format(r["region"], r["composite"]) for r in comp["rankings"][:3]])
            st.markdown(
                '<div style="background:#1a2235;border:1px solid #243048;border-radius:10px;padding:14px;margin-bottom:8px;">'
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
                '<span style="color:#fff;font-size:14px;font-weight:600;">Comparison</span>'
                '<span style="color:#8899aa;font-size:12px;">{}</span>'
                '</div>'
                '<div style="color:#c9a84c;font-size:13px;margin-bottom:4px;">Top: {}</div>'
                '<div style="color:#8899aa;font-size:12px;">Regions: {} | {}</div>'
                '</div>'.format(comp["created_at"], top3_str, regions_str, comp.get("notes", "")),
                unsafe_allow_html=True,
            )
            if st.button("Delete", key="del_comp_{}".format(comp["id"])):
                delete_comparison(st.session_state.user_id, comp["id"])
                st.rerun()
    else:
        st.info("No saved comparisons yet.")

    st.markdown("---")
    st.markdown("##### Chat Sessions")
    sessions = get_chat_sessions(st.session_state.user_id)
    if sessions:
        for s in sessions:
            st.markdown(
                '<div style="background:#1a2235;border:1px solid #243048;border-radius:8px;padding:12px;margin-bottom:6px;'
                'display:flex;justify-content:space-between;align-items:center;">'
                '<span style="color:#fff;font-size:14px;">{}</span>'
                '<span style="color:#8899aa;font-size:12px;">{}</span>'
                '</div>'.format(s["title"], s["updated_at"]),
                unsafe_allow_html=True,
            )
    else:
        st.info("No chat sessions saved yet.")

# ── Footer ───────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:40px 0 20px;border-top:1px solid #243048;margin-top:24px;">
    <div style="font-family:'Playfair Display',serif;font-size:18px;color:#fff;margin-bottom:6px;">
        HomeIQ <span style="color:#c9a84c;">v3</span>
    </div>
    <div style="color:#8899aa;font-size:12px;line-height:1.8;">
        Smart Relocation Advisor &middot; RAG-Powered &middot; API-Driven &middot; Persistent Profiles<br>
        Data: Bank of England IADB &middot; ONS Timeseries &middot; HM Land Registry HPI &middot; Adzuna Jobs API<br>
        <span style="color:#243048;">PDAI Assignment 3 &middot; ESADE Business School &middot; Not financial advice</span>
    </div>
</div>
""", unsafe_allow_html=True)

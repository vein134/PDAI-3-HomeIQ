"""
HomeIQ v3 — Smart Relocation Advisor
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

from core.regions import REGIONS, QOL_DIMS, QOL_LABELS, COMMUTE_COSTS, HMRC_MILEAGE_RATE
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
from app.theme import GLOBAL_CSS, PLOT_THEME, C, REGION_COLORS, hex_to_rgba

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="HomeIQ v3 — Smart Relocation Advisor", page_icon="🏠", layout="wide")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Init DB ──────────────────────────────────────────────────────────────
init_db()

# ── API key ──────────────────────────────────────────────────────────────
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "") or st.secrets.get("OPENAI_API_KEY", "")

# ── Session defaults ─────────────────────────────────────────────────────
if "user_id" not in st.session_state:
    st.session_state.user_id = get_or_create_user("default")
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = None

# ── Live data ────────────────────────────────────────────────────────────
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
Prices must be realistic for 2024-2025. Return ONLY valid JSON."""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": f"Find neighbourhoods in {region}"}],
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


# ── PDF Report ───────────────────────────────────────────────────────────
def generate_pdf(profile, rankings, live_data):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "HomeIQ v3 — Relocation Report", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"Generated: {date.today().isoformat()} | BoE Rate: {live_data['base_rate_current']}%", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Your Profile", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Salary: {profile.get('salary', 50000):,} | Partner: {profile.get('partner_salary', 0):,} | Deposit: {profile.get('deposit_pct', 15)}%", ln=True)
    pdf.cell(0, 6, f"Priorities: {', '.join(profile.get('priorities', []))}", ln=True)
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Regional Rankings", ln=True)
    pdf.set_font("Helvetica", "", 9)
    for i, r in enumerate(rankings[:8], 1):
        pdf.cell(0, 5, f"{i}. {r['region']} — Score: {r['composite']} | Financial: {r['financial_score']} | QoL: {r['qol_score']} | Price: {r['price']:,}", ln=True)
    return pdf.output()


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
rankings = rank_all_regions(profile, live, financial_weight, deposit_pct)
top_region = rankings[0]["region"]

# ── Hero header ──────────────────────────────────────────────────────────
st.markdown(f"""
<div style="text-align:center;padding:28px 0 8px;">
    <div style="font-family:'Playfair Display',serif;font-size:38px;font-weight:900;color:#fff;letter-spacing:-0.02em;">
        HomeIQ <span style="color:#c9a84c;">v3</span>
    </div>
    <div style="color:#8899aa;font-size:15px;margin-top:4px;font-family:'DM Sans',sans-serif;">
        Smart Relocation Advisor &middot; RAG-Powered &middot; API-Driven &middot; Persistent Profiles
    </div>
</div>
""", unsafe_allow_html=True)

# ── Key metrics ──────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Top Region", top_region, f"Score {rankings[0]['composite']}")
m2.metric("BoE Base Rate", f"{live['base_rate_current']}%")
m3.metric("5yr Fixed", f"{live['rate_5yr_current']}%")
m4.metric("CPI Inflation", f"{live['cpi_current']}%")

# ── Tabs ─────────────────────────────────────────────────────────────────
tab_brief, tab_ranking, tab_mc, tab_afford, tab_areas, tab_advisor, tab_profile = st.tabs([
    "Your Brief", "Rankings", "Monte Carlo", "Affordability",
    "Neighbourhoods", "AI Advisor (RAG)", "Profiles & History",
])

# ══════════════════════════════════════════════════════════════════════════
# TAB 1: YOUR BRIEF
# ══════════════════════════════════════════════════════════════════════════
with tab_brief:
    st.markdown("<div style='font-family:Playfair Display,serif;font-size:22px;color:#fff;margin-bottom:12px;'>Tell us about your situation</div>", unsafe_allow_html=True)

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
        salary = st.number_input("Annual Salary (£)", value=profile.get("salary", 50000), step=5000, key="form_salary")
        partner_salary = st.number_input("Partner Salary (£)", value=profile.get("partner_salary", 0), step=5000, key="form_partner")
        budget = st.number_input("Property Budget (£)", value=profile.get("budget") or 0, step=25000, key="form_budget")
        job_type = st.selectbox("Work Style", ["hybrid", "remote", "office"], index=["hybrid", "remote", "office"].index(profile.get("job_type", "hybrid")), key="form_job")
        priorities = st.multiselect("Priorities", ["green_space", "schools", "safety", "culture", "healthcare", "commute", "family_friendly", "affordability"], default=profile.get("priorities", []), key="form_priorities")
        current_savings = st.number_input("Current Savings (£)", value=int(profile.get("current_savings", 0)), step=5000, key="form_savings")

        if st.button("Save Profile", key="save_manual"):
            p = {
                "name": "Manual",
                "salary": salary, "partner_salary": partner_salary,
                "budget": budget if budget > 0 else None,
                "deposit_pct": deposit_pct, "job_type": job_type,
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
    lc1, lc2, lc3, lc4 = st.columns(4)
    lc1.metric("Base Rate", f"{live['base_rate_current']}%")
    lc2.metric("2yr Fixed", f"{live['rate_2yr_current']}%")
    lc3.metric("5yr Fixed", f"{live['rate_5yr_current']}%")
    lc4.metric("Earnings Growth", f"{live['earnings_growth_current']}%")

# ══════════════════════════════════════════════════════════════════════════
# TAB 2: REGIONAL RANKINGS
# ══════════════════════════════════════════════════════════════════════════
with tab_ranking:
    st.markdown("<div style='font-family:Playfair Display,serif;font-size:22px;color:#fff;margin-bottom:12px;'>Regional Rankings</div>", unsafe_allow_html=True)

    df_rank = pd.DataFrame(rankings)
    df_display = df_rank[["region", "composite", "financial_score", "qol_score", "affordability_ratio", "monthly_mortgage", "monthly_rent", "disposable_monthly", "price"]].copy()
    df_display.columns = ["Region", "Score", "Financial", "QoL", "Afford. Ratio", "Mortgage/mo", "Rent/mo", "Disposable/mo", "Avg Price"]
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
# TAB 3: MONTE CARLO
# ══════════════════════════════════════════════════════════════════════════
with tab_mc:
    st.markdown("<div style='font-family:Playfair Display,serif;font-size:22px;color:#fff;margin-bottom:12px;'>Monte Carlo Simulation</div>", unsafe_allow_html=True)
    st.caption("Probabilistic comparison of buy-vs-rent net financial position across regions.")

    mc_regions = st.multiselect("Regions to simulate", list(REGIONS.keys()), default=[rankings[0]["region"], rankings[1]["region"], rankings[2]["region"]], key="mc_regions")
    mc_c1, mc_c2 = st.columns(2)
    n_sims = mc_c1.slider("Simulations", 200, 3000, 1000, 100, key="mc_sims")
    mc_horizon = mc_c2.slider("Horizon (years)", 3, 25, horizon, key="mc_horizon")

    if len(mc_regions) >= 2 and st.button("Run Simulation", key="run_mc"):
        with st.spinner(f"Running {n_sims:,} simulations across {len(mc_regions)} regions..."):
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
    st.markdown("<div style='font-family:Playfair Display,serif;font-size:22px;color:#fff;margin-bottom:12px;'>Affordability & Stress Test</div>", unsafe_allow_html=True)

    af_region = st.selectbox("Region", list(REGIONS.keys()), index=list(REGIONS.keys()).index(top_region), key="af_region")
    af_savings = st.number_input("Current Savings (£)", value=int(profile.get("current_savings", 20000)), step=5000, key="af_savings")

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

    save_search(st.session_state.user_id, None, "affordability", {"region": af_region, "savings": af_savings}, af)

# ══════════════════════════════════════════════════════════════════════════
# TAB 5: NEIGHBOURHOOD FINDER
# ══════════════════════════════════════════════════════════════════════════
with tab_areas:
    st.markdown("<div style='font-family:Playfair Display,serif;font-size:22px;color:#fff;margin-bottom:12px;'>Neighbourhood Finder</div>", unsafe_allow_html=True)
    st.caption("AI-powered search for specific areas within a region.")

    nf_region = st.selectbox("Region to explore", list(REGIONS.keys()), index=list(REGIONS.keys()).index(top_region), key="nf_region")
    nf_budget = st.number_input("Budget (£)", value=profile.get("budget") or REGIONS[nf_region]["avg_price"], step=25000, key="nf_budget")

    if st.button("Find Neighbourhoods", key="find_areas") and OPENAI_KEY:
        with st.spinner("Searching for the best neighbourhoods..."):
            result = find_neighbourhoods(nf_region, profile, nf_budget, live, OPENAI_KEY)
            areas = result.get("neighbourhoods", [])

            if areas:
                for area in areas:
                    with st.expander(f"**{area['name']}** ({area.get('postcode_area', '')}) — Match: {area.get('match_score', 0)}%"):
                        ac1, ac2 = st.columns(2)
                        ac1.metric("Avg Price", f"£{area.get('avg_property_price', 0):,}")
                        ac2.metric("Match Score", f"{area.get('match_score', 0)}%")
                        st.write(f"**Price Range:** {area.get('price_range', 'N/A')}")
                        st.write(f"**Schools:** {area.get('school_rating', 'N/A')}")
                        st.write(f"**Transport:** {area.get('transport', 'N/A')}")
                        st.write(area.get("description", ""))

                save_search(st.session_state.user_id, None, "neighbourhood", {"region": nf_region, "budget": nf_budget}, result)
            else:
                st.warning("No neighbourhoods found. Try adjusting the budget.")

# ══════════════════════════════════════════════════════════════════════════
# TAB 6: AI ADVISOR (RAG-POWERED)
# ══════════════════════════════════════════════════════════════════════════
with tab_advisor:
    st.markdown("<div style='font-family:Playfair Display,serif;font-size:22px;color:#fff;margin-bottom:4px;'>AI Relocation Advisor</div>", unsafe_allow_html=True)
    st.markdown("<div style='color:#c9a84c;font-size:13px;margin-bottom:4px;font-weight:600;'>RAG-POWERED — backed by UK housing knowledge base</div>", unsafe_allow_html=True)

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
                lines.append(f"\n**{a['name']}** ({a.get('postcode_area','')}) — Match: {a.get('match_score',0)}%")
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
                parts.append(f"[{r['source']} — {r['section']}] (relevance: {r['similarity']:.2f})\n{r['text']}")
            return "\n\n---\n\n".join(parts)
        return f"Unknown tool: {name}"

    for message in st.session_state.chat_history:
        if message["role"] in ("user", "assistant"):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        elif message["role"] == "rag_sources":
            with st.chat_message("assistant"):
                st.caption(f"Sources: {message['content']}")

    if user_input := st.chat_input("Ask your relocation advisor..."):
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    rag_context = ""
                    rag_sources = []
                    if rag_engine:
                        rag_context = rag_engine.get_context_for_chat(user_input, n_results=3)
                        for chunk in rag_engine.query(user_input, n_results=3):
                            rag_sources.append(f"{chunk['source']} — {chunk['section']}")

                    system_ctx = f"""You are HomeIQ's Smart Relocation Advisor — an expert on UK regions, property, and personal finance.
You have access to a RAG knowledge base with detailed UK housing guides. Use search_knowledge_base for factual questions.
Use computation tools for numerical questions — do NOT guess numbers.

USER PROFILE: Salary £{profile.get('salary', 50000):,}, Partner £{profile.get('partner_salary', 0):,},
{profile.get('job_type', 'hybrid')} worker, Priorities: {', '.join(profile.get('priorities', []))},
Deposit: {deposit_pct}%

TOP RANKED REGIONS:
{chr(10).join(f"- {r['region']}: Score {r['composite']}" for r in rankings[:5])}

LIVE MARKET: BoE rate {live['base_rate_current']}%, 5yr fixed {live['rate_5yr_current']}%, CPI {live['cpi_current']}%

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
                            st.info(f"Computing: {tc.function.name}...")
                            result = execute_advisor_tool(tc.function.name, tc.function.arguments)
                            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                        response = client.chat.completions.create(
                            model="gpt-4o", messages=messages, tools=ADVISOR_TOOLS,
                            tool_choice="auto", max_tokens=800,
                        )
                        iterations += 1
                    reply = response.choices[0].message.content or "Analysis complete."

                    if rag_sources:
                        st.caption(f"Sources: {' | '.join(set(rag_sources))}")
                        st.session_state.chat_history.append({"role": "rag_sources", "content": " | ".join(set(rag_sources))})

                except Exception as e:
                    reply = f"Error: {str(e)}"
            st.markdown(reply)
            st.session_state.chat_history.append({"role": "assistant", "content": reply})

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
    st.markdown("<div style='font-family:Playfair Display,serif;font-size:22px;color:#fff;margin-bottom:12px;'>Profiles & History</div>", unsafe_allow_html=True)
    st.caption("Your data is stored in a SQLite database — persistent across sessions.")

    st.markdown("##### Saved Profiles")
    profiles = get_all_profiles(st.session_state.user_id)
    if profiles:
        for p in profiles:
            active = " (ACTIVE)" if p.get("is_active") else ""
            with st.expander(f"{p['name']}{active} — £{p['salary']:,} | Created: {p['created_at']}", expanded=p.get("is_active", False)):
                pc1, pc2, pc3 = st.columns(3)
                pc1.write(f"**Salary:** £{p['salary']:,}")
                pc2.write(f"**Partner:** £{p['partner_salary']:,}")
                pc3.write(f"**Deposit:** {p['deposit_pct']}%")
                budget_str = "£{:,}".format(int(p["budget"])) if p.get("budget") else "Not set"
                st.write(f"**Budget:** {budget_str}")
                st.write(f"**Priorities:** {', '.join(p.get('priorities', []))}")
                st.write(f"**Work:** {p.get('job_type', 'hybrid')}")
                bc1, bc2 = st.columns(2)
                if not p.get("is_active"):
                    if bc1.button("Activate", key=f"activate_{p['id']}"):
                        set_active_profile(st.session_state.user_id, p["id"])
                        st.rerun()
                if bc2.button("Delete", key=f"delete_{p['id']}"):
                    delete_profile(st.session_state.user_id, p["id"])
                    st.rerun()
    else:
        st.info("No saved profiles yet. Use the Brief tab to create one.")

    st.markdown("---")
    st.markdown("##### Search History")
    history = get_search_history(st.session_state.user_id, limit=10)
    if history:
        for h in history:
            with st.expander(f"{h['search_type'].title()} — {h['created_at']}"):
                st.json(h["query_params"])
    else:
        st.info("No search history yet.")

    st.markdown("---")
    st.markdown("##### Saved Comparisons")
    comparisons = get_saved_comparisons(st.session_state.user_id)
    if comparisons:
        for comp in comparisons:
            with st.expander(f"Comparison — {comp['created_at']} | {comp.get('notes', '')}"):
                st.write(f"**Regions:** {', '.join(comp['regions'][:5])}{'...' if len(comp['regions']) > 5 else ''}")
                top3 = comp["rankings"][:3]
                for r in top3:
                    st.write(f"  {r['region']}: Score {r['composite']}")
                if st.button("Delete", key=f"del_comp_{comp['id']}"):
                    delete_comparison(st.session_state.user_id, comp["id"])
                    st.rerun()
    else:
        st.info("No saved comparisons yet.")

    st.markdown("---")
    st.markdown("##### Chat Sessions")
    sessions = get_chat_sessions(st.session_state.user_id)
    if sessions:
        for s in sessions:
            st.write(f"- **{s['title']}** — {s['updated_at']}")
    else:
        st.info("No chat sessions saved yet.")

# ── Footer ───────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:32px 0 16px;color:#243048;font-size:12px;">
    HomeIQ v3 &middot; Smart Relocation Advisor &middot; RAG-Powered &middot; API-Driven &middot; SQLite Persistence<br>
    Live data: Bank of England IADB & ONS API &middot; Not financial advice
</div>
""", unsafe_allow_html=True)

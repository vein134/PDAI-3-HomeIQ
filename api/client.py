"""
HTTP client for the HomeIQ FastAPI backend.
The Streamlit frontend calls the API through this module instead of importing core modules directly.
"""
from __future__ import annotations
import requests
import streamlit as st

API_BASE = "http://localhost:8000"


def _post(path, json_data=None):
    resp = requests.post("{}{}".format(API_BASE, path), json=json_data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get(path, params=None):
    resp = requests.get("{}{}".format(API_BASE, path), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=300, show_spinner=False)
def api_get_live_data():
    return _get("/finance/live-data")


@st.cache_data(ttl=300, show_spinner=False)
def api_get_regions():
    return _get("/scoring/regions")


def api_rank_regions(profile, financial_weight=50, deposit_pct=15):
    return _post("/scoring/rank", {
        "salary": profile.get("salary", 50000),
        "partner_salary": profile.get("partner_salary", 0),
        "budget": profile.get("budget"),
        "priorities": profile.get("priorities", []),
        "job_type": profile.get("job_type", "hybrid"),
        "financial_weight": financial_weight,
        "deposit_pct": deposit_pct,
    })


def api_affordability(salary, partner_salary, region, deposit_pct, current_savings):
    return _post("/finance/affordability", {
        "salary": salary,
        "partner_salary": partner_salary,
        "region": region,
        "deposit_pct": deposit_pct,
        "current_savings": current_savings,
    })


def api_monte_carlo(regions, profile, n_sims=1000, horizon=10, deposit_pct=15):
    return _post("/scoring/monte-carlo", {
        "regions": regions,
        "salary": profile.get("salary", 50000),
        "partner_salary": profile.get("partner_salary", 0),
        "budget": profile.get("budget"),
        "priorities": profile.get("priorities", []),
        "n_sims": n_sims,
        "horizon": horizon,
        "deposit_pct": deposit_pct,
    })


def api_budget(salary, partner_salary, region, deposit_pct, mortgage_rate):
    return _post("/finance/budget", {
        "salary": salary,
        "partner_salary": partner_salary,
        "region": region,
        "deposit_pct": deposit_pct,
        "mortgage_rate": mortgage_rate,
    })


def api_chat(message, session_id=None, user_id=1, profile=None):
    return _post("/chat/message", {
        "message": message,
        "session_id": session_id,
        "user_id": user_id,
        "profile": profile,
    })


def api_rag_stats():
    return _get("/chat/rag/stats")


def is_api_available():
    try:
        resp = requests.get("{}/".format(API_BASE), timeout=2)
        return resp.status_code == 200
    except Exception:
        return False

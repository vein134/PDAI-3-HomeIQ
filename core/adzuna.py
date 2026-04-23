from __future__ import annotations
import os
import time
import requests
import streamlit as st

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs/gb"

INDUSTRY_TO_ADZUNA = {
    "technology": "it-jobs",
    "finance": "accounting-finance-jobs",
    "healthcare": "healthcare-nursing-jobs",
    "education": "teaching-jobs",
    "creative": "creative-design-jobs",
    "engineering": "engineering-jobs",
    "legal": "legal-jobs",
    "retail_hospitality": "retail-jobs",
    "construction": "construction-jobs",
    "public_sector": "admin-jobs",
}

REGION_TO_ADZUNA = {
    "London": "London",
    "South East": "South East England",
    "South West": "South West England",
    "East of England": "Eastern England",
    "East Midlands": "East Midlands",
    "West Midlands": "West Midlands",
    "Yorkshire": "Yorkshire and The Humber",
    "North West": "North West England",
    "North East": "North East England",
    "Wales": "Wales",
    "Scotland": "Scotland",
    "Northern Ireland": "Northern Ireland",
}


def _get_credentials():
    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    if not app_id:
        try:
            app_id = st.secrets.get("ADZUNA_APP_ID", "")
            app_key = st.secrets.get("ADZUNA_APP_KEY", "")
        except Exception:
            pass
    return app_id, app_key


def fetch_job_stats(industry, region_name):
    app_id, app_key = _get_credentials()
    if not app_id or not app_key:
        return None

    category = INDUSTRY_TO_ADZUNA.get(industry)
    location = REGION_TO_ADZUNA.get(region_name)
    if not category or not location:
        return None

    try:
        resp = requests.get(
            "{}/search/1".format(ADZUNA_BASE),
            params={
                "app_id": app_id,
                "app_key": app_key,
                "category": category,
                "where": location,
                "results_per_page": 0,
                "content-type": "application/json",
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {
            "count": data.get("count", 0),
            "mean_salary": round(data.get("mean", 0)),
        }
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_job_stats(industry):
    results = {}
    for region_name in REGION_TO_ADZUNA:
        stats = fetch_job_stats(industry, region_name)
        if stats:
            results[region_name] = stats
        time.sleep(0.15)
    return results


def get_live_job_density(industry):
    stats = fetch_all_job_stats(industry)
    if not stats:
        return {}
    counts = {r: s["count"] for r, s in stats.items()}
    max_count = max(counts.values()) if counts else 1
    return {r: round(c / max_count * 100) for r, c in counts.items()}


def get_live_salary_premium(industry):
    stats = fetch_all_job_stats(industry)
    if not stats:
        return {}
    salaries = {r: s["mean_salary"] for r, s in stats.items() if s["mean_salary"] > 0}
    if not salaries:
        return {}
    uk_mean = sum(salaries.values()) / len(salaries)
    return {r: round(s / uk_mean, 2) for r, s in salaries.items()}

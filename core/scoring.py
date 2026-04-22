import numpy as np
from core.regions import REGIONS, QOL_DIMS
from core.tax import compute_uk_tax, compute_stamp_duty


def compute_monthly_budget(salary, partner_salary, region_name, deposit_pct, mortgage_rate):
    r = REGIONS[region_name]
    tax1 = compute_uk_tax(salary)
    tax2 = compute_uk_tax(partner_salary) if partner_salary > 0 else {"net_monthly": 0}
    net_monthly = tax1["net_monthly"] + tax2["net_monthly"]
    price = r["avg_price"]
    loan = price * (1 - deposit_pct / 100)
    mr = mortgage_rate / 100 / 12
    n = 25 * 12
    monthly_mortgage = loan * (mr * (1 + mr)**n) / ((1 + mr)**n - 1) if mr > 0 else loan / n
    monthly_rent = int(price * r["rental_yield"] / 100 / 12)
    council_tax_monthly = r["council_tax"] / 12
    living_costs = 1500 * r["col_index"] / 100
    return {
        "net_monthly": round(net_monthly),
        "monthly_mortgage": round(monthly_mortgage),
        "monthly_rent": round(monthly_rent),
        "council_tax_monthly": round(council_tax_monthly),
        "living_costs": round(living_costs),
        "disposable_buy": round(net_monthly - monthly_mortgage - council_tax_monthly - living_costs),
        "disposable_rent": round(net_monthly - monthly_rent - council_tax_monthly - living_costs),
        "price": price,
        "loan": round(loan),
    }


def compute_regional_score(region_name, profile, live_data, financial_weight=50, deposit_pct=15):
    r = REGIONS[region_name]
    salary = profile.get("salary") or 50000
    partner_salary = profile.get("partner_salary") or 0
    user_budget = profile.get("budget") or None
    priorities = profile.get("priorities") or []

    household_income = salary + partner_salary
    price_for_scoring = r["avg_price"]
    if user_budget and user_budget < r["avg_price"]:
        price_for_scoring = user_budget * 1.10
    affordability = price_for_scoring / max(household_income, 1)
    afford_score = max(0, min(100, 100 - (affordability - 3) * 20))

    budget_data = compute_monthly_budget(
        salary, partner_salary, region_name, deposit_pct, live_data["rate_5yr_current"]
    )
    disp_score = max(0, min(100, budget_data["disposable_buy"] / 30))
    financial_score = afford_score * 0.5 + disp_score * 0.5

    priority_map = {
        "green_space": "green_space", "schools": "schools", "safety": "safety",
        "culture": "culture", "healthcare": "healthcare", "commute": "commute",
        "family_friendly": "schools", "affordability": None,
    }
    weights = {d: 1.0 for d in QOL_DIMS}
    for p in priorities:
        dim = priority_map.get(p)
        if dim and dim in weights:
            weights[dim] = 2.5

    total_w = sum(weights.values())
    qol_score = sum(r[d] * weights[d] for d in QOL_DIMS) / total_w

    fw = financial_weight / 100
    composite = financial_score * fw + qol_score * (1 - fw)

    return {
        "region": region_name,
        "financial_score": round(financial_score, 1),
        "qol_score": round(qol_score, 1),
        "composite": round(composite, 1),
        "affordability_ratio": round(affordability, 1),
        "disposable_monthly": budget_data["disposable_buy"],
        "monthly_mortgage": budget_data["monthly_mortgage"],
        "monthly_rent": budget_data["monthly_rent"],
        "price": r["avg_price"],
    }


def compute_affordability(salary, partner_salary, region_name, deposit_pct, current_savings=0):
    r = REGIONS[region_name]
    household_income = salary + partner_salary
    max_borrowing = household_income * 4.5
    price = r["avg_price"]
    deposit = price * deposit_pct / 100
    loan = price - deposit
    stamp = compute_stamp_duty(price, True)
    solicitor = 1500
    survey = 500
    total_upfront = deposit + stamp + solicitor + survey
    shortfall = max(0, total_upfront - current_savings)
    t = compute_uk_tax(salary)
    t2 = compute_uk_tax(partner_salary) if partner_salary else {"net_monthly": 0}
    net_monthly = t["net_monthly"] + t2["net_monthly"]
    living = 1500 * r["col_index"] / 100
    est_monthly_save = max(100, (net_monthly - living - r["council_tax"] / 12) * 0.30)
    months_to_save = int(np.ceil(shortfall / est_monthly_save)) if shortfall > 0 else 0
    stress_rates = np.arange(2.0, 10.5, 0.5)
    stress_payments = []
    for sr in stress_rates:
        mr = sr / 100 / 12
        mp = loan * (mr * (1 + mr)**300) / ((1 + mr)**300 - 1)
        stress_payments.append(round(mp))
    return {
        "max_borrowing": round(max_borrowing),
        "loan_needed": round(loan),
        "can_borrow": loan <= max_borrowing,
        "price": price,
        "deposit": round(deposit),
        "stamp": stamp,
        "solicitor": solicitor,
        "survey": survey,
        "total_upfront": round(total_upfront),
        "shortfall": round(shortfall),
        "months_to_save": months_to_save,
        "est_monthly_save": round(est_monthly_save),
        "stress_rates": stress_rates.tolist(),
        "stress_payments": stress_payments,
        "net_monthly": round(net_monthly),
        "danger_line": round(net_monthly * 0.35),
    }


def rank_all_regions(profile, live_data, financial_weight=50, deposit_pct=15):
    rankings = []
    for region_name in REGIONS:
        score = compute_regional_score(region_name, profile, live_data, financial_weight, deposit_pct)
        rankings.append(score)
    rankings.sort(key=lambda x: x["composite"], reverse=True)
    return rankings

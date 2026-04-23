import numpy as np
from core.regions import REGIONS
from core.tax import compute_stamp_duty


def run_regional_monte_carlo(regions_list, profile, live_data, n_sims=1000, horizon=10, seed=None, deposit_pct=15):
    rng = np.random.default_rng(seed)
    salary = profile.get("salary") or 50000
    partner_salary = profile.get("partner_salary") or 0
    base_rate = live_data["rate_5yr_current"]

    results = {}
    rate_shocks = rng.normal(0, 1.0, (n_sims, horizon))
    inflation_shocks = rng.normal(0, 1.0, (n_sims, horizon))

    for region_name in regions_list:
        r = REGIONS[region_name]
        price = float(r["avg_price"])
        loan = price * (1 - deposit_pct / 100)
        deposit = price * deposit_pct / 100
        stamp = compute_stamp_duty(price, True)
        monthly_rent_base = price * r["rental_yield"] / 100 / 12
        col_factor = r["col_index"] / 100

        appreciation = rng.normal(3.5, 2.0, (n_sims, horizon))
        yearly_vol = rng.normal(0, 3.0, (n_sims, horizon))
        eff_rates = np.clip(base_rate + rate_shocks[:, 0], 1.0, 10.0)

        mr = eff_rates / 100 / 12
        n_payments = 25 * 12
        monthly_payments = loan * (mr * (1 + mr)**n_payments) / ((1 + mr)**n_payments - 1)
        total_mortgage_paid = monthly_payments * 12 * horizon

        property_values = np.full(n_sims, price)
        for yr in range(horizon):
            annual_growth = appreciation[:, yr] + yearly_vol[:, yr]
            property_values *= (1 + annual_growth / 100)

        remaining_balance_frac = 1 - (horizon / 25)
        equity = property_values - loan * max(0, remaining_balance_frac)
        net_gain_buy = equity - deposit - stamp - total_mortgage_paid

        inflation = np.clip(live_data["cpi_current"] + inflation_shocks, 1.0, 8.0)
        rent_growth = inflation * 0.8 + rng.normal(0.5, 0.5, (n_sims, horizon))
        total_rent = np.zeros(n_sims)
        rent = np.full(n_sims, monthly_rent_base)
        for yr in range(horizon):
            total_rent += rent * 12
            rent *= (1 + rent_growth[:, yr] / 100)

        net_position = net_gain_buy + total_rent

        results[region_name] = {
            "median_property_value": round(float(np.median(property_values))),
            "p10": round(float(np.percentile(net_position, 10))),
            "p25": round(float(np.percentile(net_position, 25))),
            "p50": round(float(np.median(net_position))),
            "p75": round(float(np.percentile(net_position, 75))),
            "p90": round(float(np.percentile(net_position, 90))),
            "prob_positive": round(float(np.mean(net_position > 0) * 100), 1),
            "prob_best": 0,
            "mean_net": round(float(np.mean(net_position))),
            "std_net": round(float(np.std(net_position))),
            "histogram": net_position.tolist(),
        }

    if len(regions_list) > 1:
        all_nets = np.column_stack([
            np.array(results[r]["histogram"]) for r in regions_list
        ])
        best_idx = np.argmax(all_nets, axis=1)
        for i, rname in enumerate(regions_list):
            results[rname]["prob_best"] = round(float(np.mean(best_idx == i)), 3)

    return results

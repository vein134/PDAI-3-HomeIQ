def compute_uk_tax(gross: float) -> dict:
    personal_allowance = 12570
    if gross > 125140:
        personal_allowance = 0
    elif gross > 100000:
        personal_allowance = max(0, 12570 - (gross - 100000) / 2)
    taxable = max(0, gross - personal_allowance)
    tax = 0
    if taxable > 0:
        basic = min(taxable, 37700)
        tax += basic * 0.20
    if taxable > 37700:
        higher = min(taxable - 37700, 87440)
        tax += higher * 0.40
    if taxable > 125140:
        tax += (taxable - 125140) * 0.45
    ni = 0
    if gross > 12570:
        ni_basic = min(gross, 50270) - 12570
        ni += ni_basic * 0.08
    if gross > 50270:
        ni += (gross - 50270) * 0.02
    net = gross - tax - ni
    return {
        "gross": gross,
        "tax": round(tax),
        "ni": round(ni),
        "net_annual": round(net),
        "net_monthly": round(net / 12),
    }


def compute_stamp_duty(price: float, first_time_buyer: bool = False) -> int:
    if first_time_buyer:
        if price <= 425000:
            return 0
        elif price <= 625000:
            return round((price - 425000) * 0.05)
    bands = [(250000, 0.0), (675000, 0.05), (925000, 0.10), (1500000, 0.12)]
    tax, prev = 0.0, 0.0
    for threshold, rate in bands:
        if price <= prev:
            break
        tax += (min(price, threshold) - prev) * rate
        prev = threshold
    return round(tax)

from core.adzuna import get_live_job_density, get_live_salary_premium, fetch_all_job_stats

INDUSTRIES = {
    "technology": {
        "label": "Technology & Software",
        "avg_uk_salary": 55000,
        "growth_rate": 8.5,
        "remote_friendly": 0.85,
    },
    "finance": {
        "label": "Finance & Banking",
        "avg_uk_salary": 58000,
        "growth_rate": 4.2,
        "remote_friendly": 0.60,
    },
    "healthcare": {
        "label": "Healthcare & NHS",
        "avg_uk_salary": 38000,
        "growth_rate": 3.8,
        "remote_friendly": 0.15,
    },
    "education": {
        "label": "Education & Research",
        "avg_uk_salary": 35000,
        "growth_rate": 2.5,
        "remote_friendly": 0.30,
    },
    "creative": {
        "label": "Creative & Media",
        "avg_uk_salary": 40000,
        "growth_rate": 5.0,
        "remote_friendly": 0.75,
    },
    "engineering": {
        "label": "Engineering & Manufacturing",
        "avg_uk_salary": 45000,
        "growth_rate": 3.5,
        "remote_friendly": 0.25,
    },
    "legal": {
        "label": "Legal & Professional Services",
        "avg_uk_salary": 52000,
        "growth_rate": 3.0,
        "remote_friendly": 0.50,
    },
    "retail_hospitality": {
        "label": "Retail & Hospitality",
        "avg_uk_salary": 25000,
        "growth_rate": 1.5,
        "remote_friendly": 0.05,
    },
    "construction": {
        "label": "Construction & Property",
        "avg_uk_salary": 38000,
        "growth_rate": 4.0,
        "remote_friendly": 0.10,
    },
    "public_sector": {
        "label": "Public Sector & Government",
        "avg_uk_salary": 34000,
        "growth_rate": 1.8,
        "remote_friendly": 0.40,
    },
}

REGION_INDUSTRY_SCORES = {
    "London": {
        "technology": 95, "finance": 98, "healthcare": 80, "education": 85,
        "creative": 95, "engineering": 40, "legal": 95, "retail_hospitality": 90,
        "construction": 70, "public_sector": 90,
        "salary_premium": 1.25,
        "job_growth_5yr": 12.0,
        "major_employers": ["Google", "Meta", "Barclays", "HSBC", "NHS London", "BBC"],
        "emerging_sectors": ["AI/ML", "FinTech", "CleanTech"],
    },
    "South East": {
        "technology": 80, "finance": 70, "healthcare": 75, "education": 80,
        "creative": 55, "engineering": 65, "legal": 65, "retail_hospitality": 70,
        "construction": 75, "public_sector": 70,
        "salary_premium": 1.10,
        "job_growth_5yr": 8.5,
        "major_employers": ["Microsoft", "Samsung", "AstraZeneca", "University of Oxford"],
        "emerging_sectors": ["BioTech", "Space Tech", "Quantum Computing"],
    },
    "South West": {
        "technology": 60, "finance": 35, "healthcare": 65, "education": 70,
        "creative": 55, "engineering": 50, "legal": 40, "retail_hospitality": 75,
        "construction": 60, "public_sector": 55,
        "salary_premium": 0.95,
        "job_growth_5yr": 7.0,
        "major_employers": ["Airbus", "MoD", "University of Bristol", "Dyson"],
        "emerging_sectors": ["Aerospace", "Green Energy", "AgriTech"],
    },
    "East of England": {
        "technology": 85, "finance": 45, "healthcare": 70, "education": 90,
        "creative": 40, "engineering": 60, "legal": 40, "retail_hospitality": 55,
        "construction": 60, "public_sector": 50,
        "salary_premium": 1.05,
        "job_growth_5yr": 9.0,
        "major_employers": ["ARM", "AstraZeneca", "University of Cambridge", "Marshall"],
        "emerging_sectors": ["BioTech", "AI Research", "Genomics"],
    },
    "East Midlands": {
        "technology": 45, "finance": 30, "healthcare": 65, "education": 65,
        "creative": 30, "engineering": 75, "legal": 30, "retail_hospitality": 60,
        "construction": 65, "public_sector": 55,
        "salary_premium": 0.88,
        "job_growth_5yr": 5.5,
        "major_employers": ["Rolls-Royce", "Boots", "Experian", "Universities of Nottingham/Leicester"],
        "emerging_sectors": ["Advanced Manufacturing", "Logistics Tech", "MedTech"],
    },
    "West Midlands": {
        "technology": 55, "finance": 50, "healthcare": 70, "education": 65,
        "creative": 50, "engineering": 70, "legal": 55, "retail_hospitality": 65,
        "construction": 70, "public_sector": 65,
        "salary_premium": 0.90,
        "job_growth_5yr": 7.5,
        "major_employers": ["Jaguar Land Rover", "HSBC UK", "PwC", "University of Birmingham"],
        "emerging_sectors": ["FinTech", "Automotive EV", "Digital Health"],
    },
    "Yorkshire": {
        "technology": 55, "finance": 60, "healthcare": 65, "education": 70,
        "creative": 45, "engineering": 55, "legal": 55, "retail_hospitality": 60,
        "construction": 55, "public_sector": 60,
        "salary_premium": 0.87,
        "job_growth_5yr": 6.5,
        "major_employers": ["NHS Yorkshire", "Asda", "Sky Betting", "Channel 4 (Leeds)"],
        "emerging_sectors": ["Digital Media", "HealthTech", "Data Analytics"],
    },
    "North West": {
        "technology": 65, "finance": 55, "healthcare": 70, "education": 70,
        "creative": 75, "engineering": 55, "legal": 50, "retail_hospitality": 70,
        "construction": 60, "public_sector": 65,
        "salary_premium": 0.90,
        "job_growth_5yr": 8.0,
        "major_employers": ["BBC MediaCity", "Booking.com", "AO.com", "University of Manchester"],
        "emerging_sectors": ["Creative Digital", "Cyber Security", "Green Energy"],
    },
    "North East": {
        "technology": 35, "finance": 25, "healthcare": 60, "education": 55,
        "creative": 30, "engineering": 50, "legal": 25, "retail_hospitality": 45,
        "construction": 45, "public_sector": 55,
        "salary_premium": 0.82,
        "job_growth_5yr": 3.5,
        "major_employers": ["Nissan", "NHS North East", "Sage", "Newcastle University"],
        "emerging_sectors": ["Offshore Wind", "Digital Services", "EV Battery"],
    },
    "Wales": {
        "technology": 30, "finance": 25, "healthcare": 55, "education": 55,
        "creative": 35, "engineering": 45, "legal": 25, "retail_hospitality": 50,
        "construction": 50, "public_sector": 60,
        "salary_premium": 0.83,
        "job_growth_5yr": 3.0,
        "major_employers": ["DVLA", "Admiral", "Tata Steel", "Cardiff University"],
        "emerging_sectors": ["Cyber Security (NCSC)", "Compound Semiconductors", "Renewable Energy"],
    },
    "Scotland": {
        "technology": 60, "finance": 55, "healthcare": 70, "education": 75,
        "creative": 55, "engineering": 60, "legal": 50, "retail_hospitality": 65,
        "construction": 55, "public_sector": 70,
        "salary_premium": 0.92,
        "job_growth_5yr": 5.5,
        "major_employers": ["RBS/NatWest", "Skyscanner", "NHS Scotland", "University of Edinburgh"],
        "emerging_sectors": ["FinTech", "Space Tech", "Renewable Energy", "Data Science"],
    },
    "Northern Ireland": {
        "technology": 35, "finance": 20, "healthcare": 55, "education": 50,
        "creative": 20, "engineering": 40, "legal": 20, "retail_hospitality": 45,
        "construction": 45, "public_sector": 55,
        "salary_premium": 0.80,
        "job_growth_5yr": 2.5,
        "major_employers": ["Bombardier", "Citibank Belfast", "Allstate NI", "Queen's University"],
        "emerging_sectors": ["Cyber Security", "FinTech Ops", "Screen Industries"],
    },
}


def get_career_score(region_name, industry):
    region = REGION_INDUSTRY_SCORES.get(region_name, {})
    if not region or industry not in INDUSTRIES:
        return 0.0
    industry_score = region.get(industry, 50)
    growth = region.get("job_growth_5yr", 5.0)
    growth_score = min(100, growth * 8)
    return round(industry_score * 0.7 + growth_score * 0.3, 1)


def get_salary_projection(base_salary, region_name, industry, years=10):
    region = REGION_INDUSTRY_SCORES.get(region_name, {})
    ind = INDUSTRIES.get(industry, {})
    premium = region.get("salary_premium", 1.0)
    regional_salary = base_salary * premium
    growth_rate = ind.get("growth_rate", 3.0) / 100
    regional_growth_boost = (region.get("job_growth_5yr", 5.0) - 5.0) / 100
    effective_growth = growth_rate + regional_growth_boost * 0.3

    projections = []
    salary = regional_salary
    for year in range(years + 1):
        projections.append({
            "year": year,
            "salary": round(salary),
            "cumulative_earnings": round(sum(p["salary"] for p in projections) + salary) if projections else round(salary),
        })
        salary *= (1 + effective_growth)

    return {
        "starting_salary": round(regional_salary),
        "year_5_salary": projections[5]["salary"] if len(projections) > 5 else projections[-1]["salary"],
        "year_10_salary": projections[10]["salary"] if len(projections) > 10 else projections[-1]["salary"],
        "total_earnings_10yr": sum(p["salary"] for p in projections[:11]),
        "projections": projections,
    }


def get_region_career_summary(region_name):
    region = REGION_INDUSTRY_SCORES.get(region_name, {})
    if not region:
        return {}

    top_industries = sorted(
        [(ind, region.get(ind, 0)) for ind in INDUSTRIES],
        key=lambda x: x[1],
        reverse=True,
    )[:5]

    live_stats = {}
    for ind, _ in top_industries:
        all_stats = fetch_all_job_stats(ind)
        if all_stats and region_name in all_stats:
            live_stats[ind] = all_stats[region_name]

    return {
        "salary_premium": region.get("salary_premium", 1.0),
        "job_growth_5yr": region.get("job_growth_5yr", 0),
        "major_employers": region.get("major_employers", []),
        "emerging_sectors": region.get("emerging_sectors", []),
        "top_industries": [
            {
                "industry": ind,
                "label": INDUSTRIES[ind]["label"],
                "score": score,
                "live_jobs": live_stats.get(ind, {}).get("count"),
                "live_salary": live_stats.get(ind, {}).get("mean_salary"),
            }
            for ind, score in top_industries
        ],
    }


def compute_career_adjusted_score(region_name, industry, job_type):
    region = REGION_INDUSTRY_SCORES.get(region_name, {})
    ind_data = INDUSTRIES.get(industry, {})
    if not region or not ind_data:
        return 50.0

    live_density = get_live_job_density(industry)
    live_premium = get_live_salary_premium(industry)

    if live_density and region_name in live_density:
        job_density = live_density[region_name] * 0.6 + region.get(industry, 50) * 0.4
    else:
        job_density = region.get(industry, 50)

    growth_factor = min(100, region.get("job_growth_5yr", 5.0) * 8)

    if live_premium and region_name in live_premium:
        salary_factor = min(100, live_premium[region_name] * 80) * 0.7 + min(100, region.get("salary_premium", 1.0) * 80) * 0.3
    else:
        salary_factor = min(100, region.get("salary_premium", 1.0) * 80)

    if job_type == "remote":
        remote_friendliness = ind_data.get("remote_friendly", 0.5)
        score = (
            job_density * 0.2 +
            growth_factor * 0.25 +
            salary_factor * 0.25 +
            remote_friendliness * 100 * 0.3
        )
    elif job_type == "office":
        score = (
            job_density * 0.50 +
            growth_factor * 0.20 +
            salary_factor * 0.30
        )
    else:
        remote_friendliness = ind_data.get("remote_friendly", 0.5)
        score = (
            job_density * 0.35 +
            growth_factor * 0.20 +
            salary_factor * 0.25 +
            remote_friendliness * 100 * 0.20
        )

    return round(min(100, score), 1)

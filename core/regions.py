REGIONS = {
    "London": {
        "avg_price": 520000, "rental_yield": 3.2, "avg_salary": 44000,
        "col_index": 100, "council_tax": 1898,
        "commute": 40, "green_space": 45, "schools": 75, "safety": 50,
        "culture": 95, "healthcare": 80, "job_market": 95,
    },
    "South East": {
        "avg_price": 380000, "rental_yield": 3.8, "avg_salary": 38000,
        "col_index": 88, "council_tax": 2050,
        "commute": 55, "green_space": 75, "schools": 80, "safety": 72,
        "culture": 65, "healthcare": 75, "job_market": 80,
    },
    "South West": {
        "avg_price": 310000, "rental_yield": 4.1, "avg_salary": 34000,
        "col_index": 82, "council_tax": 2100,
        "commute": 60, "green_space": 90, "schools": 72, "safety": 80,
        "culture": 60, "healthcare": 68, "job_market": 55,
    },
    "East of England": {
        "avg_price": 340000, "rental_yield": 3.9, "avg_salary": 36000,
        "col_index": 85, "council_tax": 1950,
        "commute": 50, "green_space": 70, "schools": 74, "safety": 75,
        "culture": 50, "healthcare": 70, "job_market": 65,
    },
    "East Midlands": {
        "avg_price": 230000, "rental_yield": 4.6, "avg_salary": 32000,
        "col_index": 75, "council_tax": 1850,
        "commute": 65, "green_space": 72, "schools": 68, "safety": 70,
        "culture": 50, "healthcare": 65, "job_market": 55,
    },
    "West Midlands": {
        "avg_price": 245000, "rental_yield": 4.5, "avg_salary": 33000,
        "col_index": 77, "council_tax": 1780,
        "commute": 58, "green_space": 60, "schools": 65, "safety": 60,
        "culture": 70, "healthcare": 72, "job_market": 65,
    },
    "Yorkshire": {
        "avg_price": 200000, "rental_yield": 5.0, "avg_salary": 31000,
        "col_index": 73, "council_tax": 1750,
        "commute": 62, "green_space": 80, "schools": 66, "safety": 62,
        "culture": 65, "healthcare": 68, "job_market": 55,
    },
    "North West": {
        "avg_price": 210000, "rental_yield": 5.2, "avg_salary": 32000,
        "col_index": 74, "council_tax": 1800,
        "commute": 58, "green_space": 65, "schools": 64, "safety": 55,
        "culture": 80, "healthcare": 72, "job_market": 65,
    },
    "North East": {
        "avg_price": 155000, "rental_yield": 5.8, "avg_salary": 30000,
        "col_index": 70, "council_tax": 1700,
        "commute": 68, "green_space": 75, "schools": 60, "safety": 58,
        "culture": 50, "healthcare": 64, "job_market": 40,
    },
    "Wales": {
        "avg_price": 195000, "rental_yield": 4.8, "avg_salary": 30500,
        "col_index": 72, "council_tax": 1650,
        "commute": 60, "green_space": 92, "schools": 62, "safety": 75,
        "culture": 55, "healthcare": 60, "job_market": 40,
    },
    "Scotland": {
        "avg_price": 195000, "rental_yield": 4.7, "avg_salary": 33000,
        "col_index": 74, "council_tax": 1450,
        "commute": 62, "green_space": 88, "schools": 72, "safety": 68,
        "culture": 75, "healthcare": 74, "job_market": 60,
    },
    "Northern Ireland": {
        "avg_price": 175000, "rental_yield": 5.5, "avg_salary": 30000,
        "col_index": 68, "council_tax": 1350,
        "commute": 65, "green_space": 85, "schools": 70, "safety": 72,
        "culture": 45, "healthcare": 62, "job_market": 35,
    },
}

QOL_DIMS = ["commute", "green_space", "schools", "safety", "culture", "healthcare"]
QOL_LABELS = ["Commute", "Green Space", "Schools", "Safety", "Culture", "Healthcare"]

COMMUTE_COSTS = {
    ("South East", "London"): {"season_ticket": 4500, "drive_miles": 45},
    ("South West", "London"): {"season_ticket": 8500, "drive_miles": 120},
    ("East of England", "London"): {"season_ticket": 5200, "drive_miles": 55},
    ("East Midlands", "London"): {"season_ticket": 9200, "drive_miles": 110},
    ("West Midlands", "London"): {"season_ticket": 10400, "drive_miles": 120},
    ("Yorkshire", "London"): {"season_ticket": 11500, "drive_miles": 185},
    ("North West", "London"): {"season_ticket": 11800, "drive_miles": 200},
    ("North East", "London"): {"season_ticket": 12500, "drive_miles": 260},
    ("Wales", "London"): {"season_ticket": 9800, "drive_miles": 155},
    ("Scotland", "London"): {"season_ticket": 13500, "drive_miles": 400},
    ("Northern Ireland", "London"): {"season_ticket": 15000, "drive_miles": 500},
    ("East Midlands", "West Midlands"): {"season_ticket": 3200, "drive_miles": 50},
    ("Yorkshire", "North West"): {"season_ticket": 3800, "drive_miles": 60},
    ("Yorkshire", "West Midlands"): {"season_ticket": 5500, "drive_miles": 90},
    ("North West", "West Midlands"): {"season_ticket": 4200, "drive_miles": 80},
    ("South East", "South West"): {"season_ticket": 4800, "drive_miles": 100},
    ("Scotland", "North East"): {"season_ticket": 4500, "drive_miles": 105},
    ("Wales", "West Midlands"): {"season_ticket": 3600, "drive_miles": 70},
    ("East of England", "East Midlands"): {"season_ticket": 4000, "drive_miles": 75},
}

HMRC_MILEAGE_RATE = 0.45

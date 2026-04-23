import requests
import pandas as pd
from io import StringIO
import time

_cache = {}
_cache_time = {}
CACHE_TTL = 3600

HEADERS = {"User-Agent": "Mozilla/5.0 HomeIQ/3.0"}


def _get_cached(key, fetcher):
    now = time.time()
    if key in _cache and (now - _cache_time.get(key, 0)) < CACHE_TTL:
        return _cache[key]
    value = fetcher()
    _cache[key] = value
    _cache_time[key] = now
    return value


def fetch_live_data() -> dict:
    def _fetch():
        data = {}
        data["_sources"] = {}

        try:
            boe_url = (
                "https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"
                "?csv.x=yes&Datefrom=01/Jan/2024&Dateto=now"
                "&SeriesCodes=IUMBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
            )
            resp = requests.get(boe_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text), skiprows=1, names=["DATE", "base_rate"])
            df["base_rate"] = pd.to_numeric(df["base_rate"], errors="coerce")
            data["base_rate_current"] = round(float(df["base_rate"].dropna().iloc[-1]), 2)
            data["_sources"]["base_rate"] = "live"
        except Exception:
            data["base_rate_current"] = 4.5
            data["_sources"]["base_rate"] = "fallback"

        try:
            mort_url = (
                "https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"
                "?csv.x=yes&Datefrom=01/Jan/2024&Dateto=now"
                "&SeriesCodes=IUMBV34,IUMBV42&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
            )
            resp = requests.get(mort_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text), skiprows=1, names=["DATE", "rate_2yr", "rate_5yr"])
            df["rate_2yr"] = pd.to_numeric(df["rate_2yr"], errors="coerce")
            df["rate_5yr"] = pd.to_numeric(df["rate_5yr"], errors="coerce")
            data["rate_2yr_current"] = round(float(df["rate_2yr"].dropna().iloc[-1]), 2)
            data["rate_5yr_current"] = round(float(df["rate_5yr"].dropna().iloc[-1]), 2)
            data["_sources"]["mortgage_rates"] = "live"
        except Exception:
            data["rate_2yr_current"] = 4.45
            data["rate_5yr_current"] = 4.43
            data["_sources"]["mortgage_rates"] = "fallback"

        try:
            resp = requests.get(
                "https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7g7/mm23/data",
                headers=HEADERS, timeout=10,
            )
            resp.raise_for_status()
            months = resp.json().get("months", [])
            values = [m for m in months if m.get("value") and m["value"].strip()]
            if values:
                data["cpi_current"] = round(float(values[-1]["value"]), 1)
                data["_sources"]["cpi"] = "live"
            else:
                raise ValueError("No CPI data")
        except Exception:
            data["cpi_current"] = 3.3
            data["_sources"]["cpi"] = "fallback"

        try:
            resp = requests.get(
                "https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/earningsandworkinghours/timeseries/kac3/lms/data",
                headers=HEADERS, timeout=10,
            )
            resp.raise_for_status()
            months = resp.json().get("months", [])
            values = [m for m in months if m.get("value") and m["value"].strip()]
            if values:
                data["earnings_growth_current"] = round(float(values[-1]["value"]), 1)
                data["_sources"]["earnings"] = "live"
            else:
                raise ValueError("No earnings data")
        except Exception:
            data["earnings_growth_current"] = 3.8
            data["_sources"]["earnings"] = "fallback"

        return data

    return _get_cached("live_data", _fetch)

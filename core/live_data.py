import requests
import pandas as pd
from io import StringIO
from functools import lru_cache
import time

_cache = {}
_cache_time = {}
CACHE_TTL = 3600


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
        try:
            boe_url = (
                "https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"
                "?csv.x=yes&Datefrom=01/Jan/2020&Dateto=now"
                "&SeriesCodes=IUMBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
            )
            resp = requests.get(boe_url, timeout=10)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text), skiprows=1, names=["DATE", "base_rate"])
            df["base_rate"] = pd.to_numeric(df["base_rate"], errors="coerce")
            data["base_rate_current"] = round(float(df["base_rate"].dropna().iloc[-1]), 2)
        except Exception:
            data["base_rate_current"] = 3.75

        try:
            mort_url = (
                "https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"
                "?csv.x=yes&Datefrom=01/Jan/2020&Dateto=now"
                "&SeriesCodes=IUMBV34,IUMBV42&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
            )
            resp = requests.get(mort_url, timeout=10)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text), skiprows=1, names=["DATE", "rate_2yr", "rate_5yr"])
            df["rate_2yr"] = pd.to_numeric(df["rate_2yr"], errors="coerce")
            df["rate_5yr"] = pd.to_numeric(df["rate_5yr"], errors="coerce")
            data["rate_2yr_current"] = round(float(df["rate_2yr"].dropna().iloc[-1]), 2)
            data["rate_5yr_current"] = round(float(df["rate_5yr"].dropna().iloc[-1]), 2)
        except Exception:
            data["rate_2yr_current"] = 4.2
            data["rate_5yr_current"] = 4.4

        try:
            resp = requests.get("https://api.ons.gov.uk/v1/datasets/mm23/timeseries/D7G7/data", timeout=10)
            resp.raise_for_status()
            months = resp.json().get("months", [])
            df = pd.DataFrame(months)[["date", "value"]]
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            data["cpi_current"] = round(float(df["value"].dropna().iloc[-1]), 1)
        except Exception:
            data["cpi_current"] = 3.0

        try:
            resp = requests.get("https://api.ons.gov.uk/v1/datasets/lms/timeseries/KAB9/data", timeout=10)
            resp.raise_for_status()
            months = resp.json().get("months", [])
            df = pd.DataFrame(months)[["date", "value"]]
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            data["earnings_growth_current"] = round(float(df["value"].dropna().iloc[-1]), 1)
        except Exception:
            data["earnings_growth_current"] = 5.9

        return data

    return _get_cached("live_data", _fetch)

from __future__ import annotations
import requests
import streamlit as st

SPARQL_ENDPOINT = "https://landregistry.data.gov.uk/landregistry/query"

HPI_QUERY = '''
PREFIX ukhpi: <http://landregistry.data.gov.uk/def/ukhpi/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?regionLabel ?avgPrice ?refMonth WHERE {
  ?obs ukhpi:refRegion ?region ;
       ukhpi:averagePrice ?avgPrice ;
       ukhpi:refMonth ?refMonth .
  ?region rdfs:label ?regionLabel .
  FILTER(?region IN (
    <http://landregistry.data.gov.uk/id/region/london>,
    <http://landregistry.data.gov.uk/id/region/south-east>,
    <http://landregistry.data.gov.uk/id/region/south-west>,
    <http://landregistry.data.gov.uk/id/region/east-of-england>,
    <http://landregistry.data.gov.uk/id/region/east-midlands>,
    <http://landregistry.data.gov.uk/id/region/west-midlands>,
    <http://landregistry.data.gov.uk/id/region/yorkshire-and-the-humber>,
    <http://landregistry.data.gov.uk/id/region/north-west>,
    <http://landregistry.data.gov.uk/id/region/north-east>,
    <http://landregistry.data.gov.uk/id/region/wales>,
    <http://landregistry.data.gov.uk/id/region/scotland>,
    <http://landregistry.data.gov.uk/id/region/northern-ireland>
  ))
}
ORDER BY ?regionLabel DESC(?refMonth)
'''

LABEL_MAP = {
    "London": "London",
    "South East": "South East",
    "South West": "South West",
    "East of England": "East of England",
    "East Midlands": "East Midlands",
    "West Midlands": "West Midlands",
    "Yorkshire and The Humber": "Yorkshire",
    "North West": "North West",
    "North East": "North East",
    "Wales": "Wales",
    "Scotland": "Scotland",
    "Northern Ireland": "Northern Ireland",
}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_hpi_data():
    try:
        resp = requests.post(
            SPARQL_ENDPOINT,
            data={"query": HPI_QUERY, "output": "json"},
            headers={"Accept": "application/sparql-results+json"},
            timeout=15,
        )
        if resp.status_code != 200:
            return {}

        bindings = resp.json().get("results", {}).get("bindings", [])
        latest = {}
        for b in bindings:
            label = b["regionLabel"]["value"]
            region = LABEL_MAP.get(label)
            if not region:
                continue
            month = b["refMonth"]["value"]
            price = round(float(b["avgPrice"]["value"]))
            if region not in latest or month > latest[region]["month"]:
                latest[region] = {"price": price, "month": month}

        return {r: v["price"] for r, v in latest.items()}, max(v["month"] for v in latest.values()) if latest else ""
    except Exception:
        return {}, ""


def get_live_prices():
    result = fetch_hpi_data()
    if isinstance(result, tuple) and len(result) == 2:
        return result
    return {}, ""

from fastapi import APIRouter, HTTPException
from api.models import ScoreRequest, MonteCarloRequest
from core.scoring import compute_regional_score, rank_all_regions
from core.monte_carlo import run_regional_monte_carlo
from core.live_data import fetch_live_data
from core.regions import REGIONS

router = APIRouter(prefix="/scoring", tags=["Scoring"])


@router.post("/score/{region}")
def score_region(region: str, req: ScoreRequest):
    if region not in REGIONS:
        raise HTTPException(status_code=404, detail=f"Region '{region}' not found")
    live = fetch_live_data()
    profile = {
        "salary": req.salary,
        "partner_salary": req.partner_salary,
        "budget": req.budget,
        "priorities": req.priorities,
        "job_type": req.job_type,
    }
    return compute_regional_score(region, profile, live, req.financial_weight, req.deposit_pct)


@router.post("/rank")
def rank_regions(req: ScoreRequest):
    live = fetch_live_data()
    profile = {
        "salary": req.salary,
        "partner_salary": req.partner_salary,
        "budget": req.budget,
        "priorities": req.priorities,
        "job_type": req.job_type,
    }
    return rank_all_regions(profile, live, req.financial_weight, req.deposit_pct)


@router.post("/monte-carlo")
def monte_carlo(req: MonteCarloRequest):
    invalid = [r for r in req.regions if r not in REGIONS]
    if invalid:
        raise HTTPException(status_code=404, detail=f"Regions not found: {invalid}")
    live = fetch_live_data()
    profile = {
        "salary": req.salary,
        "partner_salary": req.partner_salary,
        "budget": req.budget,
        "priorities": req.priorities,
    }
    results = run_regional_monte_carlo(
        req.regions, profile, live, req.n_sims, req.horizon, deposit_pct=req.deposit_pct
    )
    for r in results:
        results[r].pop("histogram", None)
    return results


@router.get("/regions")
def list_regions():
    return {name: data for name, data in REGIONS.items()}

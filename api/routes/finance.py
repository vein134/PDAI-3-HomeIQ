from fastapi import APIRouter, HTTPException
from api.models import TaxRequest, StampDutyRequest, BudgetRequest, AffordabilityRequest
from core.tax import compute_uk_tax, compute_stamp_duty
from core.scoring import compute_monthly_budget, compute_affordability
from core.live_data import fetch_live_data
from core.regions import REGIONS

router = APIRouter(prefix="/finance", tags=["Finance"])


@router.post("/tax")
def calculate_tax(req: TaxRequest):
    return compute_uk_tax(req.gross_salary)


@router.post("/stamp-duty")
def calculate_stamp_duty(req: StampDutyRequest):
    return {"stamp_duty": compute_stamp_duty(req.price, req.first_time_buyer)}


@router.post("/budget")
def calculate_budget(req: BudgetRequest):
    if req.region not in REGIONS:
        raise HTTPException(status_code=404, detail=f"Region '{req.region}' not found")
    return compute_monthly_budget(req.salary, req.partner_salary, req.region, req.deposit_pct, req.mortgage_rate)


@router.post("/affordability")
def calculate_affordability(req: AffordabilityRequest):
    if req.region not in REGIONS:
        raise HTTPException(status_code=404, detail=f"Region '{req.region}' not found")
    return compute_affordability(req.salary, req.partner_salary, req.region, req.deposit_pct, req.current_savings)


@router.get("/live-data")
def get_live_data():
    return fetch_live_data()

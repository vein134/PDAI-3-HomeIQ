from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List


class TaxRequest(BaseModel):
    gross_salary: float = Field(..., gt=0)


class StampDutyRequest(BaseModel):
    price: float = Field(..., gt=0)
    first_time_buyer: bool = False


class BudgetRequest(BaseModel):
    salary: float = Field(default=50000, gt=0)
    partner_salary: float = Field(default=0, ge=0)
    region: str
    deposit_pct: float = Field(default=15, ge=0, le=100)
    mortgage_rate: float = Field(default=4.5, gt=0)


class ScoreRequest(BaseModel):
    salary: float = Field(default=50000, gt=0)
    partner_salary: float = Field(default=0, ge=0)
    budget: Optional[float] = None
    priorities: list[str] = Field(default_factory=list)
    job_type: str = "hybrid"
    financial_weight: float = Field(default=50, ge=0, le=100)
    deposit_pct: float = Field(default=15, ge=0, le=100)


class AffordabilityRequest(BaseModel):
    salary: float = Field(default=50000, gt=0)
    partner_salary: float = Field(default=0, ge=0)
    region: str
    deposit_pct: float = Field(default=15, ge=0, le=100)
    current_savings: float = Field(default=0, ge=0)


class MonteCarloRequest(BaseModel):
    regions: list[str]
    salary: float = Field(default=50000, gt=0)
    partner_salary: float = Field(default=0, ge=0)
    budget: Optional[float] = None
    priorities: list[str] = Field(default_factory=list)
    n_sims: int = Field(default=1000, ge=100, le=5000)
    horizon: int = Field(default=10, ge=1, le=30)
    deposit_pct: float = Field(default=15, ge=0, le=100)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None
    user_id: int = 1
    profile: Optional[dict] = None


class ProfileCreate(BaseModel):
    username: str
    name: str = "Default"
    salary: float = 50000
    partner_salary: float = 0
    budget: Optional[float] = None
    deposit_pct: float = 15
    job_type: str = "hybrid"
    priorities: list[str] = Field(default_factory=list)
    current_savings: float = 0


class RAGQueryRequest(BaseModel):
    query: str
    n_results: int = Field(default=5, ge=1, le=20)

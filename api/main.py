from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.database import init_db
from api.routes import finance, scoring, users, chat

app = FastAPI(
    title="HomeIQ API",
    description="Smart Relocation Advisor — REST API for UK housing analysis, financial modelling, and RAG-powered advice.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(finance.router)
app.include_router(scoring.router)
app.include_router(users.router)
app.include_router(chat.router)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def root():
    return {
        "name": "HomeIQ API",
        "version": "3.0.0",
        "docs": "/docs",
        "endpoints": {
            "finance": "/finance (tax, stamp duty, budget, affordability, live data)",
            "scoring": "/scoring (region scores, rankings, Monte Carlo)",
            "users": "/users (profiles, search history, saved comparisons)",
            "chat": "/chat (RAG-powered AI advisor)",
        },
    }

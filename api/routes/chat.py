import json
import openai
from fastapi import APIRouter, HTTPException
from api.models import ChatRequest, RAGQueryRequest
from api.database import (
    save_chat_session, update_chat_session, get_chat_session,
    save_search, get_active_profile,
)
from core.regions import REGIONS, QOL_DIMS
from core.scoring import compute_regional_score, compute_monthly_budget, compute_affordability, rank_all_regions
from core.monte_carlo import run_regional_monte_carlo
from core.live_data import fetch_live_data
from rag.engine import RAGEngine
import os

router = APIRouter(prefix="/chat", tags=["AI Chat & RAG"])

_rag_engine = None


def _get_rag():
    global _rag_engine
    if _rag_engine is None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            _rag_engine = RAGEngine(api_key)
            _rag_engine.build_index()
    return _rag_engine


ADVISOR_TOOLS = [
    {"type": "function", "function": {
        "name": "compare_regions",
        "description": "Compare two UK regions with detailed financial and QoL breakdown.",
        "parameters": {"type": "object", "properties": {
            "region1": {"type": "string"}, "region2": {"type": "string"},
        }, "required": ["region1", "region2"]}
    }},
    {"type": "function", "function": {
        "name": "run_scenario",
        "description": "Run financial analysis for a specific region with custom salary/budget.",
        "parameters": {"type": "object", "properties": {
            "region": {"type": "string"},
            "salary": {"type": "number", "description": "Annual salary (GBP)"},
            "partner_salary": {"type": "number"},
        }, "required": ["region"]}
    }},
    {"type": "function", "function": {
        "name": "find_best_region",
        "description": "Find the best region for a specific priority.",
        "parameters": {"type": "object", "properties": {
            "priority": {"type": "string", "description": "One of: affordability, green_space, schools, safety, culture, healthcare, disposable_income, overall"},
        }, "required": ["priority"]}
    }},
    {"type": "function", "function": {
        "name": "run_monte_carlo_tool",
        "description": "Run Monte Carlo simulation for specific regions to compare long-term financial outcomes.",
        "parameters": {"type": "object", "properties": {
            "regions": {"type": "string", "description": "Comma-separated region names"},
            "n_simulations": {"type": "integer"},
        }, "required": ["regions"]}
    }},
    {"type": "function", "function": {
        "name": "check_affordability",
        "description": "Check mortgage affordability for a region including max borrowing, stress test, and deposit timeline.",
        "parameters": {"type": "object", "properties": {
            "region": {"type": "string"},
            "current_savings": {"type": "integer", "description": "Current savings in GBP."},
        }, "required": ["region"]}
    }},
    {"type": "function", "function": {
        "name": "search_knowledge_base",
        "description": "Search the HomeIQ knowledge base for information about UK housing, mortgages, government schemes, regional details, and relocation advice. Use this for factual questions about the UK property market.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "The search query"},
        }, "required": ["query"]}
    }},
]


def _execute_tool(name: str, arguments_json: str, profile: dict, live_data: dict, rankings: list) -> str:
    args = json.loads(arguments_json) if arguments_json else {}
    deposit_pct = profile.get("deposit_pct", 15)

    if name == "compare_regions":
        r1, r2 = args.get("region1", "London"), args.get("region2", "Yorkshire")
        results = []
        for rname in [r1, r2]:
            if rname not in REGIONS:
                return f"Region '{rname}' not found. Available: {', '.join(REGIONS.keys())}"
            s = compute_regional_score(rname, profile, live_data, deposit_pct=deposit_pct)
            b = compute_monthly_budget(
                profile.get("salary", 50000), profile.get("partner_salary", 0),
                rname, deposit_pct, live_data["rate_5yr_current"],
            )
            r = REGIONS[rname]
            results.append(
                f"{rname}: Score={s['composite']}, Financial={s['financial_score']}, QoL={s['qol_score']}, "
                f"Price=£{r['avg_price']:,}, Mortgage=£{b['monthly_mortgage']:,}/mo, "
                f"Disposable=£{b['disposable_buy']:,}/mo, Affordability={s['affordability_ratio']}x"
            )
        return "Region comparison:\n" + "\n".join(results)

    elif name == "run_scenario":
        rname = args.get("region", "London")
        if rname not in REGIONS:
            return f"Region '{rname}' not found."
        sal = args.get("salary", profile.get("salary", 50000))
        psal = args.get("partner_salary", profile.get("partner_salary", 0))
        custom_profile = {**profile, "salary": sal, "partner_salary": psal}
        s = compute_regional_score(rname, custom_profile, live_data, deposit_pct=deposit_pct)
        b = compute_monthly_budget(sal, psal, rname, deposit_pct, live_data["rate_5yr_current"])
        return (
            f"{rname} scenario (Salary: £{sal:,}):\n"
            f"Score: {s['composite']}, Affordability: {s['affordability_ratio']}x\n"
            f"Mortgage: £{b['monthly_mortgage']:,}/mo, Rent: £{b['monthly_rent']:,}/mo\n"
            f"Disposable (buy): £{b['disposable_buy']:,}/mo, (rent): £{b['disposable_rent']:,}/mo"
        )

    elif name == "find_best_region":
        priority = args.get("priority", "overall")
        if priority == "overall":
            return f"Best overall: {rankings[0]['region']} (score {rankings[0]['composite']})"
        elif priority == "affordability":
            best = min(rankings, key=lambda x: x["affordability_ratio"])
            return f"Most affordable: {best['region']} ({best['affordability_ratio']}x income)"
        elif priority == "disposable_income":
            best = max(rankings, key=lambda x: x["disposable_monthly"])
            return f"Best disposable income: {best['region']} (£{best['disposable_monthly']:,}/mo)"
        elif priority in QOL_DIMS:
            best_r = max(REGIONS.items(), key=lambda x: x[1].get(priority, 0))
            return f"Best for {priority.replace('_', ' ')}: {best_r[0]} (score: {best_r[1][priority]})"
        return f"Unknown priority: {priority}"

    elif name == "run_monte_carlo_tool":
        regs = [r.strip() for r in args.get("regions", "London,Yorkshire").split(",")]
        regs = [r for r in regs if r in REGIONS]
        if len(regs) < 2:
            return "Need at least 2 valid regions."
        n = min(2000, max(100, args.get("n_simulations", 500)))
        mc = run_regional_monte_carlo(regs, profile, live_data, n, deposit_pct=deposit_pct)
        lines = [f"Monte Carlo ({n} sims, 10yr):"]
        for rname in sorted(regs, key=lambda r: mc[r]["prob_best"], reverse=True):
            m = mc[rname]
            lines.append(
                f"- {rname}: P(Wins)={m['prob_best']*100:.0f}%, Median=£{m['p50']:,.0f}, "
                f"P10=£{m['p10']:,.0f}, P90=£{m['p90']:,.0f}"
            )
        return "\n".join(lines)

    elif name == "check_affordability":
        rname = args.get("region", rankings[0]["region"] if rankings else "London")
        if rname not in REGIONS:
            return f"Region '{rname}' not found."
        sav = args.get("current_savings", profile.get("current_savings", 20000))
        af = compute_affordability(
            profile.get("salary", 50000), profile.get("partner_salary", 0),
            rname, deposit_pct, sav,
        )
        return (
            f"Affordability for {rname}:\n"
            f"- Max borrowing (4.5x): £{af['max_borrowing']:,} — {'Approved' if af['can_borrow'] else 'EXCEEDS LIMIT'}\n"
            f"- Loan needed: £{af['loan_needed']:,}\n"
            f"- Total upfront: £{af['total_upfront']:,} (deposit £{af['deposit']:,} + stamp £{af['stamp']:,} + fees)\n"
            f"- Savings shortfall: £{af['shortfall']:,}\n"
            f"- Months to save: {af['months_to_save']}"
        )

    elif name == "search_knowledge_base":
        rag = _get_rag()
        if not rag:
            return "Knowledge base not available (no API key configured)."
        query = args.get("query", "")
        results = rag.query(query, n_results=4)
        if not results:
            return "No relevant information found in the knowledge base."
        parts = []
        for r in results:
            parts.append(f"[{r['source']} — {r['section']}] (relevance: {r['similarity']:.2f})\n{r['text']}")
        return "\n\n---\n\n".join(parts)

    return f"Unknown tool: {name}"


@router.post("/message")
def chat_message(req: ChatRequest):
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    live_data = fetch_live_data()
    profile = req.profile or {
        "salary": 50000, "partner_salary": 0, "deposit_pct": 15,
        "priorities": [], "job_type": "hybrid",
    }
    rankings = rank_all_regions(profile, live_data, deposit_pct=profile.get("deposit_pct", 15))

    rag = _get_rag()
    rag_context = ""
    if rag:
        rag_context = rag.get_context_for_chat(req.message, n_results=3)

    system_ctx = f"""You are HomeIQ's Smart Relocation Advisor — an expert on UK regions, property, and personal finance.
You have access to a RAG knowledge base with detailed UK housing guides. Use the search_knowledge_base tool for
factual questions about mortgages, government schemes, regional details, and relocation advice.
Use computation tools for numerical questions — do NOT guess numbers.

USER PROFILE: Salary £{profile.get('salary', 50000):,}, Partner £{profile.get('partner_salary', 0):,},
{profile.get('job_type', 'hybrid')} worker, Priorities: {', '.join(profile.get('priorities', []))},
Deposit: {profile.get('deposit_pct', 15)}%

TOP RANKED REGIONS:
{chr(10).join(f"- {r['region']}: Score {r['composite']}, Financial {r['financial_score']}, QoL {r['qol_score']}" for r in rankings[:5])}

LIVE MARKET: BoE rate {live_data['base_rate_current']}%, 5yr fixed {live_data['rate_5yr_current']}%, CPI {live_data['cpi_current']}%

RELEVANT KNOWLEDGE BASE CONTEXT:
{rag_context if rag_context else 'No pre-fetched context available. Use search_knowledge_base tool for detailed information.'}"""

    messages_history = []
    if req.session_id:
        session = get_chat_session(req.session_id)
        if session:
            messages_history = session.get("messages", [])

    messages_history.append({"role": "user", "content": req.message})

    api_messages = [{"role": "system", "content": system_ctx}] + [
        {"role": m["role"], "content": m["content"]}
        for m in messages_history if m["role"] in ("user", "assistant")
    ]

    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o", messages=api_messages, tools=ADVISOR_TOOLS,
        tool_choice="auto", max_tokens=800,
    )

    tool_calls_log = []
    iterations = 0
    while response.choices[0].message.tool_calls and iterations < 3:
        tool_calls = response.choices[0].message.tool_calls
        api_messages.append(response.choices[0].message)
        for tc in tool_calls:
            result = _execute_tool(tc.function.name, tc.function.arguments, profile, live_data, rankings)
            api_messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
            tool_calls_log.append({"tool": tc.function.name, "args": tc.function.arguments, "result": result})
        response = client.chat.completions.create(
            model="gpt-4o", messages=api_messages, tools=ADVISOR_TOOLS,
            tool_choice="auto", max_tokens=800,
        )
        iterations += 1

    reply = response.choices[0].message.content or "Analysis complete."
    messages_history.append({"role": "assistant", "content": reply})

    session_id = req.session_id
    if session_id:
        update_chat_session(session_id, messages_history)
    else:
        title = req.message[:50] + ("..." if len(req.message) > 50 else "")
        session_id = save_chat_session(req.user_id, title, messages_history)

    rag_sources = []
    if rag_context:
        for line in rag_context.split("---"):
            if "[Source:" in line:
                start = line.index("[Source:") + 8
                end = line.index("]", start)
                rag_sources.append(line[start:end].strip())

    return {
        "reply": reply,
        "session_id": session_id,
        "tool_calls": tool_calls_log,
        "rag_sources": rag_sources,
    }


@router.post("/rag/query")
def rag_query(req: RAGQueryRequest):
    rag = _get_rag()
    if not rag:
        raise HTTPException(status_code=500, detail="RAG engine not available")
    results = rag.query(req.query, req.n_results)
    return {"results": results, "stats": rag.stats}


@router.post("/rag/rebuild")
def rag_rebuild():
    rag = _get_rag()
    if not rag:
        raise HTTPException(status_code=500, detail="RAG engine not available")
    rag.build_index(force_rebuild=True)
    return {"status": "rebuilt", "stats": rag.stats}


@router.get("/rag/stats")
def rag_stats():
    rag = _get_rag()
    if not rag:
        return {"total_chunks": 0, "total_documents": 0, "index_built": False}
    return rag.stats

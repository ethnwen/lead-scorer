"""FastAPI app exposing the scorer over HTTP.

Endpoints:
  GET  /health         liveness check
  GET  /weights        current scoring weights and thresholds (transparency)
  GET  /config         the full scoring configuration
  POST /score          score a single lead
  POST /score/batch    score many leads at once, best first

Run it with:
    python -m uvicorn scorer.api:app --reload
Then open http://127.0.0.1:8000/docs to try the endpoints.
"""

from typing import Literal

from fastapi import FastAPI, Query

from .config import ScoringConfig
from .models import Lead, ScoredLead
from .rules import score_lead, score_leads

app = FastAPI(title="Lead Scorer", version="0.2.0")

CONFIG = ScoringConfig()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/weights")
def weights() -> dict:
    """Expose the scoring weights and tier cutoffs so sales teams can see the rules."""
    return {
        "axis_weights": CONFIG.axis_weights,
        "fit_weights": CONFIG.fit_weights,
        "intent_weights": CONFIG.intent_weights,
        "thresholds": {"hot": CONFIG.hot_threshold, "warm": CONFIG.warm_threshold},
        "max_total": 100,
    }


@app.get("/config")
def config() -> dict:
    """The full scoring configuration, including industry fit and curve settings."""
    return CONFIG.model_dump()


@app.post("/score", response_model=ScoredLead)
def score_single(lead: Lead) -> ScoredLead:
    return score_lead(lead, CONFIG)


@app.post("/score/batch", response_model=list[ScoredLead])
def score_batch(
    leads: list[Lead],
    tier: Literal["hot", "warm", "cold"] | None = Query(
        default=None, description="Only return leads in this tier"
    ),
    top: int | None = Query(default=None, ge=1, description="Only return the top N leads"),
) -> list[ScoredLead]:
    # Best leads first: this is what a sales rep actually wants to see.
    scored = score_leads(leads, CONFIG)
    if tier:
        scored = [s for s in scored if s.tier == tier]
    if top:
        scored = scored[:top]
    return scored

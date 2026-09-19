"""FastAPI app exposing the scorer over HTTP.

Endpoints:
  GET  /health         -> liveness check
  POST /score          -> score a single lead
  POST /score/batch    -> score many leads at once
  GET  /weights        -> show the current scoring config (transparency)
"""

from fastapi import FastAPI

from .models import Lead, ScoredLead
from .rules import WEIGHTS, score_lead

app = FastAPI(title="Lead Scorer", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/weights")
def weights() -> dict:
    """Expose the scoring config so sales teams can see and tune the rules."""
    return {"weights": WEIGHTS, "max_total": sum(WEIGHTS.values())}


@app.post("/score", response_model=ScoredLead)
def score_single(lead: Lead) -> ScoredLead:
    return score_lead(lead)


@app.post("/score/batch", response_model=list[ScoredLead])
def score_batch(leads: list[Lead]) -> list[ScoredLead]:
    # Sort hottest-first — this is what a rep actually wants to see.
    return sorted((score_lead(l) for l in leads), key=lambda s: s.score, reverse=True)

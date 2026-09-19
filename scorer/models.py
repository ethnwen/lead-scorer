"""Data models for the lead scoring engine.

We keep these as plain Pydantic models so the same definitions are used by
the API, the CLI, and the tests — one source of truth for what a "lead" is.
"""

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """A prospective customer, with the signals we score on."""

    company: str
    employees: int = Field(ge=0, description="Headcount")
    industry: str = Field(description="e.g. logistics, manufacturing, retail")
    annual_revenue_musd: float = Field(ge=0, description="Annual revenue in $ millions")
    automation_readiness: int = Field(
        ge=1, le=5, description="1 = manual everything, 5 = automation-first culture"
    )
    # Engagement signals
    emails_opened: int = Field(default=0, ge=0)
    website_visits: int = Field(default=0, ge=0)
    replied: bool = False


class ScoredLead(BaseModel):
    """A Lead after scoring, with the full breakdown for explainability."""

    company: str
    score: int = Field(ge=0, le=100)
    tier: str = Field(description="hot | warm | cold")
    breakdown: dict[str, int]

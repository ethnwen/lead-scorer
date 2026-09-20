"""Data models for the lead scoring engine.

We keep these as plain Pydantic models so the same definitions are used by
the API, the CLI, and the tests. One source of truth for what a "lead" is.
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

    # Optional deal-readiness signals. Leave them out when unknown: the score
    # is then based on the signals that are available, and the result reports
    # a lower confidence instead of guessing.
    demo_requested: bool | None = None
    days_since_last_activity: int | None = Field(default=None, ge=0)
    contact_seniority: str | None = Field(
        default=None, description="c-level, vp, director, manager, or individual"
    )
    budget_confirmed: bool | None = None
    timeline_months: int | None = Field(
        default=None, ge=0, description="Expected months until a buying decision"
    )


class ScoredLead(BaseModel):
    """A Lead after scoring, with the full breakdown for explainability."""

    company: str
    score: int = Field(ge=0, le=100)
    tier: str = Field(description="hot | warm | cold")
    fit_score: int = Field(default=0, ge=0, le=100, description="How closely the company matches the ideal customer")
    intent_score: int = Field(default=0, ge=0, le=100, description="How likely the lead is to buy soon")
    confidence: float = Field(default=1.0, ge=0, le=1, description="Share of signals that were available")
    next_action: str = Field(default="", description="Recommended next step")
    breakdown: dict[str, float] = Field(
        default_factory=dict, description="Points each signal added to the final score"
    )
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)

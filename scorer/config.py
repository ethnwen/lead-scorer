"""Scoring configuration.

Every number that controls the score lives here, so the model can be tuned
without editing the scoring logic.

To use your own settings, dump the defaults to a file, edit it, and pass it in:

    python -m scorer.cli --dump-config > my_config.json
    python -m scorer.cli data/sample_leads_large.csv --config my_config.json
"""

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

FIT_SIGNALS = ("industry_fit", "company_size", "revenue", "automation_readiness")
INTENT_SIGNALS = (
    "replied",
    "demo_requested",
    "email_engagement",
    "web_engagement",
    "recency",
    "timeline",
    "contact_seniority",
    "budget_confirmed",
)


class ScoringConfig(BaseModel):
    """All tunable settings, with sensible defaults for an AI automation
    platform selling into logistics, manufacturing, and similar industries."""

    # Share of the final score that comes from each axis. Must sum to 1.
    axis_weights: dict[str, float] = Field(
        default_factory=lambda: {"fit": 0.5, "intent": 0.5}
    )

    # Relative importance of each signal inside its axis. Only the ratios
    # matter, because each axis is rescaled to a 0-100 range.
    fit_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "industry_fit": 30,
            "company_size": 25,
            "revenue": 15,
            "automation_readiness": 30,
        }
    )
    intent_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "replied": 15,
            "demo_requested": 15,
            "email_engagement": 10,
            "web_engagement": 10,
            "recency": 15,
            "timeline": 10,
            "contact_seniority": 10,
            "budget_confirmed": 15,
        }
    )

    # How well each industry matches your ideal customer profile (0 to 1).
    # Anything not listed falls back to the "other" entry.
    industry_fit: dict[str, float] = Field(
        default_factory=lambda: {
            "logistics": 1.0,
            "transportation": 1.0,
            "manufacturing": 0.9,
            "warehousing": 0.9,
            "supply chain": 0.85,
            "finance": 0.7,
            "healthcare": 0.6,
            "retail": 0.5,
            "software": 0.4,
            "other": 0.3,
        }
    )

    # Company size: full credit inside the plateau (in employees), then a
    # smooth decay on each side. Sigma controls how fast credit falls off,
    # measured in orders of magnitude (log10) of headcount.
    size_plateau_low: int = 50
    size_plateau_high: int = 300
    size_sigma_low: float = 0.5
    size_sigma_high: float = 0.7

    # Revenue (in $ millions) at which revenue credit reaches its maximum.
    revenue_cap_musd: float = 50.0

    # Engagement curves. Saturation is the count where credit reaches about
    # 63 percent, so early activity counts most and extra activity counts less.
    email_saturation: float = 3.0
    web_saturation: float = 4.0

    # Recency: credit halves every this many days without activity.
    recency_halflife_days: float = 30.0
    stale_after_days: int = 90

    # Buying timeline as (months_at_most, credit) pairs, plus a default for
    # anything slower than the last pair.
    timeline_scores: list[tuple[float, float]] = Field(
        default_factory=lambda: [(1, 1.0), (3, 0.8), (6, 0.5), (12, 0.25)]
    )
    timeline_default: float = 0.1

    # Decision-maker seniority (0 to 1). Unlisted titles use "other".
    seniority_scores: dict[str, float] = Field(
        default_factory=lambda: {
            "c-level": 1.0,
            "vp": 0.9,
            "director": 0.8,
            "manager": 0.5,
            "individual": 0.25,
            "other": 0.25,
        }
    )

    # Tier cutoffs on the final 0-100 score.
    hot_threshold: int = 75
    warm_threshold: int = 40
    # Fit and intent scores at or above this count as "high". It picks the
    # recommended next step, and a lead only stays "hot" if BOTH axes are high.
    quadrant_split: int = 55
    # Flag a lead when less than this share of signals is available.
    low_confidence_below: float = 0.5

    @model_validator(mode="after")
    def _validate(self) -> "ScoringConfig":
        if set(self.axis_weights) != {"fit", "intent"}:
            raise ValueError("axis_weights must have exactly the keys 'fit' and 'intent'")
        if any(w < 0 for w in self.axis_weights.values()):
            raise ValueError("axis_weights cannot be negative")
        if abs(sum(self.axis_weights.values()) - 1.0) > 1e-6:
            raise ValueError("axis_weights must add up to 1")

        for label, weights, allowed in (
            ("fit_weights", self.fit_weights, FIT_SIGNALS),
            ("intent_weights", self.intent_weights, INTENT_SIGNALS),
        ):
            unknown = set(weights) - set(allowed)
            if unknown:
                raise ValueError(
                    f"{label} has unknown signals {sorted(unknown)}. Allowed: {list(allowed)}"
                )
            if any(w < 0 for w in weights.values()):
                raise ValueError(f"{label} cannot contain negative weights")
            if sum(weights.values()) <= 0:
                raise ValueError(f"{label} must have at least one positive weight")

        for label, table in (
            ("industry_fit", self.industry_fit),
            ("seniority_scores", self.seniority_scores),
        ):
            if any(not 0 <= v <= 1 for v in table.values()):
                raise ValueError(f"{label} values must be between 0 and 1")

        if not 0 <= self.warm_threshold < self.hot_threshold <= 100:
            raise ValueError("thresholds must satisfy 0 <= warm < hot <= 100")
        if min(self.size_sigma_low, self.size_sigma_high) <= 0:
            raise ValueError("size sigmas must be positive")
        if self.size_plateau_low <= 0 or self.size_plateau_low > self.size_plateau_high:
            raise ValueError("size plateau must satisfy 0 < low <= high")
        if min(self.email_saturation, self.web_saturation, self.recency_halflife_days) <= 0:
            raise ValueError("saturation and half-life values must be positive")
        return self

    @classmethod
    def from_json(cls, path: str | Path) -> "ScoringConfig":
        """Load settings from a JSON file. Missing settings keep their defaults."""
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))

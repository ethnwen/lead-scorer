"""The scoring engine.

Pure functions, no file or network access. This is the part of the project
that maps directly to real sales-operations logic.

How a lead is scored
--------------------
Every lead gets two sub-scores on a 0 to 100 scale:

  FIT     Does this company look like our ideal customer?
          Signals: industry, company size, revenue, automation readiness.

  INTENT  Are they likely to buy soon?
          Signals: replies, demo requests, email and website engagement,
          recent activity, buying timeline, contact seniority, budget.

The final score is a weighted blend of the two. This mirrors the classic
BANT qualification framework (Budget, Authority, Need, Timeline).

Design choices worth knowing
----------------------------
* Smooth curves instead of step functions, so 49 and 51 employees are
  scored almost the same instead of jumping at a cutoff.
* Missing optional data never counts as zero. Each axis is rescaled over
  the signals that are actually known, and the result reports a confidence
  value showing how much data the score is based on.
* A lead can only be "hot" if BOTH fit and intent are high. A perfect
  company that never engages, or an engaged lead that is a poor fit, is
  held at "warm".
* Every point is traceable: the result lists each signal's contribution,
  the biggest strengths, and the biggest gaps.
"""

import math
from dataclasses import dataclass

from .config import ScoringConfig
from .models import Lead, ScoredLead

DEFAULT_CONFIG = ScoringConfig()

SIGNAL_LABELS = {
    "industry_fit": "Industry fit",
    "company_size": "Company size",
    "revenue": "Revenue",
    "automation_readiness": "Automation readiness",
    "replied": "Replied to outreach",
    "demo_requested": "Demo requested",
    "email_engagement": "Email engagement",
    "web_engagement": "Website engagement",
    "recency": "Recent activity",
    "timeline": "Buying timeline",
    "contact_seniority": "Contact seniority",
    "budget_confirmed": "Budget confirmed",
}

ACTION_GUIDANCE = {
    "Priority outreach": "Strong fit and strong buying signals. Contact within one business day.",
    "Follow up soon": "Good fit and good buying signals, just short of top priority. Follow up within the week.",
    "Nurture": "Strong fit but little buying activity so far. Keep warm with relevant content and check back.",
    "Qualify first": "Very engaged but a weaker fit. Confirm need and budget before investing sales time.",
    "Low priority": "Weak fit and weak signals. Automated nurture only.",
}

SENIORITY_ALIASES = {
    "c-suite": "c-level",
    "cxo": "c-level",
    "ceo": "c-level",
    "cfo": "c-level",
    "coo": "c-level",
    "cto": "c-level",
    "cio": "c-level",
    "owner": "c-level",
    "founder": "c-level",
    "president": "c-level",
    "vice-president": "vp",
    "svp": "vp",
    "evp": "vp",
    "head": "director",
    "senior-manager": "manager",
    "ic": "individual",
    "analyst": "individual",
    "associate": "individual",
}


# ---------------------------------------------------------------------------
# Individual signal curves. Each returns a value from 0 (worst) to 1 (best).
# ---------------------------------------------------------------------------

def size_value(employees: int, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    """Mid-market is the sweet spot: big enough to have budget and pain,
    small enough to move fast. Credit is full inside the plateau and decays
    smoothly on both sides. Very large enterprises decay more slowly than
    tiny companies because they still have budget, just slower sales cycles."""
    if employees <= 0:
        return 0.0
    x = math.log10(employees)
    low = math.log10(cfg.size_plateau_low)
    high = math.log10(cfg.size_plateau_high)
    if x < low:
        distance = (low - x) / cfg.size_sigma_low
    elif x > high:
        distance = (x - high) / cfg.size_sigma_high
    else:
        return 1.0
    return math.exp(-0.5 * distance * distance)


def industry_value(industry: str, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    table = cfg.industry_fit
    return table.get(industry.strip().lower(), table.get("other", 0.3))


def revenue_value(revenue_musd: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    """Log scale, so going from $1M to $10M matters more than $40M to $50M."""
    if revenue_musd <= 0:
        return 0.0
    value = math.log10(revenue_musd + 1) / math.log10(cfg.revenue_cap_musd + 1)
    return min(value, 1.0)


def readiness_value(readiness: int) -> float:
    """Maps the 1 to 5 readiness rating onto 0 to 1."""
    return (readiness - 1) / 4


def email_value(opens: int, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    return 1 - math.exp(-opens / cfg.email_saturation)


def web_value(visits: int, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    return 1 - math.exp(-visits / cfg.web_saturation)


def recency_value(days: int, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    """Interest fades: credit halves every recency_halflife_days."""
    return 0.5 ** (days / cfg.recency_halflife_days)


def timeline_value(months: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    for limit, credit in sorted(cfg.timeline_scores):
        if months <= limit:
            return credit
    return cfg.timeline_default


def _normalize_seniority(label: str) -> str:
    key = label.strip().lower().replace("_", "-").replace(" ", "-")
    return SENIORITY_ALIASES.get(key, key)


def seniority_value(label: str, cfg: ScoringConfig = DEFAULT_CONFIG) -> float:
    table = cfg.seniority_scores
    return table.get(_normalize_seniority(label), table.get("other", 0.25))


# ---------------------------------------------------------------------------
# Turning a lead into signals
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    name: str
    axis: str
    value: float | None  # None means the data was not provided
    note: str


@dataclass
class Contribution:
    name: str
    axis: str
    value: float
    points: float
    max_points: float
    note: str


def fit_signals(lead: Lead, cfg: ScoringConfig = DEFAULT_CONFIG) -> list[Signal]:
    if lead.employees <= 0:
        size_note = "no headcount reported"
    elif lead.employees < cfg.size_plateau_low:
        size_note = f"{lead.employees:,} employees, below the ideal range (smaller budgets)"
    elif lead.employees > cfg.size_plateau_high:
        size_note = f"{lead.employees:,} employees, above the ideal range (slower sales cycles)"
    else:
        size_note = f"{lead.employees:,} employees, inside the ideal range"

    industry_credit = industry_value(lead.industry, cfg)
    listed = lead.industry.strip().lower() in cfg.industry_fit
    industry_note = f"{lead.industry} is a {industry_credit:.0%} match to the ideal customer profile"
    if not listed:
        industry_note += " (industry not listed, using the default)"

    return [
        Signal("industry_fit", "fit", industry_credit, industry_note),
        Signal("company_size", "fit", size_value(lead.employees, cfg), size_note),
        Signal(
            "revenue",
            "fit",
            revenue_value(lead.annual_revenue_musd, cfg),
            f"${lead.annual_revenue_musd:g}M annual revenue",
        ),
        Signal(
            "automation_readiness",
            "fit",
            readiness_value(lead.automation_readiness),
            f"automation readiness {lead.automation_readiness} out of 5",
        ),
    ]


def intent_signals(lead: Lead, cfg: ScoringConfig = DEFAULT_CONFIG) -> list[Signal]:
    signals = [
        Signal(
            "replied",
            "intent",
            1.0 if lead.replied else 0.0,
            "replied to outreach" if lead.replied else "has not replied",
        ),
        Signal(
            "demo_requested",
            "intent",
            None if lead.demo_requested is None else float(lead.demo_requested),
            "requested a demo" if lead.demo_requested else "no demo requested",
        ),
        Signal(
            "email_engagement",
            "intent",
            email_value(lead.emails_opened, cfg),
            f"{lead.emails_opened} email opens",
        ),
        Signal(
            "web_engagement",
            "intent",
            web_value(lead.website_visits, cfg),
            f"{lead.website_visits} website visits",
        ),
    ]

    days = lead.days_since_last_activity
    signals.append(
        Signal(
            "recency",
            "intent",
            None if days is None else recency_value(days, cfg),
            f"last activity {days} days ago",
        )
    )

    months = lead.timeline_months
    signals.append(
        Signal(
            "timeline",
            "intent",
            None if months is None else timeline_value(months, cfg),
            f"expects to decide within {months} months",
        )
    )

    seniority = lead.contact_seniority
    signals.append(
        Signal(
            "contact_seniority",
            "intent",
            None if not seniority else seniority_value(seniority, cfg),
            f"main contact level: {seniority}",
        )
    )

    budget = lead.budget_confirmed
    signals.append(
        Signal(
            "budget_confirmed",
            "intent",
            None if budget is None else float(budget),
            "budget confirmed" if budget else "budget not confirmed",
        )
    )
    return signals


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _weights_for(axis: str, cfg: ScoringConfig) -> dict[str, float]:
    return cfg.fit_weights if axis == "fit" else cfg.intent_weights


def _score_axis(signals: list[Signal], axis: str, cfg: ScoringConfig):
    """Return (axis score 0-100, coverage 0-1, known signals with weights)."""
    weights = _weights_for(axis, cfg)
    active = [(s, weights.get(s.name, 0.0)) for s in signals if weights.get(s.name, 0.0) > 0]
    total_weight = sum(w for _, w in active)
    known = [(s, w) for s, w in active if s.value is not None]
    known_weight = sum(w for _, w in known)
    if known_weight == 0:
        return 0.0, 0.0, []
    score = 100.0 * sum(w * s.value for s, w in known) / known_weight
    return score, known_weight / total_weight, known


def assign_tier(score: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> str:
    if score >= cfg.hot_threshold:
        return "hot"
    if score >= cfg.warm_threshold:
        return "warm"
    return "cold"


def recommend_action(
    fit: float, intent: float, score: float, cfg: ScoringConfig = DEFAULT_CONFIG
) -> str:
    high_fit = fit >= cfg.quadrant_split
    high_intent = intent >= cfg.quadrant_split
    if high_fit and high_intent:
        return "Priority outreach" if score >= cfg.hot_threshold else "Follow up soon"
    if high_fit:
        return "Nurture"
    if high_intent:
        return "Qualify first"
    return "Low priority"


def score_lead(lead: Lead, config: ScoringConfig | None = None) -> ScoredLead:
    """Score a single lead and return the result with a full breakdown,
    so a sales rep can always see why a lead got its score."""
    cfg = config or DEFAULT_CONFIG
    aw = cfg.axis_weights

    fit, fit_cov, fit_known = _score_axis(fit_signals(lead, cfg), "fit", cfg)
    intent_all = intent_signals(lead, cfg)
    intent, intent_cov, intent_known = _score_axis(intent_all, "intent", cfg)

    total = aw["fit"] * fit + aw["intent"] * intent
    confidence = aw["fit"] * fit_cov + aw["intent"] * intent_cov

    # Work out how many points each signal added to the final score.
    contributions: list[Contribution] = []
    for axis, known in (("fit", fit_known), ("intent", intent_known)):
        known_weight = sum(w for _, w in known)
        for signal, weight in known:
            max_points = aw[axis] * 100.0 * weight / known_weight
            contributions.append(
                Contribution(
                    signal.name, axis, signal.value, max_points * signal.value, max_points, signal.note
                )
            )

    strengths = sorted((c for c in contributions if c.value >= 0.6), key=lambda c: c.points, reverse=True)[:3]
    gaps = sorted(
        (c for c in contributions if c.value < 0.4),
        key=lambda c: c.max_points - c.points,
        reverse=True,
    )[:3]

    score = int(min(max(total, 0.0), 100.0) + 0.5)
    tier = assign_tier(score, cfg)

    flags: list[str] = []
    if tier == "hot" and min(fit, intent) < cfg.quadrant_split:
        weaker = "fit" if fit < intent else "intent"
        tier = "warm"
        flags.append(f"Held at warm: {weaker} score is only {round(min(fit, intent))}")

    days = lead.days_since_last_activity
    if days is not None and days >= cfg.stale_after_days:
        flags.append(f"Stale: no activity in {days} days")
    if confidence < cfg.low_confidence_below:
        flags.append(f"Limited data: only {confidence:.0%} of signals available")

    missing = [
        s.name
        for s in intent_all
        if s.value is None and cfg.intent_weights.get(s.name, 0.0) > 0
    ]

    return ScoredLead(
        company=lead.company,
        score=score,
        tier=tier,
        fit_score=int(fit + 0.5),
        intent_score=int(intent + 0.5),
        confidence=round(confidence, 2),
        next_action=recommend_action(fit, intent, score, cfg),
        breakdown={c.name: round(c.points, 1) for c in contributions},
        strengths=[f"{SIGNAL_LABELS[c.name]} (+{c.points:.1f}): {c.note}" for c in strengths],
        gaps=[
            f"{SIGNAL_LABELS[c.name]} (-{c.max_points - c.points:.1f} pts lost): {c.note}"
            for c in gaps
        ],
        flags=flags,
        missing_signals=missing,
    )


def score_leads(leads: list[Lead], config: ScoringConfig | None = None) -> list[ScoredLead]:
    """Score many leads and return them ranked from best to worst."""
    scored = [score_lead(lead, config) for lead in leads]
    return sorted(scored, key=lambda s: (-s.score, -s.fit_score, s.company))

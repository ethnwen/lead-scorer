"""The scoring engine.

Pure functions, no I/O — this is the heart of the project and the part
that maps directly to real sales-ops logic:

  score = sum of weighted sub-scores, one per signal dimension.

Each sub-score function returns points on a fixed scale, so the weights
below always sum to 100 and the total is directly interpretable.
"""

from .models import Lead, ScoredLead

# Maximum points available per dimension. Sum must equal 100.
WEIGHTS = {
    "company_size": 15,
    "industry_fit": 20,
    "automation_readiness": 25,
    "revenue": 15,
    "engagement": 25,
}

# Industries this product (an AI automation platform) sells best into,
# ranked. Adjust to your own ideal customer profile (ICP).
INDUSTRY_FIT = {
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


def score_company_size(employees: int, max_points: int) -> int:
    """Mid-market is the sweet spot: big enough to have budget and pain,
    small enough to move fast. Very large enterprises get slightly fewer
    points because sales cycles are slow."""
    if employees <= 0:
        return 0
    if employees < 11:
        return int(max_points * 0.3)   # tiny, low budget
    if employees < 51:
        return int(max_points * 0.6)
    if employees < 201:
        return max_points              # ideal
    if employees < 1001:
        return int(max_points * 0.8)
    return int(max_points * 0.6)       # enterprise, slower cycle


def score_industry(industry: str, max_points: int) -> int:
    fit = INDUSTRY_FIT.get(industry.strip().lower(), INDUSTRY_FIT["other"])
    return round(max_points * fit)


def score_automation_readiness(readiness: int, max_points: int) -> int:
    """The strongest single signal: a company that knows it has manual-work
    pain AND is open to fixing it converts far better than a perfect-fit
    company that is not ready to change."""
    return round(max_points * (readiness - 1) / 4)  # map 1-5 to 0-max


def score_revenue(revenue_musd: float, max_points: int) -> int:
    if revenue_musd >= 50:
        return max_points
    if revenue_musd >= 10:
        return int(max_points * 0.8)
    if revenue_musd >= 1:
        return int(max_points * 0.5)
    return int(max_points * 0.2)


def score_engagement(lead: Lead, max_points: int) -> int:
    """Behavioral signals: opens, site visits, and replies. Replies are the
    strongest — a reply usually means a real conversation has started."""
    points = min(lead.emails_opened, 5) * 2          # up to 10
    points += min(lead.website_visits, 5) * 1        # up to 5
    if lead.replied:
        points += 10                                 # conversation started
    return min(points, max_points)


def assign_tier(score: int) -> str:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def score_lead(lead: Lead) -> ScoredLead:
    """Score a single lead and return the result with a full breakdown,
    so a sales rep can always see *why* a lead got its score."""
    breakdown = {
        "company_size": score_company_size(lead.employees, WEIGHTS["company_size"]),
        "industry_fit": score_industry(lead.industry, WEIGHTS["industry_fit"]),
        "automation_readiness": score_automation_readiness(
            lead.automation_readiness, WEIGHTS["automation_readiness"]
        ),
        "revenue": score_revenue(lead.annual_revenue_musd, WEIGHTS["revenue"]),
        "engagement": score_engagement(lead, WEIGHTS["engagement"]),
    }
    total = min(sum(breakdown.values()), 100)
    return ScoredLead(
        company=lead.company,
        score=total,
        tier=assign_tier(total),
        breakdown=breakdown,
    )

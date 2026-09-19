"""Unit tests for the scoring engine.

Run with: pytest -v
"""

from scorer.models import Lead
from scorer.rules import WEIGHTS, assign_tier, score_lead


def make_lead(**overrides) -> Lead:
    base = dict(
        company="TestCo",
        employees=100,
        industry="logistics",
        annual_revenue_musd=30.0,
        automation_readiness=4,
        emails_opened=4,
        website_visits=3,
        replied=True,
    )
    base.update(overrides)
    return Lead(**base)


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_score_always_within_bounds():
    strong = make_lead()
    weak = make_lead(employees=2, industry="software", annual_revenue_musd=0.2,
                     automation_readiness=1, emails_opened=0, website_visits=0,
                     replied=False)
    for s in (score_lead(strong), score_lead(weak)):
        assert 0 <= s.score <= 100


def test_engaged_ideal_customer_is_hot():
    assert score_lead(make_lead()).tier == "hot"


def test_unengaged_poor_fit_is_cold():
    lead = make_lead(employees=2, industry="software", annual_revenue_musd=0.2,
                     automation_readiness=1, emails_opened=0, website_visits=0,
                     replied=False)
    assert score_lead(lead).tier == "cold"


def test_reply_boosts_score():
    without = score_lead(make_lead(replied=False, emails_opened=0, website_visits=0))
    with_reply = score_lead(make_lead(replied=True, emails_opened=0, website_visits=0))
    assert with_reply.score > without.score


def test_unknown_industry_gets_default_fit():
    lead = make_lead(industry=" asteroid mining ")
    scored = score_lead(lead)
    assert scored.breakdown["industry_fit"] == round(WEIGHTS["industry_fit"] * 0.3)


def test_breakdown_matches_total():
    scored = score_lead(make_lead())
    assert sum(scored.breakdown.values()) == scored.score


def test_tier_boundaries():
    assert assign_tier(70) == "hot"
    assert assign_tier(40) == "warm"
    assert assign_tier(39) == "cold"

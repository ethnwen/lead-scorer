from pathlib import Path

import pytest

from scorer.config import ScoringConfig
from scorer.loader import load_leads
from scorer.models import Lead
from scorer.rules import (
    assign_tier,
    email_value,
    industry_value,
    readiness_value,
    recency_value,
    recommend_action,
    revenue_value,
    score_lead,
    score_leads,
    seniority_value,
    size_value,
    timeline_value,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def make_lead(**overrides) -> Lead:
    """A solid, average lead. Tests change one thing at a time."""
    values = dict(
        company="Test Co",
        employees=120,
        industry="logistics",
        annual_revenue_musd=30.0,
        automation_readiness=4,
        emails_opened=3,
        website_visits=3,
        replied=False,
    )
    values.update(overrides)
    return Lead(**values)


# --- individual signal curves ------------------------------------------------

def test_size_full_credit_inside_plateau():
    assert size_value(50) == 1.0
    assert size_value(120) == 1.0
    assert size_value(300) == 1.0


def test_size_decays_smoothly_on_both_sides():
    assert 0 < size_value(10) < size_value(30) < 1.0
    assert 0 < size_value(5000) < size_value(1000) < 1.0
    # no cliff at the plateau edge
    assert size_value(49) > 0.99


def test_size_zero_employees_scores_zero():
    assert size_value(0) == 0.0


def test_industry_known_and_unknown():
    assert industry_value("Logistics") == 1.0
    assert industry_value("  MANUFACTURING ") == 0.9
    assert industry_value("underwater basket weaving") == ScoringConfig().industry_fit["other"]


def test_readiness_maps_one_to_five_onto_zero_to_one():
    assert readiness_value(1) == 0.0
    assert readiness_value(3) == 0.5
    assert readiness_value(5) == 1.0


def test_revenue_is_monotonic_and_capped():
    assert revenue_value(0) == 0.0
    assert revenue_value(1) < revenue_value(10) < revenue_value(50)
    assert revenue_value(50) == pytest.approx(1.0)
    assert revenue_value(5000) == 1.0


def test_engagement_has_diminishing_returns():
    first_step = email_value(1) - email_value(0)
    later_step = email_value(9) - email_value(8)
    assert first_step > later_step > 0


def test_recency_halves_every_halflife():
    assert recency_value(0) == 1.0
    assert recency_value(30) == pytest.approx(0.5)
    assert recency_value(60) == pytest.approx(0.25)


def test_timeline_faster_is_better():
    assert timeline_value(1) > timeline_value(3) > timeline_value(6) > timeline_value(12)
    assert timeline_value(60) == ScoringConfig().timeline_default


def test_seniority_ordering_and_aliases():
    assert seniority_value("C-Level") > seniority_value("director") > seniority_value("individual")
    assert seniority_value("CEO") == seniority_value("c-level")
    assert seniority_value("Vice President") == seniority_value("vp")
    assert seniority_value("astronaut") == ScoringConfig().seniority_scores["other"]


# --- whole-lead scoring ------------------------------------------------------

def test_score_and_axes_stay_in_range():
    for lead in (
        make_lead(),
        make_lead(employees=0, automation_readiness=1, annual_revenue_musd=0),
        make_lead(emails_opened=500, website_visits=500, replied=True),
    ):
        result = score_lead(lead)
        assert 0 <= result.score <= 100
        assert 0 <= result.fit_score <= 100
        assert 0 <= result.intent_score <= 100
        assert 0 <= result.confidence <= 1


def test_ideal_lead_is_hot_and_poor_lead_is_cold():
    ideal = make_lead(
        employees=100, annual_revenue_musd=60, automation_readiness=5,
        emails_opened=8, website_visits=10, replied=True,
        demo_requested=True, days_since_last_activity=2,
        contact_seniority="c-level", budget_confirmed=True, timeline_months=1,
    )
    poor = make_lead(
        employees=3, industry="other", annual_revenue_musd=0.2, automation_readiness=1,
        emails_opened=0, website_visits=0, replied=False,
        demo_requested=False, days_since_last_activity=200,
        contact_seniority="individual", budget_confirmed=False, timeline_months=24,
    )
    assert score_lead(ideal).tier == "hot"
    assert score_lead(ideal).score >= 90
    assert score_lead(poor).tier == "cold"
    assert score_lead(poor).score <= 15


def test_more_engagement_never_lowers_the_score():
    quiet = score_lead(make_lead(emails_opened=0, website_visits=0)).score
    active = score_lead(make_lead(emails_opened=6, website_visits=8)).score
    replied = score_lead(make_lead(emails_opened=6, website_visits=8, replied=True)).score
    assert quiet < active < replied


def test_better_fit_raises_the_score():
    weak = score_lead(make_lead(industry="other", automation_readiness=1)).score
    strong = score_lead(make_lead(industry="logistics", automation_readiness=5)).score
    assert weak < strong


def test_breakdown_adds_up_to_the_score():
    result = score_lead(make_lead(replied=True, demo_requested=True, timeline_months=2))
    assert sum(result.breakdown.values()) == pytest.approx(result.score, abs=1.5)


def test_missing_optional_data_lowers_confidence_but_does_not_punish():
    basic = score_lead(make_lead())
    full = score_lead(
        make_lead(
            demo_requested=False, days_since_last_activity=10,
            contact_seniority="director", budget_confirmed=True, timeline_months=3,
        )
    )
    assert basic.confidence < full.confidence == 1.0
    assert "timeline" in basic.missing_signals
    assert "timeline" not in full.missing_signals
    # unknown is not treated as a zero: a lead with no optional data still scores sensibly
    assert basic.score > 30


def test_hot_requires_both_axes_to_be_high():
    # Heavy weight on intent lets a poor-fit lead cross the hot threshold on score alone.
    config = ScoringConfig(axis_weights={"fit": 0.2, "intent": 0.8})
    lead = make_lead(
        industry="other", automation_readiness=1, employees=5, annual_revenue_musd=0.5,
        emails_opened=9, website_visits=12, replied=True, demo_requested=True,
        days_since_last_activity=1, contact_seniority="c-level",
        budget_confirmed=True, timeline_months=1,
    )
    result = score_lead(lead, config)
    assert result.score >= config.hot_threshold
    assert result.tier == "warm"
    assert any("Held at warm" in flag for flag in result.flags)


def test_stale_lead_is_flagged():
    result = score_lead(make_lead(days_since_last_activity=120))
    assert any("Stale" in flag for flag in result.flags)
    assert not score_lead(make_lead(days_since_last_activity=5)).flags


def test_low_confidence_is_flagged_when_most_signals_are_missing():
    config = ScoringConfig(low_confidence_below=0.9)
    result = score_lead(make_lead(), config)
    assert any("Limited data" in flag for flag in result.flags)


def test_strengths_and_gaps_are_explained():
    result = score_lead(make_lead(emails_opened=0, website_visits=0))
    assert result.strengths
    assert any("Email engagement" in gap for gap in result.gaps)


def test_next_action_quadrants():
    cfg = ScoringConfig()
    assert recommend_action(90, 90, 90, cfg) == "Priority outreach"
    assert recommend_action(70, 70, 70, cfg) == "Follow up soon"
    assert recommend_action(90, 10, 50, cfg) == "Nurture"
    assert recommend_action(10, 90, 50, cfg) == "Qualify first"
    assert recommend_action(10, 10, 10, cfg) == "Low priority"


def test_assign_tier_boundaries():
    cfg = ScoringConfig()
    assert assign_tier(cfg.hot_threshold, cfg) == "hot"
    assert assign_tier(cfg.hot_threshold - 1, cfg) == "warm"
    assert assign_tier(cfg.warm_threshold, cfg) == "warm"
    assert assign_tier(cfg.warm_threshold - 1, cfg) == "cold"


def test_score_leads_are_ranked_best_first():
    ranked = score_leads([
        make_lead(company="Weak", employees=3, industry="other", automation_readiness=1),
        make_lead(company="Strong", replied=True, emails_opened=6, website_visits=8),
        make_lead(company="Middle"),
    ])
    assert [s.company for s in ranked] == ["Strong", "Middle", "Weak"]


# --- configuration -----------------------------------------------------------

def test_default_config_is_valid_and_round_trips(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(ScoringConfig().model_dump_json(), encoding="utf-8")
    assert ScoringConfig.from_json(path) == ScoringConfig()


def test_partial_config_keeps_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"hot_threshold": 85}', encoding="utf-8")
    config = ScoringConfig.from_json(path)
    assert config.hot_threshold == 85
    assert config.warm_threshold == ScoringConfig().warm_threshold


@pytest.mark.parametrize(
    "bad",
    [
        {"axis_weights": {"fit": 0.7, "intent": 0.7}},
        {"axis_weights": {"fit": 1.0}},
        {"fit_weights": {"not_a_signal": 10}},
        {"intent_weights": {"replied": -5}},
        {"industry_fit": {"logistics": 1.5}},
        {"hot_threshold": 30, "warm_threshold": 40},
    ],
)
def test_invalid_config_is_rejected(bad):
    with pytest.raises(ValueError):
        ScoringConfig(**bad)


def test_changing_weights_changes_the_ranking():
    fit_heavy = ScoringConfig(axis_weights={"fit": 0.9, "intent": 0.1})
    intent_heavy = ScoringConfig(axis_weights={"fit": 0.1, "intent": 0.9})
    great_fit_no_engagement = make_lead(
        industry="logistics", automation_readiness=5, emails_opened=0, website_visits=0
    )
    assert score_lead(great_fit_no_engagement, fit_heavy).score > score_lead(
        great_fit_no_engagement, intent_heavy
    ).score


# --- integration with the sample files --------------------------------------

def test_original_sample_file_still_scores():
    data = load_leads(DATA_DIR / "sample_leads.csv")
    assert data.leads
    ranked = score_leads(data.leads)
    assert len(ranked) == len(data.leads)
    assert all(0 <= s.score <= 100 for s in ranked)
    assert [s.score for s in ranked] == sorted((s.score for s in ranked), reverse=True)


def test_large_sample_file_has_a_healthy_spread_of_tiers():
    data = load_leads(DATA_DIR / "sample_leads_large.csv")
    assert not data.warnings
    tiers = {s.tier for s in score_leads(data.leads)}
    assert tiers == {"hot", "warm", "cold"}

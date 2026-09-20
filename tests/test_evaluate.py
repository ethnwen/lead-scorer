import pytest

from scorer.evaluate import evaluate, lift_at_fraction, precision_at_k, roc_auc
from scorer.loader import load_leads
from scorer.rules import score_lead


# --- metrics -----------------------------------------------------------------

def test_auc_perfect_reversed_and_ties():
    assert roc_auc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) == 1.0
    assert roc_auc([0.1, 0.2, 0.8, 0.9], [True, True, False, False]) == 0.0
    assert roc_auc([5, 5, 5, 5], [True, False, True, False]) == 0.5


def test_auc_known_textbook_example():
    scores = [0.1, 0.4, 0.35, 0.8]
    labels = [False, False, True, True]
    assert roc_auc(scores, labels) == pytest.approx(0.75)


def test_auc_needs_both_classes():
    with pytest.raises(ValueError):
        roc_auc([1, 2, 3], [True, True, True])


def test_precision_at_k_and_lift():
    scores = [90, 80, 70, 60, 50, 40, 30, 20]
    labels = [True, True, False, True, False, False, False, False]
    assert precision_at_k(scores, labels, 2) == 1.0
    assert precision_at_k(scores, labels, 4) == 0.75
    # base rate is 3/8, top quarter (2 leads) converts at 100%
    assert lift_at_fraction(scores, labels, 0.25) == pytest.approx(1.0 / (3 / 8))


def test_lift_is_none_when_nobody_won():
    assert lift_at_fraction([3, 2, 1], [False, False, False]) is None


def test_evaluate_ignores_unknown_outcomes(tmp_path):
    path = tmp_path / "leads.csv"
    path.write_text(
        "company,employees,industry,annual_revenue_musd,automation_readiness,emails_opened,website_visits,replied,won\n"
        "Alpha,120,logistics,40,5,8,10,yes,yes\n"
        "Beta,110,manufacturing,30,4,5,6,yes,yes\n"
        "Gamma,5,other,0.5,1,0,0,no,no\n"
        "Delta,3,other,0.4,1,0,0,no,no\n"
        "Epsilon,90,logistics,20,4,2,2,no,\n",
        encoding="utf-8",
    )
    data = load_leads(path, outcome_column="won")
    scored = [score_lead(lead) for lead in data.leads]
    result = evaluate(scored, data.outcomes)
    assert result["n"] == 4
    assert result["won"] == 2
    assert result["auc_score"] == 1.0


# --- loader ------------------------------------------------------------------

HEADER = "company,employees,industry,annual_revenue_musd,automation_readiness,emails_opened,website_visits,replied\n"


def test_loader_skips_bad_rows_with_warnings(tmp_path):
    path = tmp_path / "leads.csv"
    path.write_text(
        HEADER
        + "Good Co,100,logistics,20,4,2,3,yes\n"
        + "Bad Readiness,100,logistics,20,9,2,3,yes\n"
        + "Not A Number,lots,logistics,20,4,2,3,yes\n"
        + "Good Co,100,logistics,20,4,2,3,yes\n",
        encoding="utf-8",
    )
    data = load_leads(path)
    assert [lead.company for lead in data.leads] == ["Good Co"]
    assert len(data.warnings) == 3
    assert any("duplicate" in w for w in data.warnings)


def test_loader_reads_yes_no_and_blank_optional_values(tmp_path):
    path = tmp_path / "leads.csv"
    path.write_text(
        HEADER.strip() + ",demo_requested,budget_confirmed,timeline_months\n"
        "A,100,logistics,20,4,2,3,YES,no,,\n"
        "B,100,logistics,20,4,,,False,,true,6\n",
        encoding="utf-8",
    )
    a, b = load_leads(path).leads
    assert a.replied is True and a.demo_requested is False
    assert a.budget_confirmed is None and a.timeline_months is None
    assert b.emails_opened == 0 and b.website_visits == 0 and b.replied is False
    assert b.budget_confirmed is True and b.timeline_months == 6


def test_loader_reports_missing_columns(tmp_path):
    path = tmp_path / "leads.csv"
    path.write_text("company,employees\nA,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required columns"):
        load_leads(path)


def test_loader_reports_missing_file():
    with pytest.raises(FileNotFoundError):
        load_leads("does_not_exist.csv")


def test_loader_reads_json_list_and_wrapped_json(tmp_path):
    row = '{"company": "A", "employees": 50, "industry": "retail", "annual_revenue_musd": 5, "automation_readiness": 3}'
    plain = tmp_path / "plain.json"
    plain.write_text(f"[{row}]", encoding="utf-8")
    wrapped = tmp_path / "wrapped.json"
    wrapped.write_text(f'{{"leads": [{row}]}}', encoding="utf-8")
    assert load_leads(plain).leads[0].company == "A"
    assert load_leads(wrapped).leads[0].company == "A"


def test_loader_handles_tab_separated_files(tmp_path):
    path = tmp_path / "leads.tsv"
    path.write_text(
        "company\temployees\tindustry\tannual_revenue_musd\tautomation_readiness\n"
        "A\t50\tretail\t5\t3\n",
        encoding="utf-8",
    )
    assert load_leads(path).leads[0].employees == 50

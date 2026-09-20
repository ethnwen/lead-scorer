"""Measure how well the scores predict real outcomes.

Add a column to your leads file with what actually happened (for example a
"won" column with yes/no or true/false), then run:

    python -m scorer.evaluate my_leads_with_outcomes.csv --outcome won

Metrics:
  AUC            Chance that a random winner outscored a random loser.
                 0.5 is a coin flip, 1.0 is perfect ranking.
  Precision @ k  Share of the top k leads that were won.
  Lift           How many times better the top of the ranking converts
                 than leads picked at random.
  Tier table     Win rate inside each tier. A useful scorer shows hot > warm > cold.
"""

import argparse
import sys

from pydantic import ValidationError

from .config import ScoringConfig
from .loader import load_leads
from .models import ScoredLead
from .rules import score_lead


def roc_auc(scores: list[float], labels: list[bool]) -> float:
    """Area under the ROC curve, computed by comparing every winner with
    every loser. Ties count as half. Fine for up to a few thousand leads."""
    positives = [s for s, y in zip(scores, labels) if y]
    negatives = [s for s, y in zip(scores, labels) if not y]
    if not positives or not negatives:
        raise ValueError("Need at least one won and one lost lead to compute AUC")
    wins = 0.0
    for p in positives:
        for n in negatives:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(positives) * len(negatives))


def _ranked_labels(scores: list[float], labels: list[bool]) -> list[bool]:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    return [labels[i] for i in order]


def precision_at_k(scores: list[float], labels: list[bool], k: int) -> float:
    k = max(1, min(k, len(scores)))
    top = _ranked_labels(scores, labels)[:k]
    return sum(top) / k


def lift_at_fraction(scores: list[float], labels: list[bool], fraction: float = 0.25) -> float | None:
    base_rate = sum(labels) / len(labels)
    if base_rate == 0:
        return None
    k = max(1, round(len(labels) * fraction))
    return precision_at_k(scores, labels, k) / base_rate


def evaluate(scored: list[ScoredLead], outcomes: list[bool | None]) -> dict:
    """Compare scores with outcomes. Leads without a known outcome are ignored."""
    pairs = [(s, y) for s, y in zip(scored, outcomes) if y is not None]
    if not pairs:
        raise ValueError("No leads with a known outcome")
    leads = [s for s, _ in pairs]
    labels = [y for _, y in pairs]

    total = [float(s.score) for s in leads]
    result = {
        "n": len(labels),
        "won": sum(labels),
        "win_rate": sum(labels) / len(labels),
        "auc_score": roc_auc(total, labels),
        "auc_fit": roc_auc([float(s.fit_score) for s in leads], labels),
        "auc_intent": roc_auc([float(s.intent_score) for s in leads], labels),
        "precision_at_5": precision_at_k(total, labels, 5),
        "lift_top_25": lift_at_fraction(total, labels, 0.25),
        "tiers": {},
    }
    for tier in ("hot", "warm", "cold"):
        in_tier = [y for s, y in pairs if s.tier == tier]
        result["tiers"][tier] = (len(in_tier), sum(in_tier))
    return result


def format_report(result: dict) -> str:
    lines = [
        f"Evaluation on {result['n']} leads: {result['won']} won ({result['win_rate']:.0%} win rate)",
        "",
        f"AUC, final score      {result['auc_score']:.3f}   (0.5 = random, 1.0 = perfect)",
        f"AUC, fit only         {result['auc_fit']:.3f}",
        f"AUC, intent only      {result['auc_intent']:.3f}",
        f"Precision at top 5    {result['precision_at_5']:.0%}",
    ]
    lift = result["lift_top_25"]
    lines.append(f"Lift, top 25%         {lift:.2f}x" if lift is not None else "Lift, top 25%         n/a")
    lines += ["", "Win rate by tier"]
    for tier, (count, wins) in result["tiers"].items():
        rate = f"{wins / count:.0%}" if count else "n/a"
        lines.append(f"  {tier:<6} leads {count:<4} won {wins:<4} rate {rate}")
    if result["n"] < 50:
        lines += ["", "Note: with fewer than 50 labeled leads these numbers are noisy. Treat them as a sanity check."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scorer.evaluate",
        description="Compare lead scores against real win/loss outcomes.",
    )
    parser.add_argument("path", help="CSV or JSON file with leads and an outcome column")
    parser.add_argument("--outcome", default="won", help="name of the outcome column (default: won)")
    parser.add_argument("--config", help="JSON file with custom scoring settings")
    args = parser.parse_args(argv)

    try:
        config = ScoringConfig.from_json(args.config) if args.config else ScoringConfig()
        data = load_leads(args.path, outcome_column=args.outcome)
        for warning in data.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        scored = [score_lead(lead, config) for lead in data.leads]  # keep file order to match outcomes
        result = evaluate(scored, data.outcomes)
    except ValidationError as error:
        sys.exit("Invalid scoring settings: " + "; ".join(item["msg"].removeprefix("Value error, ") for item in error.errors()))
    except (OSError, ValueError) as error:
        sys.exit(str(error))

    print("\n" + format_report(result) + "\n")


if __name__ == "__main__":
    main()

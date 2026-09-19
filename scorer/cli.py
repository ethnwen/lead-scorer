"""Command-line interface: score a CSV of leads and print a ranked table.

Usage:
    python -m scorer.cli data/sample_leads.csv
"""

import sys

import pandas as pd

from .models import Lead
from .rules import score_lead


def csv_to_leads(path: str) -> list[Lead]:
    df = pd.read_csv(path)
    return [
        Lead(
            company=row["company"],
            employees=int(row["employees"]),
            industry=row["industry"],
            annual_revenue_musd=float(row["annual_revenue_musd"]),
            automation_readiness=int(row["automation_readiness"]),
            emails_opened=int(row.get("emails_opened", 0)),
            website_visits=int(row.get("website_visits", 0)),
            replied=bool(row.get("replied", False)),
        )
        for _, row in df.iterrows()
    ]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m scorer.cli <leads.csv>")
    leads = csv_to_leads(sys.argv[1])
    scored = sorted((score_lead(l) for l in leads), key=lambda s: s.score, reverse=True)

    print("\n" + f"{'COMPANY':<25}{'SCORE':<8}{'TIER':<8}")
    print("-" * 41)
    for s in scored:
        print(f"{s.company:<25}{s.score:<8}{s.tier:<8}")
    print()


if __name__ == "__main__":
    main()

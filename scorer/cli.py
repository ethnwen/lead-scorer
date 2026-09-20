"""Command-line interface: score a file of leads and print a ranked table.

Usage:
    python -m scorer.cli data/sample_leads.csv
    python -m scorer.cli data/sample_leads_large.csv --explain --top 5
    python -m scorer.cli data/sample_leads_large.csv --format csv --output ranked.csv
    python -m scorer.cli --help
"""

import argparse
import json
import sys

import pandas as pd
from pydantic import ValidationError

from .config import ScoringConfig
from .loader import load_leads
from .models import ScoredLead
from .rules import ACTION_GUIDANCE, score_leads


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scorer.cli",
        description="Score and rank sales leads from a CSV or JSON file.",
    )
    parser.add_argument("path", nargs="?", help="CSV or JSON file of leads")
    parser.add_argument("--config", help="JSON file with custom scoring settings")
    parser.add_argument(
        "--dump-config", action="store_true", help="print the default settings as JSON and exit"
    )
    parser.add_argument("--top", type=int, help="only show the top N leads")
    parser.add_argument("--tier", choices=["hot", "warm", "cold"], help="only show leads in this tier")
    parser.add_argument("--explain", action="store_true", help="show why each lead got its score")
    parser.add_argument("--format", choices=["table", "csv", "json"], default="table")
    parser.add_argument("--output", help="write results to this file instead of the screen")
    return parser


def format_table(scored: list[ScoredLead]) -> str:
    header = (
        f"{'#':<4}{'COMPANY':<28}{'SCORE':<7}{'TIER':<7}"
        f"{'FIT':<6}{'INTENT':<8}{'CONF':<7}NEXT STEP"
    )
    lines = [header, "-" * (len(header) + 12)]
    for rank, s in enumerate(scored, start=1):
        lines.append(
            f"{rank:<4}{s.company[:26]:<28}{s.score:<7}{s.tier:<7}"
            f"{s.fit_score:<6}{s.intent_score:<8}{s.confidence:<7.0%}{s.next_action}"
        )
    return "\n".join(lines)


def format_summary(scored: list[ScoredLead]) -> str:
    counts = {tier: sum(1 for s in scored if s.tier == tier) for tier in ("hot", "warm", "cold")}
    average = sum(s.score for s in scored) / len(scored)
    noun = "lead" if len(scored) == 1 else "leads"
    return (
        f"{len(scored)} {noun} | hot {counts['hot']} | warm {counts['warm']} | "
        f"cold {counts['cold']} | average score {average:.0f}"
    )


def format_explanations(scored: list[ScoredLead]) -> str:
    blocks = []
    for rank, s in enumerate(scored, start=1):
        lines = [
            f"{rank}. {s.company}: {s.score} ({s.tier.upper()})  "
            f"fit {s.fit_score}, intent {s.intent_score}, confidence {s.confidence:.0%}",
            f"   Next step: {s.next_action}. {ACTION_GUIDANCE.get(s.next_action, '')}",
        ]
        if s.strengths:
            lines.append("   Strengths:")
            lines += [f"     + {item}" for item in s.strengths]
        if s.gaps:
            lines.append("   Gaps:")
            lines += [f"     - {item}" for item in s.gaps]
        if s.flags:
            lines.append("   Flags:")
            lines += [f"     ! {item}" for item in s.flags]
        if s.missing_signals:
            lines.append(f"   Not provided: {', '.join(s.missing_signals)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_csv(scored: list[ScoredLead]) -> str:
    rows = []
    for s in scored:
        row = {
            "company": s.company,
            "score": s.score,
            "tier": s.tier,
            "fit_score": s.fit_score,
            "intent_score": s.intent_score,
            "confidence": s.confidence,
            "next_action": s.next_action,
            "flags": "; ".join(s.flags),
        }
        row.update({f"pts_{name}": pts for name, pts in s.breakdown.items()})
        rows.append(row)
    return pd.DataFrame(rows).to_csv(index=False)


def format_json(scored: list[ScoredLead]) -> str:
    return json.dumps([s.model_dump() for s in scored], indent=2)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    try:
        config = ScoringConfig.from_json(args.config) if args.config else ScoringConfig()
    except ValidationError as error:
        problems = "; ".join(item["msg"].removeprefix("Value error, ") for item in error.errors())
        sys.exit(f"Invalid scoring settings: {problems}")
    except (OSError, ValueError) as error:  # missing file or malformed JSON
        sys.exit(f"Could not load the config file: {error}")

    if args.dump_config:
        print(config.model_dump_json(indent=2))
        return

    if not args.path:
        sys.exit("Please give a leads file, for example: python -m scorer.cli data/sample_leads.csv")

    try:
        data = load_leads(args.path)
    except (FileNotFoundError, ValueError) as error:
        sys.exit(str(error))

    for warning in data.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    if not data.leads:
        sys.exit("No valid leads found in the file.")

    scored = score_leads(data.leads, config)
    if args.tier:
        scored = [s for s in scored if s.tier == args.tier]
    if args.top:
        scored = scored[: args.top]
    if not scored:
        sys.exit("No leads match those filters.")

    if args.format == "csv":
        text = format_csv(scored)
    elif args.format == "json":
        text = format_json(scored)
    else:
        parts = [format_table(scored), "", format_summary(scored)]
        if args.explain:
            parts += ["", format_explanations(scored)]
        text = "\n".join(parts) + "\n"

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        print(f"Saved {len(scored)} leads to {args.output}")
    else:
        print("\n" + text)


if __name__ == "__main__":
    main()

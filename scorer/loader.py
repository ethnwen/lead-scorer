"""Reading leads from CSV or JSON files, with validation and clear warnings.

Bad rows are skipped with a warning instead of crashing the whole run, and
optional columns can be left out entirely.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from .models import Lead

REQUIRED_COLUMNS = [
    "company",
    "employees",
    "industry",
    "annual_revenue_musd",
    "automation_readiness",
]

TRUE_WORDS = {"true", "yes", "y", "1", "1.0", "t"}
FALSE_WORDS = {"false", "no", "n", "0", "0.0", "f"}


@dataclass
class LoadedData:
    leads: list[Lead]
    outcomes: list[bool | None] | None = None
    warnings: list[str] = field(default_factory=list)


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _to_str(value) -> str | None:
    return None if _blank(value) else str(value).strip()


def _to_int(value) -> int | None:
    return None if _blank(value) else int(float(str(value).replace(",", "")))


def _to_float(value) -> float | None:
    return None if _blank(value) else float(str(value).replace(",", "").replace("$", ""))


def _to_bool(value) -> bool | None:
    if _blank(value):
        return None
    word = str(value).strip().lower()
    if word in TRUE_WORDS:
        return True
    if word in FALSE_WORDS:
        return False
    raise ValueError(f"cannot read {value!r} as yes/no")


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("leads", data)
        return pd.DataFrame(data)

    first_line = path.read_text(encoding="utf-8-sig").splitlines()[0] if path.stat().st_size else ""
    separator = "\t" if "\t" in first_line and "," not in first_line else ","
    return pd.read_csv(path, sep=separator, encoding="utf-8-sig")


def _get(row: dict, name: str, convert):
    """Read one column and convert it, naming the column if it cannot be read."""
    try:
        return convert(row.get(name))
    except (ValueError, TypeError):
        raise ValueError(f"{name}: could not read {row.get(name)!r}") from None


def _row_to_lead(row: dict) -> Lead:
    return Lead(
        company=_get(row, "company", _to_str),
        employees=_get(row, "employees", _to_int),
        industry=_get(row, "industry", _to_str),
        annual_revenue_musd=_get(row, "annual_revenue_musd", _to_float),
        automation_readiness=_get(row, "automation_readiness", _to_int),
        emails_opened=_get(row, "emails_opened", _to_int) or 0,
        website_visits=_get(row, "website_visits", _to_int) or 0,
        replied=_get(row, "replied", _to_bool) or False,
        demo_requested=_get(row, "demo_requested", _to_bool),
        days_since_last_activity=_get(row, "days_since_last_activity", _to_int),
        contact_seniority=_get(row, "contact_seniority", _to_str),
        budget_confirmed=_get(row, "budget_confirmed", _to_bool),
        timeline_months=_get(row, "timeline_months", _to_int),
    )


def _short_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        first = error.errors()[0]
        field_name = ".".join(str(part) for part in first["loc"])
        return f"{field_name}: {first['msg']}"
    return str(error)


def load_leads(path: str | Path, outcome_column: str | None = None) -> LoadedData:
    """Read a CSV or JSON file into Lead objects.

    If outcome_column is given (for example "won"), the matching win/loss
    values are returned in the same order as the leads, for evaluation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Could not find the file: {path}")

    df = _read_table(path)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}. "
            f"Columns found: {', '.join(df.columns)}"
        )
    if outcome_column and outcome_column not in df.columns:
        raise ValueError(f"Outcome column '{outcome_column}' not found in the file")

    leads: list[Lead] = []
    outcomes: list[bool | None] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for index, row in enumerate(df.to_dict(orient="records")):
        row_number = index + 2  # header is row 1 in a spreadsheet
        name = _to_str(row.get("company")) or f"row {row_number}"
        try:
            lead = _row_to_lead(row)
            outcome = _to_bool(row.get(outcome_column)) if outcome_column else None
        except (ValidationError, ValueError, TypeError) as error:
            warnings.append(f"Skipped row {row_number} ({name}): {_short_error(error)}")
            continue

        key = lead.company.strip().lower()
        if key in seen:
            warnings.append(f"Skipped row {row_number} ({name}): duplicate company name")
            continue
        seen.add(key)
        leads.append(lead)
        outcomes.append(outcome)

    return LoadedData(
        leads=leads,
        outcomes=outcomes if outcome_column else None,
        warnings=warnings,
    )

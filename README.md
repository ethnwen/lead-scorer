# Lead Scorer

A transparent, rule-based lead scoring engine for sales teams. It reads a list of prospects, scores each one from 0 to 100, sorts them into hot, warm, and cold tiers, and explains exactly why every lead got its score. It runs as a command-line tool, and the same scoring logic is available through a small FastAPI service.

## Features

- **Two-axis scoring.** Every lead gets a Fit score and an Intent score, blended into one final score.
- **Explainable results.** Each result lists the points every signal contributed, the biggest strengths, the biggest gaps, warning flags, and a recommended next step.
- **Handles incomplete data.** Optional columns can be left blank. Missing data is never treated as a zero, and each result reports a confidence value.
- **Configurable.** All weights and thresholds live in one place and can be overridden with a JSON file.
- **Accuracy checking.** An evaluation tool compares scores with real win/loss outcomes.
- **Sturdy input handling.** Reads CSV or JSON. Rows with bad values are skipped with a clear warning instead of crashing the run.
- **Tested.** 46 automated tests cover the scoring curves, tiers, configuration, loading, and metrics.

## How the scoring works

Each lead gets two sub-scores from 0 to 100. They are blended into a final score and a tier.

| Axis | Question it answers | Signals |
|---|---|---|
| Fit | Does this company look like our ideal customer? | Industry, company size, revenue, automation readiness |
| Intent | Are they likely to buy soon? | Replies, demo requests, email and website engagement, recent activity, buying timeline, contact seniority, confirmed budget |

This follows the BANT qualification framework (Budget, Authority, Need, Timeline) that sales teams already use.

### Design choices

- **Smooth curves, not cutoffs.** A company with 49 employees scores almost the same as one with 51, instead of jumping at a threshold.
- **Missing data is not treated as zero.** Each axis is rescaled over the signals that are known, and every result reports how much data it was based on.
- **Hot means strong on both axes.** A perfect-fit company that never engages, or a very engaged lead that is a poor fit, is held at warm.
- **Diminishing returns.** The first few email opens matter more than the tenth, and interest fades the longer a lead goes quiet.

### Tiers and next steps

| Tier | Rule |
|---|---|
| Hot | Score of 75 or higher, with both Fit and Intent high |
| Warm | Score from 40 to 74 |
| Cold | Score below 40 |

Each lead also gets a recommended next step:

| Next step | Meaning |
|---|---|
| Priority outreach | Strong fit and strong buying signals. Contact within one business day. |
| Follow up soon | Good fit and good signals, just short of top priority. |
| Nurture | Strong fit but little buying activity so far. Keep warm with relevant content. |
| Qualify first | Very engaged but a weaker fit. Confirm need and budget before investing time. |
| Low priority | Weak fit and weak signals. Automated nurture only. |

## Project structure

```
lead-scorer/
├── README.md
├── requirements.txt
├── sample_leads.json
├── scorer/
│   ├── __init__.py
│   ├── config.py      # every weight and threshold
│   ├── models.py      # Lead and ScoredLead data models
│   ├── rules.py       # the scoring engine (pure functions)
│   ├── loader.py      # reads and validates CSV or JSON files
│   ├── cli.py         # command-line interface
│   ├── evaluate.py    # accuracy metrics against real outcomes
│   └── api.py         # FastAPI service
├── tests/
│   ├── test_rules.py
│   └── test_evaluate.py
└── data/
    ├── sample_leads.csv
    └── sample_leads_large.csv
```

## Setup

You need Python 3.10 or newer.

```
git clone https://github.com/ethnwen/lead-scorer.git
cd lead-scorer
python -m venv venv
```

Activate the virtual environment:

```
# Windows
venv\Scripts\activate

# Mac or Linux
source venv/bin/activate
```

Then install the dependencies:

```
pip install -r requirements.txt
```

## Usage

Score a file of leads and print a ranked table:

```
python -m scorer.cli data/sample_leads_large.csv
```

Example output:

```
#   COMPANY                     SCORE  TIER   FIT   INTENT  CONF   NEXT STEP
----------------------------------------------------------------------------------------
1   Cobalt Trucking             96     hot    96    96      100%   Priority outreach
2   Cedar Fleet Services        92     hot    92    91      93%    Priority outreach
3   Riverbend Fabrication       91     hot    90    93      95%    Priority outreach
4   Juniper Logistics           89     hot    100   79      100%   Priority outreach
5   Ironwood Industrial         86     hot    97    75      95%    Priority outreach
```

See why a lead scored the way it did:

```
python -m scorer.cli data/sample_leads_large.csv --explain --top 3
```

```
1. Cobalt Trucking: 96 (HOT)  fit 96, intent 96, confidence 100%
   Next step: Priority outreach. Strong fit and strong buying signals. Contact within one business day.
   Strengths:
     + Industry fit (+15.0): transportation is a 100% match to the ideal customer profile
     + Automation readiness (+15.0): automation readiness 5 out of 5
     + Company size (+12.5): 122 employees, inside the ideal range
```

### Command-line options

| Option | What it does |
|---|---|
| `--explain` | Show strengths, gaps, and flags for each lead |
| `--top N` | Only show the top N leads |
| `--tier hot` | Only show leads in one tier (hot, warm, or cold) |
| `--format csv` | Output as CSV or JSON instead of a table |
| `--output FILE` | Save the results to a file |
| `--config FILE` | Use custom scoring settings |
| `--dump-config` | Print the default settings as JSON |
| `--help` | Show all options |

### Input files

Files can be CSV or JSON.

Required columns: `company`, `employees`, `industry`, `annual_revenue_musd`, `automation_readiness` (1 to 5).

Optional columns: `emails_opened`, `website_visits`, `replied`, `demo_requested`, `days_since_last_activity`, `contact_seniority`, `budget_confirmed`, `timeline_months`.

Leave optional values blank when they are unknown. The score is then based on the signals that are available, and the confidence value goes down instead of the lead being penalized.

## Custom settings

Every weight, curve, and threshold can be changed without editing the code:

```
python -m scorer.cli --dump-config > my_config.json
python -m scorer.cli data/sample_leads_large.csv --config my_config.json
```

Your file only needs to include the settings you want to change. Anything you leave out keeps its default. Invalid settings, such as weights that do not add up, are rejected with a clear message.

## Checking accuracy against real results

Add a `won` column (yes or no) to a file of past leads, then run:

```
python -m scorer.evaluate past_leads.csv --outcome won
```

The report includes:

- **AUC.** The chance that a random winner outscored a random loser. 0.5 is a coin flip and 1.0 is perfect.
- **Precision at the top.** The share of the top-ranked leads that were actually won.
- **Lift.** How many times better the top of the ranking converts than random picking.
- **Win rate by tier.** A useful scorer shows hot converting better than warm, and warm better than cold.

## API

The scoring logic is also available as a FastAPI service. Start it with:

```
python -m uvicorn scorer.api:app --reload
```

Then open `http://127.0.0.1:8000/docs` in a browser to see the available endpoints and try them out.

## Tests

```
python -m pytest
```

## Limitations

The weights are expert judgment, not learned from data, and the sample files are fictional. This scorer is a transparent starting point rather than a proven predictor. Once real won and lost outcomes are available, use the evaluation tool to check how well it performs and to tune the weights. Training a model on that data is a sensible next step.

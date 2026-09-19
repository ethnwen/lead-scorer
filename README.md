# Lead Scorer 🔍

A lightweight, rules-based **B2B lead scoring engine** built with Python and FastAPI.
It ranks prospective customers from 0–100 so a sales team spends its time on the
leads most likely to convert — the same idea behind the scoring system I built
during my internship (which cut account qualification time by ~30%).

## Why lead scoring?

Not every prospect deserves equal effort. Lead scoring converts messy, qualitative
signals (company size, industry fit, engagement, automation readiness) into a single
rankable number. Sales teams work the "qualifying" leads first.

## How the scoring works

Each lead is graded on five weighted dimensions (weights sum to 100):

| Dimension            | Max points | What it captures |
|----------------------|-----------|------------------|
| Company size         | 15        | Right-sized target (mid-market sweet spot) |
| Industry fit         | 20        | How well the industry matches the product |
| Automation readiness | 25        | Pain + willingness to adopt (strongest signal) |
| Revenue              | 15        | Ability to pay |
| Engagement           | 25        | Signals of active interest (opens, replies, visits) |

The total maps to a tier:

- **Hot (70–100)** → contact within 24h
- **Warm (40–69)** → nurture sequence
- **Cold (0–39)**  → automated drip or drop

This is deliberately *rules-based* instead of ML: it is transparent, explainable to
a sales team, needs zero training data, and is a realistic v1 before graduating to
a logistic-regression model once conversion labels exist.

## Project structure

```
lead-scorer/
├── scorer/
│   ├── __init__.py
│   ├── models.py     # Lead data model + scored result
│   ├── rules.py      # The scoring engine (pure functions, easy to test)
│   ├── api.py        # FastAPI app: score single leads or batches
│   └── cli.py        # Score a CSV from the command line
├── tests/
│   └── test_rules.py # Unit tests for the scoring logic
├── data/
│   └── sample_leads.csv
├── requirements.txt
└── README.md
```

## Quick start

```bash
pip install -r requirements.txt

# Score a CSV of leads
python -m scorer.cli data/sample_leads.csv

# Or run the API
uvicorn scorer.api:app --reload
```

### API usage

```bash
# Single lead
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{
    "company": "NorthStar Logistics",
    "employees": 120,
    "industry": "logistics",
    "annual_revenue_musd": 45.0,
    "automation_readiness": 4,
    "emails_opened": 6,
    "website_visits": 9,
    "replied": true
  }'

# Batch
curl -X POST http://localhost:8000/score/batch \
  -H "Content-Type: application/json" \
  -d @data/sample_leads.json
```

Example response:

```json
{
  "company": "NorthStar Logistics",
  "score": 82,
  "tier": "hot",
  "breakdown": {
    "company_size": 15,
    "industry_fit": 18,
    "automation_readiness": 20,
    "revenue": 12,
    "engagement": 17
  }
}
```

## Testing

```bash
pytest -v
```

## Roadmap (where a v2 could go)

- [ ] Logistic regression once real conversion outcomes exist
- [ ] Apollo / LinkedIn Sales Navigator enrichment hooks
- [ ] CRM webhook (HubSpot/Salesforce) to push scores back
- [ ] Threshold tuning dashboard

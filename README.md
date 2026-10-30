# ShadowCost

ShadowCost finds repetitive spreadsheet and email work in small companies. The
agents it generates prove themselves in **shadow mode** before anyone trusts them
to act.

> Enterprise platforms such as Celonis and UiPath are moving toward
> discover-and-automate. ShadowCost targets the gap for smaller companies: agents
> that prove themselves against real human work before they get autonomy.

## What makes it different

- **Shadow mode before autonomy.** Each generated agent runs silently alongside the
  human for N cases. Its output is compared with what the human actually did, and
  it earns autonomy in stages: draft only, then act with approval, then act alone.
  Promotion uses the Wilson lower bound of the agreement rate, so a lucky streak
  isn't enough, and agents get demoted when their agreement drops.
- **Works without enterprise event logs.** Workflows are inferred from what small
  companies already have: CSV/Excel files, file snapshots and email-style records.
- **Measured savings.** Savings come from real execution data, and every estimate
  states its assumptions.

## The pipeline

```
upload → discover → recommend → generate spec → test → approve → shadow → promote → execute → report
```

See [docs/architecture.md](docs/architecture.md) for the architecture diagram and
[docs/roadmap.md](docs/roadmap.md) for build status.

## Status

Early development. Done so far:

- `shadowcost.shadow`: field-by-field comparison of agent output against the human's.
- `shadowcost.autonomy`: the autonomy ladder (shadow → draft → approval →
  autonomous) and the promotion and demotion policy.
- `shadowcost.synth`: a synthetic small company with known ground truth (see below).

## Synthetic data

Real small-company data with labels for "this was repetitive work, and it took
this long" doesn't exist, so ShadowCost ships with a simulator. It models
Fernhill Supplies, a fictional wholesaler whose office manager sends invoices,
records payments and chases late payers. Over four months, it produces:

- what ShadowCost gets to see: daily snapshots of the invoice spreadsheet, a
  bank export and the accounts mailbox;
- what it never sees: a ground-truth log of every action the office manager
  took, its workflow and the minutes it took.

The ground truth lets discovery be scored with precision and recall, and lets
savings estimates be checked against the real minutes. The office manager is
deliberately imperfect: payments are recorded late, reminders get forgotten and
emails are phrased differently each time. See
[data/sample/README.md](data/sample/README.md) for the data card.

```bash
shadowcost-synth --out data/my-run --seed 42 --days 180
```

## Quickstart

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
pytest
```

## Repository layout

```
src/shadowcost/   library code, one module per pipeline stage
tests/            pytest suite
docs/             architecture and roadmap
data/sample/      small synthetic datasets (other data/ contents are git-ignored)
```

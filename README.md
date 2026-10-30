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

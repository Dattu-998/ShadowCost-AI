# Agents: spec, test, approve, shadow

Once discovery has found a workflow, ShadowCost drafts an agent for it, tests
the agent against history, has a person approve it, and runs it in shadow mode,
where it earns autonomy in stages.

```bash
shadowcost-agent generate data/sample --out specs        # draft with the LLM, then backtest
shadowcost-agent approve specs/W2.json --by "<name>"    # nothing runs unapproved
shadowcost-agent shadow specs/W2.json data/sample        # work alongside the person
```

## Design

**The LLM drafts and an engine executes.** The LLM (Groq, `openai/gpt-oss-120b`)
writes a *spec*, which is data and not code: one trigger and an ordered list of
rules, each with conditions, the cells it sets and the email it sends
(`agent/spec.py`). A deterministic engine runs it (`agent/runtime.py`), so
every action can be audited and running an agent costs nothing.

**Specs can't run arbitrary code.** Expressions in a spec (`{{row.reminders_sent + 1}}`,
`{{money(row.amount)}}`) are parsed with Python's `ast` and checked against a
whitelist: `row`/`event` fields, constants, `+ - *` and eight named functions.
Imports, attribute tricks (`row.__class__`), lambdas and comprehensions are
rejected before anything runs (`agent/expr.py`, tested).

**The LLM gets measured evidence, not raw data** (`agent/evidence.py`): the
trigger and date condition from discovery; for each variant of the work, how
the rows looked beforehand (value counts, days-since ranges); for each changed
column, which simple explanations hold and how often ("equals today" 100%,
"previous value + 1" 100%, "equals the bank credit's date" 95%); and two real
example emails. Variants seen only once are listed but not described, because
the first draft of the payment spec turned a single "we already paid" reply
into a rule that emailed every payer.

**Drafts are repaired against the evidence period only** (`agent/generate.py`).
A draft that fails validation (unknown column, bad operator, an expression
that errors on a real row, or invalid JSON) goes back to the model with the
problems listed. A valid draft is backtested on the *same* period the evidence
came from. Below 85% agreement, the model sees its disagreements, grouped and
with examples, and revises. The best of up to three attempts is kept. Later
data is never shown to the model (tested).

**The test replays history** (`agent/backtest.py`). Each morning the agent
sees the spreadsheet as it stood the night before, plus the day's bank credits
or emails, and nothing later (tested). Its actions are paired with the
person's actions on the same case within 4 days, because the person records
payments a day or two late. Each outcome is a *match*, a *mismatch* (some
field differs), *agent only* or *human only*. Only a match counts as
agreement, and days where neither acted are not counted, since that would
inflate the rate.

**Approval is tied to the exact spec.** `approve` stores a content hash of the
spec in SQLite (`agent/store.py`). Shadow mode refuses unapproved specs, and
any edit changes the hash, so an edited spec needs a fresh approval.

**Shadow mode feeds outcomes into the autonomy ladder** (`agent/shadow_mode.py`)
in the order they become known. Promotion needs 30 cases at the current stage
and a Wilson lower bound on agreement of at least 0.85. Evidence restarts at
each stage. An agent emailing a customer on its own when the person wouldn't
have counts as a critical failure and sends it back to shadow. Time saved is
credited only on agreeing cases: 0% in shadow, 50% at draft, 80% at approval
and 100% when autonomous.

## Results

Specs were drafted from the first 80 days of the sample (5 Jan to 25 Mar 2026)
and tested on the 40 held-out days after that. To show what is achievable at
all, each is compared with a reference spec written by hand from the
simulator's actual rules:

| Workflow | LLM attempts | Held-out agreement (LLM) | Reference spec | Agent precision / recall |
|---|---|---|---|---|
| Send invoice email | 1 | 100% (34 cases) | 100% | 100% / 100% |
| Record payment | 1 | 77.8% (36) | 77.8% | 88.9% / 100% |
| Chase overdue invoices | 3 | 77.8% (27) | 76.7% | 88.0% / 91.7% |

On held-out data the LLM's specs match the specs written from the simulator's
real rules. The remaining disagreements are the person's own inconsistency,
which no spec can reproduce: sometimes using the recording date instead of the
bank date, forgetting reminders, holding off after a customer's promise. The
agent records payments a median of 1 day *earlier* than the person.

**Shadow mode over a year** (seed 7, 365 days, with the same specs, since the
first 80 days are identical to the sample):

| Agent | Path | Agreement by stage | Time saved |
|---|---|---|---|
| Send invoice email | shadow → draft (29 Apr) → approval (28 May) → autonomous (2 Jul) | 100% at every stage | 27.3 h |
| Record payment | shadow → draft (26 May, after 56 cases) → approval (29 Jun) → autonomous (30 Jul) | 91% / 100% / 100% / 94% | 13.6 h |
| Chase overdue invoices | stays in shadow | 67% | 0 h |

The chasing agent never earns trust, and that is correct. Chasing involves
judgment (promises, forgotten reminders, timing) that a rule-based spec doesn't
capture, so ShadowCost keeps it in shadow and keeps measuring.

Reproduce the year-long run:

```bash
shadowcost-synth --out data/demo-year --days 365
shadowcost-agent approve specs/W1.json --by "<name>"
shadowcost-agent shadow specs/W1.json data/demo-year
```

## Limitations

- **Time saved uses estimated minutes per case**, from discovery's stated
  assumptions, multiplied by an assumed share per stage. A real deployment
  should log how long people spend reviewing drafts and approving actions.
- **Approvals in the replay are counterfactual.** In the historical replay,
  "the person would have approved" means the person did the same thing. A live
  deployment would record real approve and reject clicks.
- **The spec language covers rules on a single spreadsheet row.** Work that
  needs reading free text (a customer's reply) or looking across rows (one
  payment for two invoices) isn't expressible yet. Those workflows correctly
  stay in shadow.
- **LLM output varies between runs.** Responses are cached by request hash,
  so a run can be reproduced, but a fresh draft can differ. That is why every
  draft is backtested and approved before it runs.

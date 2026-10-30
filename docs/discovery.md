# Discovery and recommendation: method and results

ShadowCost has to answer two questions from a small company's ordinary files:
*what work keeps repeating?* and *what is it worth automating?* There is no
event log and no timesheet. The inputs are spreadsheet snapshots, a bank export
and a mailbox, reduced by `ingest` to one event table.

## Method

**1. Email templates** (`discover/templates.py`). Sent emails are masked so
that what varies between instances doesn't count: ids, amounts, dates, and the
recipient's name, recognised because it echoes their address
(`billing@maple-vets.example` → "Maple Vets"). They are then clustered by cosine
distance on TF-IDF word 1–2 grams, using average-linkage agglomerative
clustering with a distance cut-off, so the number of templates isn't fixed in
advance.

**2. Episodes** (`discover/episodes.py`). Work means what the company itself did:
spreadsheet edits and sent emails. An episode is all the work on one case
(spreadsheet row) on one day, which is the finest grain at which a day-level
snapshot edit can be paired with an email. Its *signature* is the set of steps,
for example `{invoices.add, email.sent:T01}`.

**3. Workflows** (`discover/__init__.py`). Signatures that change mostly the same
spreadsheet columns (Jaccard ≥ 0.6) are merged, so a first reminder (which
also changes `status`) and a later one count as one workflow with two variants.
Groups with fewer than 8 instances are treated as one-off work.

**4. Triggers** (`discover/triggers.py`). Each group is tested against three
explanations of *when* it happens. The one that explains the most instances wins:

| Trigger | Test |
|---|---|
| event | an outside event (bank credit, received email) on the same case within 4 days before |
| new row | the work creates the case |
| schedule | ≥ 90% of instances fall on one or two weekdays, with a binomial test against an even spread (p < 0.01, Bonferroni-corrected) |

Groups that a trigger explains for at least 60% of instances are workflows. The
rest are reported as irregular repeated work. Scheduled work on existing rows
also gets a **date condition**: a one-column decision stump, "*column* at least
*N* days ago". It is fitted on the rows as they stood before each episode,
replayed from the event table. N is the 5th percentile of the instances' offsets,
and the column whose condition picks out worked-on rows most precisely is kept.
Status-like columns narrow the candidate rows only if that rules out at least
10% of them.

**5. Cost** (`recommend.py`). The data shows *that* work happened, not how long it
took. Time per instance is therefore an estimate from explicit per-step
assumptions (new row 3 min, row edit 1.5 min, templated email 4 min, finding the
row after a payment 2 min, +5 min when the payment had no usable reference), and
each recommendation prints the ones it used. A second figure comes from the
median gap between consecutive emails of the same workflow sent in one sitting.
It includes everything else done in between, so it is reported as an **upper
bound**. Workflows are ranked by *addressable hours*: hours per month ×
regularity × consistency, halved when the trigger is a free-text email that
someone has to interpret.

## Results

The template distance cut-off (0.75) was tuned on development seeds 1, 2 and 11.
The committed sample (seed 7) was held out and is used only for reporting.

**Held-out sample** (`shadowcost-discover data/sample --evaluate`, 4 months):

| Discovered | Ground truth | Purity | Coverage | Trigger found | True h | Estimated h | Upper bound h |
|---|---|---|---|---|---|---|---|
| W1 add invoice row + send invoice | send_invoice | 1.00 | 100% | new invoices row | 13.6 | 12.7 | 20.0 |
| W2 update [paid_date, status] | record_payment | 1.00 | 100% | bank credit, median 1 day before | 6.9 | 5.5 | – |
| W3 send reminder + update reminder fields | chase_overdue | 1.00 | 100% | Mondays and Thursdays; due_date ≥ 7 days ago, status not paid | 5.0 | 4.2 | 7.9 |

Workflow precision 1.00 and recall 1.00. Email templates have homogeneity
1.000: no template mixes two kinds of email. Completeness is 0.72 because
templates are deliberately finer than the ground truth's steps (first reminders,
second reminders and final notices are separate templates but one
`send_reminder` step).

The date condition recovered the simulator's real first-reminder rule (7 days
past due, unpaid) from the data alone. Its precision is 54%: of the unpaid rows
more than 7 days overdue on a chasing day, about half were chased. The rest
were reminded recently, had a payment promise, or the reminder was forgotten.
The spec step has to handle those cases.

**Development seeds** (default settings):

| Seed | Precision | Recall | Min coverage | Estimate error (invoice / payment / chase) |
|---|---|---|---|---|
| 1 | 1.00 | 1.00 | 97.5% | −9% / −25% / −17% |
| 2 | 1.00 | 1.00 | 98.6% | −8% / −23% / −17% |
| 3 | 0.75 | 1.00 | 98.6% | −8% / −22% / −14% |
| 11 | 1.00 | 1.00 | 97.5% | −7% / −25% / −17% |

## Known limitations

- **Precision on seed 3 is a labelling question.** The extra workflow is "note
  the customer's payment promise in the spreadsheet", set off by their reply.
  It *is* triggered and repeated. The simulator labels it ad hoc because it needs
  someone to read a free-text reply. ShadowCost flags it as needing judgment and
  ranks it last, but it still counts as a precision miss here.
- **The default time assumptions run 7–25% low** on the synthetic company. They are
  generic priors, deliberately not fitted to the simulator. The upper bound from
  email gaps was above the true time in every case. Real savings are measured
  later, in shadow mode.
- **The synthetic data is cooperative.** Each workflow has a clean spreadsheet
  footprint and one sender. Real companies will have several people editing the
  same sheet, renamed columns and one payment covering several invoices.
- **Template clustering is O(n²)** in emails, which is fine for a small
  company's mailbox but not for a large one.

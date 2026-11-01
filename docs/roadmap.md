# Roadmap

**Done** means one workflow running end to end (upload, discover, recommend,
generate spec, test, approve, shadow, promote, execute, report), shipped with a
public repo, README, architecture diagram, demo video and a live deployment.

## Milestones

- [x] **0. Foundation.** Repo, packaging, tests, shadow comparison, autonomy ladder.
- [x] **1. Synthetic company.** A data generator for a small company's invoice
      and payment-chasing work: an invoices spreadsheet over time, payment
      records and reminder emails, with a known ground truth for which work is
      repetitive. (`shadowcost.synth`; sample in `data/sample/`.)
- [x] **2. Ingest.** Normalize CSV/Excel, snapshots and email records into one
      event table. (`shadowcost.ingest`. On the sample: spreadsheet edits
      recovered with precision and recall 1.0, 80/80 recorded payments and
      180/180 emails linked to the right invoice. The synthetic data is cleaner
      than real exports, so a messier generator mode is a known follow-up.)
- [x] **3. Discover + recommend.** Find repeated workflows and rank them by
      cost. Evaluate discovery against the generator's ground truth
      (precision/recall). (`shadowcost.discover`, `shadowcost.recommend`;
      method and results in [discovery.md](discovery.md).)
- [x] **4. Spec + test.** Generate an agent spec with an LLM and replay it on
      historical cases. (`shadowcost.agent`, Groq `openai/gpt-oss-120b`. LLM
      specs match the true-rule reference on held-out days. See
      [agents.md](agents.md).)
- [x] **5. Shadow loop.** Persist cases, run the agent alongside new cases,
      compare outcomes and apply the autonomy ladder. (Approval gate and
      SQLite audit trail; over a year, two agents reach autonomy and the
      chasing agent correctly stays in shadow.)
- [ ] **6. Execute + report.** Stage-aware execution and a savings report with
      stated assumptions.
- [ ] **7. UI + API.** A web UI that runs the whole flow.
- [ ] **8. Ship.** Live deployment, demo video, polished README.

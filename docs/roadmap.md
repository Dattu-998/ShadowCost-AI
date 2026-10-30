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
- [ ] **2. Ingest.** Normalize CSV/Excel, snapshots and email records into one
      event table.
- [ ] **3. Discover + recommend.** Find repeated workflows and rank them by
      cost. Evaluate discovery against the generator's ground truth
      (precision/recall).
- [ ] **4. Spec + test.** Generate an agent spec with an LLM and replay it on
      historical cases.
- [ ] **5. Shadow loop.** Persist cases, run the agent alongside new cases,
      compare outcomes and apply the autonomy ladder.
- [ ] **6. Execute + report.** Stage-aware execution and a savings report with
      stated assumptions.
- [ ] **7. UI + API.** A web UI that runs the whole flow.
- [ ] **8. Ship.** Live deployment, demo video, polished README.

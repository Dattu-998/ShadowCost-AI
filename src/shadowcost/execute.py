"""Execute step: carry out an agent's proposals for a day, as its stage allows.

| Stage      | What happens to each proposal                                         |
|------------|-----------------------------------------------------------------------|
| shadow     | logged only; the person does the work as usual                       |
| draft      | email saved to ``outbox/drafts``; cell changes listed as suggestions |
| approval   | queued in the store until a person approves or rejects it            |
| autonomous | applied: cells written to a new copy of the sheet, email to ``outbox/ready`` |

Nothing is sent or overwritten from here. Emails are written as ``.eml`` files
for a mail client or a separate sending job to pick up, and spreadsheets are
written as new files in the workspace, never over the uploaded originals.
That keeps the blast radius of a wrong agent to files a person can inspect.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date
from email.message import EmailMessage
from pathlib import Path

import pandas as pd

from shadowcost.agent.runtime import Proposal, propose_day
from shadowcost.agent.spec import AgentSpec
from shadowcost.agent.store import Store, spec_id
from shadowcost.autonomy import Stage
from shadowcost.discover.episodes import RowHistory


@dataclass
class Execution:
    day: date
    stage: Stage
    proposals: list[Proposal]
    drafts: list[Path] = field(default_factory=list)
    ready: list[Path] = field(default_factory=list)
    queued: list[int] = field(default_factory=list)  # action ids awaiting a person
    suggestions: Path | None = None
    sheet: Path | None = None  # the spreadsheet after applied changes

    def summary(self) -> str:
        lines = [f"{self.day} at stage {self.stage.name}: {len(self.proposals)} proposals"]
        if self.stage == Stage.SHADOW and self.proposals:
            lines.append("  logged only (shadow mode)")
        if self.drafts:
            lines.append(f"  {len(self.drafts)} email drafts in {self.drafts[0].parent}")
        if self.suggestions:
            lines.append(f"  suggested cell changes in {self.suggestions}")
        if self.queued:
            lines.append(f"  {len(self.queued)} actions waiting for approval: ids {self.queued}")
        if self.ready:
            lines.append(f"  {len(self.ready)} emails ready to send in {self.ready[0].parent}")
        if self.sheet:
            lines.append(f"  updated spreadsheet written to {self.sheet}")
        return "\n".join(lines)


def execute_day(
    spec: AgentSpec,
    stage: Stage,
    day: date,
    events: pd.DataFrame,
    workspace: Path,
    store: Store,
    sender: str,
) -> Execution:
    rows = RowHistory(events).before(day)
    today = events[events["timestamp"].dt.date == day]
    proposals = [p for p in propose_day(spec, day, rows, today) if not p.error]
    run = Execution(day, stage, proposals)
    if stage == Stage.SHADOW or not proposals:
        return run

    if stage == Stage.DRAFT:
        run.drafts = [
            write_email(p.email, sender, workspace / "outbox" / "drafts", _name(spec, p))
            for p in proposals
            if p.email
        ]
        changes = [
            {"case_id": p.case_id, "column": col, "current": rows.get(p.case_id, {}).get(col, ""),
             "suggested": value, "rule": p.rule}
            for p in proposals
            for col, value in p.updates.items()
        ]  # fmt: skip
        if changes:
            run.suggestions = workspace / "suggestions" / f"{spec.workflow_id}_{day}.csv"
            run.suggestions.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(changes).to_csv(run.suggestions, index=False, lineterminator="\n")
    elif stage == Stage.APPROVAL:
        run.queued = [store.queue_action(spec, proposal_record(p)) for p in proposals]
    else:  # autonomous
        run.ready, run.sheet = apply(spec, proposals, rows, day, workspace, sender)
    return run


def apply_approved(
    spec: AgentSpec, events: pd.DataFrame, workspace: Path, store: Store, sender: str
) -> list[Execution]:
    """Apply every approved, not yet applied action for this spec, day by day."""
    applied = []
    by_day: dict[str, list[dict]] = {}
    for action in store.actions("approved"):
        if action["spec_id"] == spec_id(spec):
            by_day.setdefault(action["day"], []).append(action)
    for day_text, actions in sorted(by_day.items()):
        day = date.fromisoformat(day_text)
        proposals = [proposal_from_record(a["proposal"]) for a in actions]
        rows = RowHistory(events).before(day)
        ready, sheet = apply(spec, proposals, rows, day, workspace, sender)
        applied.append(Execution(day, Stage.APPROVAL, proposals, ready=ready, sheet=sheet))
        for a in actions:
            store.db.execute(
                "UPDATE actions SET status = 'applied' WHERE action_id = ?", (a["action_id"],)
            )
        store.db.commit()
    return applied


def apply(
    spec: AgentSpec,
    proposals: list[Proposal],
    rows: dict[str, dict],
    day: date,
    workspace: Path,
    sender: str,
) -> tuple[list[Path], Path | None]:
    ready = [
        write_email(p.email, sender, workspace / "outbox" / "ready", _name(spec, p))
        for p in proposals
        if p.email
    ]
    sheet = None
    if any(p.updates for p in proposals):
        updated = {case: dict(row) for case, row in rows.items()}
        for p in proposals:
            updated.setdefault(p.case_id, {}).update(p.updates)
        sheet = workspace / "sheets" / f"{spec.series}_{day}_{spec.workflow_id}.csv"
        sheet.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(list(updated.values())).to_csv(sheet, index=False, lineterminator="\n")
    return ready, sheet


def write_email(email: dict, sender: str, folder: Path, name: str) -> Path:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email["to"]
    message["Subject"] = email["subject"]
    message.set_content(email["body"])
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.eml"
    path.write_bytes(bytes(message))
    return path


def proposal_record(p: Proposal) -> dict:
    return asdict(p) | {"day": p.day.isoformat()}


def proposal_from_record(record: dict) -> Proposal:
    return Proposal(**(record | {"day": date.fromisoformat(record["day"])}))


def mailbox_owner(events: pd.DataFrame) -> str:
    """The address the company sends from: the most common sender of sent email."""
    sent = events[events["activity"] == "email.sent"]
    counts = Counter(sent["actor"])
    return counts.most_common(1)[0][0] if counts else "agent@localhost"


def _name(spec: AgentSpec, p: Proposal) -> str:
    return f"{p.day}_{spec.workflow_id}_{p.case_id}".replace("/", "-")


def stage_from_name(name: str) -> Stage:
    return Stage[name.upper()]

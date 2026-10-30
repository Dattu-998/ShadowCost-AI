"""Group work events into episodes and rebuild spreadsheet rows over time.

Work is what the company itself does: spreadsheet edits and sent emails. Bank
credits and received emails happen *to* the company and are only used as
possible triggers.

An episode is all the work done on one case on one day, such as "added the
invoice row and emailed the invoice". Snapshots only show edits by day, so a
day is the finest grain at which a spreadsheet edit and an email can be paired.
Its signature is the set of distinct steps, with sent emails identified by
their template, so episodes of the same kind of work share a signature.
"""

from __future__ import annotations

import bisect
from datetime import date

import pandas as pd


def work_events(events: pd.DataFrame) -> pd.DataFrame:
    is_sheet = events["source"] == "spreadsheet"
    # Rows in the first snapshot may have been created long before it, so their
    # "add" isn't evidence of work done that day.
    predates = is_sheet & events["payload"].map(lambda p: bool(p.get("first_snapshot")))
    return events[(is_sheet & ~predates) | (events["activity"] == "email.sent")]


def build_episodes(events: pd.DataFrame, template_of: dict[str, str]) -> pd.DataFrame:
    work = work_events(events).copy()
    work["step"] = [
        f"email.sent:{template_of[obj]}" if act == "email.sent" else act
        for act, obj in zip(work["activity"], work["object_id"], strict=True)
    ]
    work["day"] = work["timestamp"].dt.date
    # Work not tied to a case (an internal email) is an episode on its own.
    work["episode_key"] = [
        f"{case}|{day}" if case else f"solo|{event_id}"
        for case, day, event_id in zip(work["case_id"], work["day"], work["event_id"], strict=True)
    ]

    rows = []
    for _, group in work.groupby("episode_key", sort=False):
        rows.append(
            {
                "case_id": group["case_id"].iloc[0],
                "day": group["day"].iloc[0],
                "signature": tuple(sorted(set(group["step"]))),
                "event_ids": group["event_id"].tolist(),
            }
        )
    episodes = pd.DataFrame(rows, columns=["case_id", "day", "signature", "event_ids"])
    episodes = episodes.sort_values(["day", "case_id"], kind="stable").reset_index(drop=True)
    episodes.insert(0, "episode_id", [f"ep{i:05d}" for i in range(1, len(episodes) + 1)])
    return episodes


class RowHistory:
    """The state of every spreadsheet row at the end of each day, replayed from events.

    Rows are keyed by case id, so case ids are assumed unique across spreadsheets.
    """

    def __init__(self, events: pd.DataFrame):
        sheet = events[events["source"] == "spreadsheet"]
        self._days: list[date] = []
        self._states: list[dict[str, dict]] = []
        state: dict[str, dict] = {}
        for day, group in sheet.groupby(sheet["timestamp"].dt.date, sort=True):
            for activity, case_id, payload in zip(
                group["activity"], group["case_id"], group["payload"], strict=True
            ):
                verb = activity.split(".", 1)[1]
                if verb == "add":
                    state[case_id] = dict(payload["row"])
                elif verb == "remove":
                    state.pop(case_id, None)
                else:
                    for column, (_, new) in payload["changes"].items():
                        state.setdefault(case_id, {})[column] = new
            self._days.append(day)
            self._states.append({k: dict(v) for k, v in state.items()})

    def before(self, day: date) -> dict[str, dict]:
        """Every row as it stood before ``day``'s work: the last observed state before it."""
        i = bisect.bisect_left(self._days, day)
        return self._states[i - 1] if i > 0 else {}

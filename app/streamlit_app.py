"""ShadowCost web app: upload -> discover -> agents -> shadow mode -> execute -> report.

streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from shadowcost.agent.backtest import backtest
from shadowcost.agent.generate import generate_spec
from shadowcost.agent.shadow_mode import TIME_SAVED_SHARE, run_shadow
from shadowcost.agent.spec import AgentSpec
from shadowcost.agent.store import Store, spec_id
from shadowcost.api import extract_zip
from shadowcost.autonomy import Stage
from shadowcost.discover import discover
from shadowcost.execute import execute_day, mailbox_owner
from shadowcost.ingest import ingest_folder
from shadowcost.llm import ChatClient, load_dotenv
from shadowcost.recommend import recommend
from shadowcost.report import build_report
from shadowcost.synth import Config, simulate, write_dataset

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = Path(os.environ.get("SHADOWCOST_WORKSPACE", ROOT / "workspace"))
BUNDLED_SPECS = ROOT / "specs"
SAMPLE = ROOT / "data" / "sample"
STAGE_LABELS = {Stage.SHADOW: "Shadow", Stage.DRAFT: "Draft", Stage.APPROVAL: "Approval",
                Stage.AUTONOMOUS: "Autonomous"}  # fmt: skip

st.set_page_config(page_title="ShadowCost", page_icon="🕵️", layout="wide")
load_dotenv(ROOT / ".env")
try:  # Streamlit Cloud keeps secrets here rather than in .env
    os.environ.setdefault("GROQ_API_KEY", st.secrets["GROQ_API_KEY"])
except (KeyError, FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    pass


# --- cached steps ---------------------------------------------------------------------------


@st.cache_resource(show_spinner="Simulating a year of office work...")
def demo_year() -> Path:
    folder = WORKSPACE / "demo-year"
    if not (folder / "manifest.json").exists():
        write_dataset(simulate(Config(seed=7, days=365)), folder, overwrite=True)
    return folder


@st.cache_resource(show_spinner="Reading the files...")
def ingest(folder: str):
    return ingest_folder(folder)


@st.cache_resource(show_spinner="Looking for repeated work...")
def discovered(folder: str, train_days: int):
    events = ingest(folder).events
    split = events["timestamp"].min().date() + timedelta(days=train_days)
    discovery = discover(events[events["timestamp"].dt.date < split])
    return discovery, recommend(discovery), split


@st.cache_data(show_spinner="Replaying held-out days...")
def backtest_metrics(folder: str, spec_json: str, start, end) -> dict:
    spec = AgentSpec.from_dict(json.loads(spec_json))
    return backtest(spec, ingest(folder).events, start, end).metrics()


@st.cache_resource(show_spinner="Running shadow mode...")
def shadow_run(folder: str, spec_json: str, start, end, minutes: float):
    spec = AgentSpec.from_dict(json.loads(spec_json))
    return run_shadow(spec, ingest(folder).events, start, end, minutes)


def store() -> Store:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return Store(WORKSPACE / "shadowcost.db")


# --- sidebar: choose data -------------------------------------------------------------------

st.sidebar.title("ShadowCost")
st.sidebar.caption("Agents that prove themselves against real human work before they get autonomy.")
choice = st.sidebar.radio(
    "Data",
    ["Sample: 4 months (bundled)", "Simulated year", "Upload a zip"],
    help="The simulated company is Fernhill Supplies: invoices, payments and reminder emails.",
)
if choice.startswith("Sample"):
    folder, specs_dir = SAMPLE, BUNDLED_SPECS
elif choice == "Simulated year":
    folder, specs_dir = demo_year(), BUNDLED_SPECS
else:
    upload = st.sidebar.file_uploader("Zip of spreadsheets, bank export and email log", type="zip")
    if upload is None:
        st.info("Upload a zip with spreadsheet snapshots (dated file names), a bank export and an "
                "email log (.jsonl), or pick the sample in the sidebar.")  # fmt: skip
        st.stop()
    data = upload.getvalue()
    digest = hashlib.sha256(data).hexdigest()[:12]
    folder = WORKSPACE / "datasets" / digest
    if not folder.exists():
        try:
            extract_zip(data, folder)
        except Exception as err:  # noqa: BLE001 - shown to the user
            st.error(f"Could not use that zip: {err}")
            st.stop()
    specs_dir = WORKSPACE / "specs" / digest

train_days = st.sidebar.slider("Days of history to learn from", 30, 120, 80, step=10)
has_key = bool(os.environ.get("GROQ_API_KEY"))
st.sidebar.caption(("🟢" if has_key else "⚪") + " LLM (Groq) " + ("connected" if has_key else
                   "not configured: bundled specs only"))  # fmt: skip

result = ingest(str(folder))
events = result.events
if events.empty:
    st.error("No usable events in these files.")
    st.stop()
discovery, recommendations, split = discovered(str(folder), train_days)
last_day = events["timestamp"].max().date()


def load_specs() -> list[tuple[AgentSpec, dict]]:
    out = []
    for path in sorted(specs_dir.glob("*.json")) if specs_dir.exists() else []:
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append((AgentSpec.from_dict(data), data.get("evaluation", {})))
    return out


def as_json(spec: AgentSpec) -> str:
    return json.dumps(spec.to_dict(), sort_keys=True)


tabs = st.tabs(["Overview", "1 Discover", "2 Agents", "3 Shadow mode", "4 Execute", "5 Report"])

# --- overview -------------------------------------------------------------------------------

with tabs[0]:
    st.title("ShadowCost")
    st.markdown(
        "ShadowCost finds repetitive spreadsheet and email work in small companies, drafts an "
        "agent for each workflow, and makes the agent **prove itself in shadow mode** against "
        "what the person actually did before it gets autonomy: draft only, then act with "
        "approval, then act alone."
    )
    st.caption("upload → discover → recommend → generate spec → test → approve → shadow → "
               "promote → execute → report")  # fmt: skip
    c = st.columns(4)
    c[0].metric("Files", len(result.files))
    c[1].metric("Events", f"{len(events):,}")
    c[2].metric("Period", f"{(last_day - events['timestamp'].min().date()).days + 1} days")
    c[3].metric("Linked to a case", f"{(events['case_id'] != '').mean():.0%}")
    st.subheader("Events by source")
    st.bar_chart(events["source"].value_counts())
    st.subheader("A few events")
    st.dataframe(
        events[["timestamp", "source", "activity", "case_id", "link_method", "actor"]].head(200),
        use_container_width=True, hide_index=True,
    )  # fmt: skip
    for warning in result.warnings:
        st.warning(warning)

# --- discover -------------------------------------------------------------------------------

with tabs[1]:
    st.header("Repeated work")
    st.caption(f"Learned from {events['timestamp'].min().date()} to {split - timedelta(days=1)}. "
               "Time per case is an estimate; the assumptions are listed for each workflow.")  # fmt: skip
    if not recommendations:
        st.info("No repeated workflows found in this period.")
    table = pd.DataFrame(
        [
            {
                "Id": r.workflow.workflow_id,
                "Work": r.workflow.name,
                "When": r.workflow.trigger.description,
                "Per month": r.instances_per_month,
                "Min each": r.minutes_per_instance,
                "Hours/month": r.hours_per_month,
                "Automation score": r.automation_score,
            }
            for r in recommendations
        ]
    )
    st.dataframe(table, use_container_width=True, hide_index=True)
    for r in recommendations:
        w = r.workflow
        with st.expander(f"{w.workflow_id}: {w.name}"):
            st.write(f"**Trigger:** {w.trigger.description} ({w.regularity:.0%} of {w.size} cases)")
            if w.condition:
                st.write(f"**Condition:** {w.condition.description} (covers "
                         f"{w.condition.support:.0%}, precision {w.condition.precision:.0%})")  # fmt: skip
            st.write("**Assumptions:** " + "; ".join(r.assumptions))
            for caveat in r.caveats:
                st.warning(caveat)
            st.write("**Variants:**")
            st.dataframe(pd.DataFrame([{"steps": " + ".join(s), "cases": n} for s, n in w.variants]),
                         hide_index=True)  # fmt: skip

# --- agents ---------------------------------------------------------------------------------

with tabs[2]:
    st.header("Agents: draft, test, approve")
    specs = load_specs()
    if has_key and st.button("Draft agents with the LLM", disabled=not recommendations):
        specs_dir.mkdir(parents=True, exist_ok=True)
        minutes = {r.workflow.workflow_id: r.minutes_per_instance for r in recommendations}
        for w in discovery.workflows:
            with st.spinner(f"Drafting {w.workflow_id}..."):
                g = generate_spec(discovery, w, ChatClient(cache_dir=WORKSPACE / "llm-cache"))
            if g.spec is None:
                st.error(f"{w.workflow_id}: no valid spec ({'; '.join(g.problems[:3])})")
                continue
            data = g.spec.to_dict() | {"evaluation": {"minutes_per_case": minutes[w.workflow_id]}}
            (specs_dir / f"{w.workflow_id}.json").write_text(json.dumps(data, indent=2))
        st.rerun()
    if not specs:
        st.info("No agents yet. " + ("Draft them with the LLM above." if has_key else
                "Set GROQ_API_KEY to draft agents for your own data."))  # fmt: skip
    db = store()
    for spec, _ in specs:
        start = split
        metrics = backtest_metrics(str(folder), as_json(spec), start, last_day)
        approval = db.approval(spec)
        with st.container(border=True):
            left, right = st.columns([3, 2])
            left.subheader(f"{spec.workflow_id}: {spec.name}")
            left.write(spec.summary)
            left.caption(f"Drafted by {spec.source.get('generated_by', 'hand')}; "
                         f"id {spec_id(spec)}")  # fmt: skip
            m = right.columns(3)
            m[0].metric("Held-out agreement", f"{metrics['agreement']:.0%}")
            m[1].metric("Precision", f"{metrics['action_precision']:.0%}")
            m[2].metric("Recall", f"{metrics['action_recall']:.0%}")
            right.caption(f"{metrics['outcomes']} cases from {start} to {last_day}: "
                          f"{metrics['kinds']}")  # fmt: skip
            with st.expander("Rules"):
                for rule in spec.rules:
                    st.markdown(f"**{rule.name}**")
                    st.write("when " + (", ".join(f"`{c.column} {c.op} {c.value if c.value is not None else ''}`"
                                                  for c in rule.when) or "always"))  # fmt: skip
                    if rule.set:
                        st.write("set " + ", ".join(f"`{k} = {v}`" for k, v in rule.set.items()))
                    if rule.email:
                        st.code(f"To: {rule.email.to}\nSubject: {rule.email.subject}\n\n"
                                f"{rule.email.body}", language="text")  # fmt: skip
            if approval:
                st.success(f"Approved by {approval[0]} at {approval[1]}")
            else:
                name = st.text_input("Your name", key=f"name-{spec_id(spec)}")
                if st.button(
                    "Approve this agent", key=f"approve-{spec_id(spec)}", disabled=not name
                ):
                    db.approve(spec, name)
                    st.rerun()

# --- shadow mode ----------------------------------------------------------------------------

with tabs[3]:
    st.header("Shadow mode: earning autonomy")
    st.caption("Each case is compared with what the person did. 30 cases with a 95% lower bound "
               "of agreement ≥ 0.85 earn the next stage; evidence restarts at each stage.")  # fmt: skip
    approved = [(s, e) for s, e in load_specs() if db.approval(s)]
    if not approved:
        st.info("Approve an agent first (tab 2).")
    for spec, evaluation in approved:
        minutes = evaluation.get("minutes_per_case") or 5.0
        run = shadow_run(str(folder), as_json(spec), split, last_day, minutes)
        st.subheader(f"{spec.workflow_id}: {spec.name}: {STAGE_LABELS[run.final_stage]}")
        points = [{"day": split, "stage": 0}] + [
            {"day": c.day, "stage": int(c.decision.next)} for c in run.changes
        ] + [{"day": last_day, "stage": int(run.final_stage)}]  # fmt: skip
        chart = (
            alt.Chart(pd.DataFrame(points))
            .mark_line(interpolate="step-after", strokeWidth=3)
            .encode(
                x=alt.X("day:T", title=None),
                y=alt.Y("stage:Q", title=None, scale=alt.Scale(domain=[0, 3]),
                        axis=alt.Axis(values=[0, 1, 2, 3], labelExpr=
                        "['Shadow','Draft','Approval','Autonomous'][datum.value]")),
            )
            .properties(height=180)
        )  # fmt: skip
        st.altair_chart(chart, use_container_width=True)
        c = st.columns(3)
        c[0].metric("Cases", len(run.outcomes))
        c[1].metric(
            "Agreement", f"{sum(o.agrees for o, _ in run.outcomes) / max(len(run.outcomes), 1):.0%}"
        )
        c[2].metric("Hours saved (est.)", f"{run.minutes_saved() / 60:.1f}")
        if run.changes:
            st.dataframe(pd.DataFrame([{"day": ch.day, "change": f"{ch.decision.action} to "
                                        f"{STAGE_LABELS[ch.decision.next]}", "why": ch.decision.reason}
                                       for ch in run.changes]), hide_index=True)  # fmt: skip
        if st.button("Save this run to the audit trail", key=f"save-{spec_id(spec)}"):
            st.success(f"Saved as run {db.save_run(run)}")
    st.caption("Time saved per agreeing case, by stage: " + ", ".join(
        f"{STAGE_LABELS[s]} {v:.0%}" for s, v in TIME_SAVED_SHARE.items()))  # fmt: skip

# --- execute --------------------------------------------------------------------------------

with tabs[4]:
    st.header("Execute a day")
    st.caption("Drafts and approved actions go to an outbox and to new copies of the sheet in "
               "the workspace. Nothing is sent or overwritten.")  # fmt: skip
    approved = [s for s, _ in load_specs() if db.approval(s)]
    if not approved:
        st.info("Approve an agent first (tab 2).")
    else:
        names = {f"{s.workflow_id}: {s.name}": s for s in approved}
        spec = names[st.selectbox("Agent", list(names))]
        c = st.columns(2)
        day = c[0].date_input("Day", value=split, min_value=split, max_value=last_day)
        stage = Stage[c[1].selectbox("Stage", [s.name for s in Stage], index=1)]
        if st.button("Run"):
            run = execute_day(spec, stage, day, events, WORKSPACE / "outbox-demo", db,
                              mailbox_owner(events))  # fmt: skip
            st.write(f"{len(run.proposals)} proposals at stage {STAGE_LABELS[stage]}.")
            for p in run.proposals:
                with st.container(border=True):
                    st.write(f"**{p.case_id}** ({p.rule})")
                    if p.updates:
                        st.write(", ".join(f"`{k} → {v}`" for k, v in p.updates.items()))
                    if p.email:
                        st.code(f"To: {p.email['to']}\nSubject: {p.email['subject']}\n\n"
                                f"{p.email['body']}", language="text")  # fmt: skip
        pending = db.actions("pending")
        if pending:
            st.subheader(f"Waiting for approval ({len(pending)})")
            for a in pending:
                cols = st.columns([4, 1, 1])
                p = a["proposal"]
                cols[0].write(f"#{a['action_id']} {a['day']} {a['case_id']}: {p['rule']}")
                if cols[1].button("Approve", key=f"ok-{a['action_id']}"):
                    db.decide(a["action_id"], True, "web")
                    st.rerun()
                if cols[2].button("Reject", key=f"no-{a['action_id']}"):
                    db.decide(a["action_id"], False, "web")
                    st.rerun()

# --- report ---------------------------------------------------------------------------------

with tabs[5]:
    st.header("Savings report")
    specs = load_specs()
    if not specs:
        st.info("No agents to report on yet.")
    elif st.button("Build report"):
        with st.spinner("Building the report..."):
            report = build_report(folder, specs, train_days)
        st.download_button("Download HTML", report.html(), "shadowcost-report.html", "text/html")
        st.markdown(report.markdown())

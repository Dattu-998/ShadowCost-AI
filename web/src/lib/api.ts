/**
 * Typed client for the ShadowCost API (FastAPI on Render). The free plan sleeps when idle, so
 * a first request can take about a minute; `useSlowRequests` lets the shell say so honestly.
 */
import { useSyncExternalStore } from "react";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type Stage = "shadow" | "draft" | "approval" | "autonomous";
export const STAGES: Stage[] = ["shadow", "draft", "approval", "autonomous"];

export type DatasetSummary = {
  dataset_id: string;
  name: string;
  files: Record<string, number>;
  events: number;
  first_day: string | null;
  last_day: string | null;
  by_source: Record<string, number>;
  linked_share: number;
  weekly: ({ week: string } & Record<string, number | string>)[];
  has_ground_truth: boolean;
  warnings: string[];
};

export type EventRow = {
  event_id: string;
  timestamp: string;
  source: "spreadsheet" | "bank" | "email";
  activity: string;
  case_id: string;
  link_method: string;
  actor: string;
  detail: string;
};

export type Workflow = {
  workflow_id: string;
  name: string;
  instances: number;
  instances_per_week: number;
  instances_per_month: number;
  trigger: { kind: string; description: string; support: number };
  condition: { description: string; support: number; precision: number } | null;
  variants: { steps: string[]; count: number }[];
  regularity: number;
  consistency: number;
  minutes_per_instance: number;
  observed_minutes: number | null;
  hours_per_month: number;
  automation_score: number;
  addressable_hours_per_month: number;
  assumptions: string[];
  caveats: string[];
};

export type Discovery = {
  evidence_from: string;
  evidence_to: string;
  episodes: number;
  templates: number;
  workflows: Workflow[];
  irregular: { name: string; instances: number }[];
};

export type Condition = { column: string; op: string; value?: unknown };
export type Rule = {
  name: string;
  when: Condition[];
  set: Record<string, string>;
  email?: { to: string; subject: string; body: string };
};
export type BacktestMetrics = {
  outcomes: number;
  kinds: Record<string, number>;
  agreement: number;
  agreement_lower_bound: number;
  action_precision: number;
  action_recall: number;
  field_agreement: Record<string, number>;
  median_days_ahead_of_human: number | null;
};
export type Spec = {
  workflow_id: string;
  name: string;
  summary: string;
  series: string;
  trigger: { kind: string; weekdays?: number[]; activity?: string };
  rules: Rule[];
  source: {
    generated_by?: string;
    evidence_period?: [string, string];
    attempts?: number;
    notes?: string[];
  };
  evaluation?: {
    minutes_per_case: number;
    evidence_period: BacktestMetrics;
    held_out: BacktestMetrics & { from: string; to: string };
  };
};
export type SpecEntry = {
  spec_id: string;
  spec: Spec;
  approved_by: string | null;
  approved_at: string | null;
};

export type ShadowRun = {
  run_id: number;
  from: string;
  to: string;
  cases: number;
  final_stage: Stage;
  changes: {
    day: string;
    action: "promote" | "demote";
    from: Stage;
    to: Stage;
    reason: string;
    cases: number;
    agreement: number;
    lower_bound: number;
  }[];
  by_stage: Partial<Record<Stage, { cases: number; agreement: number }>>;
  points: { day: string; stage: Stage; agrees: boolean; kind: string; agreement_so_far: number }[];
  minutes_per_case: number;
  hours_saved_estimated: number;
  policy: { min_cases: number; promote_lower_bound: number; time_saved_share: Record<Stage, number> };
};

export type Backtest = BacktestMetrics & {
  from: string;
  to: string;
  examples: {
    case_id: string;
    kind: string;
    agent_day: string | null;
    human_day: string | null;
    rule: string;
    differing: string[];
  }[];
};

export type Proposal = {
  case_id: string;
  rule: string;
  updates: Record<string, string>;
  email: { to: string; subject: string; body: string } | null;
};
export type Execution = {
  day: string;
  stage: Stage;
  proposals: Proposal[];
  drafts: number;
  queued: number[];
  ready: number;
  sheet_written: boolean;
};
export type QueuedAction = {
  action_id: number;
  spec_id: string;
  case_id: string;
  day: string;
  proposal: Proposal & { day: string };
  status: string;
  decided_by: string | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

// --- slow-request tracking (the server may be waking up) -------------------------------------

let slow = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function useSlowRequests(): boolean {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => slow > 0,
    () => false,
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let marked = false;
  const timer = setTimeout(() => {
    marked = true;
    slow++;
    emit();
  }, 4000);
  try {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch {
        // keep the status text
      }
      throw new ApiError(detail, response.status);
    }
    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(`Could not reach the API at ${API_URL}.`, 0);
  } finally {
    clearTimeout(timer);
    if (marked) {
      slow--;
      emit();
    }
  }
}

export const get = <T>(path: string) => request<T>(path);
export const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

/** SWR fetcher: a string key is a GET; ["POST", path, body] is a POST. */
export function fetcher<T>(key: string | readonly [string, string, unknown]): Promise<T> {
  if (typeof key === "string") return get<T>(key);
  return post<T>(key[1], key[2]);
}

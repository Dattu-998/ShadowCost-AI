"use client";

import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";
import useSWR from "swr";
import {
  fetcher,
  post,
  ROLE_RANK,
  type Backtest,
  type DatasetRow,
  type DatasetSummary,
  type Execution,
  type Me,
  type OrgDetail,
  type Role,
  type SpecEntry,
  type Stage,
} from "@/lib/api";

/*
 * One set of screens, two kinds of workspace:
 * - demo: the public Fernhill Supplies sample or simulated year, no account needed;
 * - org: a signed-in customer's workspace and their own datasets.
 * Each provides the same `api` adapter, so a screen never needs to know which it's in.
 */

export type Mode = "demo" | "org";
type Key = readonly [string, string, unknown];

export type Api = {
  summary: string | null;
  events: (limit: number) => string | null;
  workflows: string | null;
  specs: string | null;
  approve: (entry: SpecEntry) => Promise<unknown>;
  backtest: (entry: SpecEntry) => Promise<Backtest>;
  shadowKey: (entry: SpecEntry) => Key | null;
  execute: (entry: SpecEntry, day: string, stage: Stage) => Promise<Execution>;
  actions: string | null;
  decide: (actionId: number, approve: boolean) => Promise<unknown>;
  report: (specs: SpecEntry[]) => Promise<{ markdown: string; html: string }>;
};

type Workspace = {
  mode: Mode;
  base: "/demo" | "/app";
  name: string;
  dataset: string | null;
  setDataset: (id: string) => void;
  datasets: { id: string; label: string; detail?: string }[];
  approver: string;
  setApprover: (name: string) => void;
  org: OrgDetail | null;
  workspaces: Me["workspaces"];
  role: Role;
  can: (minimum: Role) => boolean;
  api: Api;
};

const Context = createContext<Workspace | null>(null);

export function useWorkspace(): Workspace {
  const value = useContext(Context);
  if (!value) throw new Error("useWorkspace outside a workspace provider");
  return value;
}

// --- per-browser memory (the landing page's form writes the demo choices) ----------------------

const listeners = new Set<() => void>();
function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
export function remember(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage unavailable: the choice lasts until reload
  }
  listeners.forEach((l) => l());
}
export function usePersisted(key: string, fallback: string): string {
  return useSyncExternalStore(subscribe, () => read(key) ?? fallback, () => fallback);
}

// --- demo ----------------------------------------------------------------------------------------

export const DEMO_DATASETS = [
  { id: "sample", label: "4 months", detail: "the bundled sample" },
  { id: "year", label: "A full year", detail: "simulated, generated on first use" },
];

export function DemoWorkspaceProvider({ children }: { children: ReactNode }) {
  const stored = usePersisted("shadowcost.dataset", "sample");
  const dataset = stored === "year" ? "year" : "sample";
  const approver = usePersisted("shadowcost.approver", "Office manager");
  const value = useMemo<Workspace>(() => {
    const d = `/datasets/${dataset}`;
    return {
      mode: "demo",
      base: "/demo",
      name: "Fernhill Supplies",
      dataset,
      setDataset: (id) => remember("shadowcost.dataset", id),
      datasets: DEMO_DATASETS,
      approver,
      setApprover: (name) => remember("shadowcost.approver", name),
      org: null,
      workspaces: [],
      role: "owner",
      can: () => true,
      api: {
        summary: d,
        events: (limit) => `${d}/events?limit=${limit}`,
        workflows: `${d}/workflows?train_days=80`,
        specs: "/specs",
        approve: (e) => post("/specs/approve", { spec: e.spec, by: approver || "Office manager" }),
        backtest: (e) => post<Backtest>(`${d}/backtest`, { spec: e.spec }),
        shadowKey: (e) => (e.approved_by ? (["POST", `${d}/shadow`, { spec: e.spec }] as const) : null),
        execute: (e, day, stage) => post<Execution>(`${d}/execute`, { spec: e.spec, day, stage }),
        actions: "/actions",
        decide: (id, approve) =>
          post(`/actions/${id}/decision`, { approve, by: approver || "Office manager" }),
        report: (specs) =>
          post(`${d}/report`, { specs: specs.map((s) => s.spec), train_days: 80 }),
      },
    };
  }, [dataset, approver]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

// --- signed-in workspace -------------------------------------------------------------------------

export function OrgWorkspaceProvider({ me, children }: { me: Me; children: ReactNode }) {
  const storedOrg = usePersisted("shadowcost.org", "");
  const orgId = me.workspaces.some((w) => w.id === storedOrg) ? storedOrg : me.workspaces[0].id;
  const org = useSWR<OrgDetail>(`/v1/orgs/${orgId}`, fetcher);
  const datasets = useSWR<DatasetRow[]>(`/v1/orgs/${orgId}/datasets`, fetcher, {
    refreshInterval: (rows) => (rows?.some((r) => r.status === "processing") ? 3000 : 0),
  });
  const storedDataset = usePersisted(`shadowcost.dataset.${orgId}`, "");
  const ready = (datasets.data ?? []).filter((d) => d.status === "ready");
  const dataset = ready.some((d) => d.id === storedDataset) ? storedDataset : (ready[0]?.id ?? null);
  const role: Role = org.data?.role ?? me.workspaces.find((w) => w.id === orgId)?.role ?? "viewer";

  const value = useMemo<Workspace>(() => {
    const o = `/v1/orgs/${orgId}`;
    const d = dataset ? `${o}/datasets/${dataset}` : null;
    return {
      mode: "org",
      base: "/app",
      name: org.data?.name ?? me.workspaces.find((w) => w.id === orgId)?.name ?? "Workspace",
      dataset,
      setDataset: (id) => remember(`shadowcost.dataset.${orgId}`, id),
      datasets: ready.map((r) => ({ id: r.id, label: r.name, detail: r.source })),
      approver: me.user.email,
      setApprover: () => undefined,
      org: org.data ?? null,
      workspaces: me.workspaces,
      role,
      can: (minimum) => ROLE_RANK[role] >= ROLE_RANK[minimum],
      api: {
        summary: d,
        events: (limit) => (d ? `${d}/events?limit=${limit}` : null),
        workflows: d ? `${d}/workflows` : null,
        specs: dataset ? `${o}/agents?dataset_id=${dataset}` : null,
        approve: (e) => post(`${o}/agents/${e.spec_id}/approve`),
        backtest: (e) => post<Backtest>(`${o}/agents/${e.spec_id}/backtest`, { dataset_id: dataset }),
        shadowKey: (e) =>
          e.approved_by && dataset
            ? (["POST", `${o}/agents/${e.spec_id}/shadow`, { dataset_id: dataset }] as const)
            : null,
        execute: (e, day, stage) =>
          post<Execution>(`${o}/agents/${e.spec_id}/execute`, { dataset_id: dataset, day, stage }),
        actions: `${o}/actions`,
        decide: (id, approve) => post(`${o}/actions/${id}/decision`, { approve }),
        report: () => post(`${d}/report`),
      },
    };
  }, [orgId, dataset, org.data, ready, me, role]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

// --- data hooks shared by the screens ------------------------------------------------------------

export function useDataset() {
  const { api } = useWorkspace();
  return useSWR<DatasetSummary>(api.summary, fetcher);
}

export function useSpecs() {
  const { api } = useWorkspace();
  return useSWR<SpecEntry[]>(api.specs, fetcher);
}

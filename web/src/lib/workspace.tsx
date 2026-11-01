"use client";

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";
import useSWR from "swr";
import { fetcher, type DatasetSummary, type SpecEntry } from "@/lib/api";

/** Which data the app is looking at and who signs approvals. Remembered per browser. */
export const DATASETS = [
  { id: "sample", label: "4 months", detail: "the bundled sample" },
  { id: "year", label: "A full year", detail: "simulated, generated on first use" },
] as const;
export type DatasetId = (typeof DATASETS)[number]["id"];

type Workspace = {
  dataset: DatasetId;
  setDataset: (id: DatasetId) => void;
  approver: string;
  setApprover: (name: string) => void;
};

const Context = createContext<Workspace | null>(null);

// Browser storage as an external store: the landing page's form writes it, the app reads it.
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
    return null; // storage unavailable: defaults stand
  }
}
function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // the choice then lasts until reload
  }
  listeners.forEach((l) => l());
}
function usePersisted(key: string, fallback: string): string {
  return useSyncExternalStore(subscribe, () => read(key) ?? fallback, () => fallback);
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const stored = usePersisted("shadowcost.dataset", "sample");
  const dataset: DatasetId = stored === "year" ? "year" : "sample";
  const approver = usePersisted("shadowcost.approver", "Office manager");
  const value: Workspace = {
    dataset,
    setDataset: (id) => write("shadowcost.dataset", id),
    approver,
    setApprover: (name) => write("shadowcost.approver", name),
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useWorkspace(): Workspace {
  const value = useContext(Context);
  if (!value) throw new Error("useWorkspace outside WorkspaceProvider");
  return value;
}

export function useDataset() {
  const { dataset } = useWorkspace();
  return useSWR<DatasetSummary>(`/datasets/${dataset}`, fetcher);
}

export function useSpecs() {
  return useSWR<SpecEntry[]>("/specs", fetcher);
}

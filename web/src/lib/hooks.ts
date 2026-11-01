"use client";

import useSWR, { useSWRConfig } from "swr";
import { fetcher, post, type Discovery, type ShadowRun, type SpecEntry } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

export const TRAIN_DAYS = 80;

export function useDiscovery() {
  const { dataset } = useWorkspace();
  return useSWR<Discovery>(`/datasets/${dataset}/workflows?train_days=${TRAIN_DAYS}`, fetcher);
}

/** The shadow run for an approved spec on the current data; nothing for unapproved specs. */
export function useShadowRun(entry: SpecEntry | undefined) {
  const { dataset } = useWorkspace();
  const key =
    entry && entry.approved_by
      ? (["POST", `/datasets/${dataset}/shadow`, { spec: entry.spec }] as const)
      : null;
  return useSWR<ShadowRun>(key, fetcher, { revalidateOnFocus: false });
}

export function useApprove() {
  const { approver } = useWorkspace();
  const { mutate } = useSWRConfig();
  return async (entry: SpecEntry) => {
    await post("/specs/approve", { spec: entry.spec, by: approver || "Office manager" });
    await mutate("/specs");
  };
}

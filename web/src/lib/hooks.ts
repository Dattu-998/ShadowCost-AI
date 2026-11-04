"use client";

import useSWR, { useSWRConfig } from "swr";
import { fetcher, type Discovery, type ShadowRun, type SpecEntry } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

export const TRAIN_DAYS = 80;

export function useDiscovery() {
  const { api } = useWorkspace();
  return useSWR<Discovery>(api.workflows, fetcher);
}

/** The shadow run for an approved spec on the current data; nothing for unapproved specs. */
export function useShadowRun(entry: SpecEntry | undefined) {
  const { api } = useWorkspace();
  return useSWR<ShadowRun>(entry ? api.shadowKey(entry) : null, fetcher, {
    revalidateOnFocus: false,
  });
}

export function useApprove() {
  const { api } = useWorkspace();
  const { mutate } = useSWRConfig();
  return async (entry: SpecEntry) => {
    await api.approve(entry);
    await mutate(api.specs);
  };
}

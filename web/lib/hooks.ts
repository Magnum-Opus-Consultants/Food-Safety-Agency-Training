"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { api, ApiError, Envelope } from "./api";
import { findNav } from "./nav";

export type Me = {
  ref: string; name: string; position: string; role: string; roleLabel: string;
  segments: string[]; writes: string[]; canMoveClock: boolean;
};

export function useScreen() {
  return findNav(usePathname())?.item.screen ?? "";
}

/** Register reads: always fresh (staleTime 0), refetched on every mount and navigation. */
export function useRegister<T>(path: string, enabled = true) {
  return useQuery<Envelope<T>, ApiError>({ queryKey: [path], queryFn: () => api<T>(path), enabled });
}

export function useMe() {
  return useQuery<Envelope<Me>, ApiError>({ queryKey: ["/me"], queryFn: () => api<Me>("/me"), retry: false });
}

/** A state-changing action. On success every query is invalidated so the rail's badges,
 *  the screen's register and its audit trail all re-read from the registers. On refusal the
 *  reasons are kept for <Blocked/> to render verbatim. */
export function useAction<TBody = unknown, TData = unknown>(method: string, path: string | ((v: TBody) => string)) {
  const qc = useQueryClient();
  const screen = useScreen();
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  const m = useMutation<Envelope<TData>, ApiError, TBody>({
    mutationFn: (body: TBody) =>
      api<TData>(typeof path === "function" ? path(body) : path, { method, body: body ?? {}, screen }),
    onMutate: () => setRefusal(null),
    onSuccess: () => qc.invalidateQueries(),
    onError: (e) => setRefusal(e),
  });
  return { ...m, refusal, clear: () => setRefusal(null) };
}

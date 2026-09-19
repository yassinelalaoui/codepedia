/**
 * Calls to the hub's API (contracts/hub-http-api.md).
 *
 * Every state-changing call carries the token in a header. `apiToken.ts` is
 * reused unchanged from the wiki: it already reads `?token=` on first load,
 * moves it into `localStorage`, and strips it from the address bar - exactly
 * the handling the homepage needs, and for the same reason.
 */

import { apiTokenHeaders, currentApiToken } from "./apiToken";

export interface StageState {
  name: string;
  label: string;
  status: "pending" | "running" | "done" | "failed";
  completed: number | null;
  total: number | null;
  elapsedSeconds: number | null;
}

export interface ProviderSwitch {
  chain: string | null;
  fromProvider: string | null;
  toProvider: string | null;
  reason: string | null;
  at: string;
}

export interface RunSnapshot {
  runId: string;
  kind: "index" | "open";
  repositoryPath: string;
  stages: StageState[];
  currentStage: string | null;
  providerSwitches: ProviderSwitch[];
  notices: string[];
  catchup: { phase: string; completed: number; total: number; path: string } | null;
  outcome: "succeeded" | "failed" | "cancelled" | null;
  failedStage: string | null;
  failureMessage: string | null;
  providersAttempted: string[];
  serverUrl: string | null;
  startedAt: string;
  endedAt: string | null;
  version: number;
  discardedEverything: boolean;
}

export interface HistoryEntry {
  stateId: string;
  repositoryPath: string;
  lastIndexedAt: string | null;
  available: boolean;
}

export interface RunRecord {
  runId: string;
  repositoryPath: string;
  kind: string;
  startedAt: string;
  endedAt: string | null;
  outcome: string | null;
  failedStage: string | null;
  failureMessage: string | null;
  providersAttempted: string[];
}

export class HubApiError extends Error {
  readonly kind: string;
  readonly status: number;

  constructor(kind: string, message: string, status: number) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...apiTokenHeaders(),
      ...(init.headers ?? {}),
    },
  });

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    // The server's own message, verbatim. It was written to be read by a person
    // in a browser with no terminal open (spec SC-004), so replacing it with a
    // generic one here would throw away the only useful part.
    const error = body?.error;
    throw new HubApiError(
      error?.kind ?? "error",
      error?.message ?? `Request failed (${response.status}).`,
      response.status,
    );
  }
  return body as T;
}

export const hubApi = {
  startRun: (path: string) =>
    request<{ runId: string; repositoryPath: string }>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  currentRun: () => request<{ run: RunSnapshot | null }>("/api/runs/current"),

  cancelRun: () => request<{ run: RunSnapshot }>("/api/runs/current/cancel", { method: "POST" }),

  dismissRun: () => request<void>("/api/runs/current/dismiss", { method: "POST" }),

  repositories: () => request<{ repositories: HistoryEntry[] }>("/api/repositories"),

  openRepository: (stateId: string) =>
    request<{ url?: string; runId?: string; catchup?: boolean }>(
      `/api/repositories/${encodeURIComponent(stateId)}/open`,
      { method: "POST" },
    ),

  removeRepository: (stateId: string) =>
    request<void>(`/api/repositories/${encodeURIComponent(stateId)}`, { method: "DELETE" }),

  runLog: () => request<{ runs: RunRecord[] }>("/api/run-log"),
};

/** The stream's URL, with the token in the query string. */
export function runStreamUrl(): string {
  const token = currentApiToken();
  return token ? `/api/runs/stream?token=${encodeURIComponent(token)}` : "/api/runs/stream";
}

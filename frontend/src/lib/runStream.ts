/**
 * Subscribe to the hub's run stream (contracts/hub-http-api.md).
 *
 * `EventSource` rather than polling: a run can last forty minutes, and polling
 * at the cadence spec SC-002 implies would be thousands of requests for one
 * run. It also reconnects on its own, which is most of spec FR-018 - a run
 * survives the browser closing, and reopening the page rejoins it - for free.
 *
 * The server sends a **complete snapshot** every time, never a delta, so there
 * is no accumulated client state that could drift from the server's, and a late
 * attach is the same code path as the first one.
 */

import { type RunSnapshot, runStreamUrl } from "./hubApiClient";

export interface RunStreamHandlers {
  onSnapshot: (run: RunSnapshot | null) => void;
  onError?: (error: Event) => void;
}

export function subscribeToRun(handlers: RunStreamHandlers): () => void {
  if (typeof EventSource === "undefined") {
    // jsdom, and any browser without it. The caller has already fetched the
    // current snapshot, so the page is correct - just not live.
    return () => {};
  }

  const source = new EventSource(runStreamUrl());

  source.onmessage = (event: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(event.data) as { run: RunSnapshot | null };
      handlers.onSnapshot(payload.run);
    } catch {
      // A truncated frame is not worth tearing the stream down for: the next
      // snapshot is a complete one and will correct the display.
    }
  };

  source.onerror = (event: Event) => {
    handlers.onError?.(event);
    // Deliberately not closed: EventSource retries on its own, which is what
    // makes a hub restart or a slept machine recover without a reload.
  };

  return () => source.close();
}

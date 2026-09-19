import { StrictMode, useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

// The wiki's tokens and base styles first, then the homepage's own on top.
// hub.css is imported only here, so nothing in it reaches wiki-ui.css.
import "./styles.css";
import "./hub.css";

import { captureApiTokenFromUrl } from "./lib/apiToken";
import {
  HubApiError,
  type HistoryEntry,
  type RunRecord,
  type RunSnapshot,
  hubApi,
} from "./lib/hubApiClient";
import { subscribeToRun } from "./lib/runStream";
import { HistoryList } from "./components/HistoryList";
import { IndexBar } from "./components/IndexBar";
import { RunLogList } from "./components/RunLogList";
import { RunOutcome } from "./components/RunOutcome";
import { RunProgress } from "./components/RunProgress";
import { ThemeToggle } from "./components/ThemeToggle";

/**
 * The Codepedia homepage (spec FR-013a).
 *
 * One page, one address. A running analysis takes over the area the index
 * control occupies, with the history still listed below it - so reloading, or
 * opening a second tab, lands on the live run with no navigation and no
 * separate run URL to keep in step.
 */

/**
 * Send the reader to a wiki, telling it where the homepage is.
 *
 * A wiki is generated before any hub exists, so it cannot know which port
 * `codepedia home` ended up on - without this its "Home" link can only guess at
 * the default. Only the origin travels, never the token: `sessionStorage` is
 * per tab *and* per origin and survives navigating away and back, so the hub's
 * own token is still here when the reader returns (lib/hubLink.ts).
 */
function goToWiki(url: string): void {
  try {
    const target = new URL(url);
    target.searchParams.set("hub", window.location.origin + "/");
    window.location.href = target.toString();
  } catch {
    window.location.href = url;
  }
}

export function HubPage(): JSX.Element {
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  // Which open we are actually waiting to be taken to. Without this, *any*
  // finished open with a server URL would send this tab to that wiki - which
  // meant returning to the homepage bounced you straight back out of it, with
  // no way to ever stay here.
  const followingOpen = useRef<string | null>(null);

  const refreshHistory = useCallback(async () => {
    try {
      const [repositories, runLog] = await Promise.all([hubApi.repositories(), hubApi.runLog()]);
      setEntries(repositories.repositories);
      setRuns(runLog.runs);
    } catch {
      // A listing that cannot be read is not worth blocking the page for; the
      // server already degrades to an empty list rather than an error.
    }
  }, []);

  useEffect(() => {
    captureApiTokenFromUrl();
    void (async () => {
      try {
        const current = await hubApi.currentRun();
        setRun(current.run);
      } catch {
        /* the stream will correct this */
      }
      await refreshHistory();
    })();
  }, [refreshHistory]);

  // Spec FR-018: a run belongs to the hub, not to this tab. Attaching shows
  // whatever is happening now, whether this tab started it or not.
  useEffect(() => subscribeToRun({ onSnapshot: setRun }), []);

  // Spec FR-032: a finished run updates the listing without a manual reload.
  // Spec FR-035: an Open whose catch-up finished navigates when the URL lands.
  const outcome = run?.outcome ?? null;
  const serverUrl = run?.serverUrl ?? null;
  useEffect(() => {
    if (outcome !== null) void refreshHistory();
  }, [outcome, refreshHistory]);
  useEffect(() => {
    if (!serverUrl || run?.kind !== "open") return;
    if (followingOpen.current !== run.runId) return;
    followingOpen.current = null;
    goToWiki(serverUrl);
  }, [serverUrl, run?.kind, run?.runId]);

  const startRun = useCallback(async (path: string) => {
    setError(null);
    setNotice(null);
    try {
      await hubApi.startRun(path);
      const current = await hubApi.currentRun();
      setRun(current.run);
    } catch (thrown) {
      setError(thrown instanceof HubApiError ? thrown.message : String(thrown));
    }
  }, []);

  const cancel = useCallback(async () => {
    setCancelling(true);
    try {
      const result = await hubApi.cancelRun();
      setRun(result.run);
    } catch (thrown) {
      setError(thrown instanceof HubApiError ? thrown.message : String(thrown));
    } finally {
      setCancelling(false);
    }
  }, []);

  const dismiss = useCallback(async () => {
    try {
      await hubApi.dismissRun();
    } finally {
      setRun(null);
    }
  }, []);

  const retry = useCallback(async () => {
    if (!run) return;
    setRetrying(true);
    try {
      await hubApi.dismissRun();
      // Spec FR-024: the same path, without the person retyping it.
      await startRun(run.repositoryPath);
    } finally {
      setRetrying(false);
    }
  }, [run, startRun]);

  const open = useCallback(
    async (entry: HistoryEntry) => {
      setError(null);
      setNotice(null);
      try {
        const result = await hubApi.openRepository(entry.stateId);
        if (result.url) {
          goToWiki(result.url);
          return;
        }
        // Catch-up work started; the stream now drives the display and the
        // navigation happens when `server_ready` arrives (spec FR-019). Record
        // which run we are following, so only this open takes us away.
        if (result.runId) followingOpen.current = result.runId;
        const current = await hubApi.currentRun();
        setRun(current.run);
      } catch (thrown) {
        setError(thrown instanceof HubApiError ? thrown.message : String(thrown));
      }
    },
    [],
  );

  const closeServer = useCallback(
    async (entry: HistoryEntry) => {
      setError(null);
      try {
        const result = await hubApi.closeRepository(entry.stateId);
        setNotice(
          result.closed
            ? `Closed the wiki for ${entry.repositoryPath}.`
            : `No wiki was running for ${entry.repositoryPath}.`,
        );
        await refreshHistory();
      } catch (thrown) {
        setError(thrown instanceof HubApiError ? thrown.message : String(thrown));
      }
    },
    [refreshHistory],
  );

  const remove = useCallback(
    async (entry: HistoryEntry) => {
      setError(null);
      try {
        await hubApi.removeRepository(entry.stateId);
        setNotice(`Removed the stored analysis for ${entry.repositoryPath}.`);
        await refreshHistory();
      } catch (thrown) {
        setError(thrown instanceof HubApiError ? thrown.message : String(thrown));
      }
    },
    [refreshHistory],
  );

  const active = run !== null && run.outcome === null;

  return (
    <div className="hub">
      <header className="hub__header">
        <a className="hub__brand" href="/">
          <img className="hub__lockup hub__lockup--light" src="/codepedia-lockup-light.svg" alt="Codepedia" />
          <img className="hub__lockup hub__lockup--dark" src="/codepedia-lockup-dark.svg" alt="" aria-hidden="true" />
        </a>
        <ThemeToggle />
      </header>

      <main className="hub__main">
        {active && run ? (
          <RunProgress run={run} onCancel={cancel} cancelling={cancelling} />
        ) : (
          <IndexBar
            onSubmit={startRun}
            error={error}
            busyLabel={notice ?? undefined}
          />
        )}

        {run && run.outcome !== null ? (
          <RunOutcome
            run={run}
            onRetry={retry}
            onDismiss={dismiss}
            retrying={retrying}
            onOpen={run.serverUrl ? () => { goToWiki(run.serverUrl as string); } : undefined}
          />
        ) : null}

        {active && error ? (
          <p className="hub__error" role="alert">
            {error}
          </p>
        ) : null}

        <HistoryList
          entries={entries}
          onOpen={open}
          onCloseServer={closeServer}
          onRemove={remove}
          busy={active}
        />
        <RunLogList runs={runs} />
      </main>
    </div>
  );
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <StrictMode>
      <HubPage />
    </StrictMode>,
  );
}

import type { RunSnapshot } from "../lib/hubApiClient";

/**
 * How a run ended, and what that means (spec FR-021 to FR-027).
 *
 * The sentence that matters most here is "Nothing was kept". A display showing
 * nine ticked stages next to the word "failed" is actively misleading: the
 * pipeline builds into a staging directory and promotes it only on full
 * success, so a late failure throws away documentation that was generated
 * correctly minutes earlier. Spec FR-023 requires that be said out loud rather
 * than left to be inferred from a column of ticks.
 *
 * Nothing here clears itself on a timer (spec FR-026). A failure naming a stage
 * and a provider chain is exactly the text a person needs to sit and read.
 */

export interface RunOutcomeProps {
  run: RunSnapshot;
  onRetry?: () => void;
  onDismiss?: () => void;
  onOpen?: () => void;
  retrying?: boolean;
}

export function RunOutcome({ run, onRetry, onDismiss, onOpen, retrying = false }: RunOutcomeProps): JSX.Element | null {
  if (run.outcome === null) return null;

  const succeeded = run.outcome === "succeeded";
  const cancelled = run.outcome === "cancelled";
  const opened = run.kind === "open";

  return (
    <section className={`run-outcome run-outcome--${run.outcome}`} aria-label="Analysis result" role="status">
      <h2 className="run-outcome__title">
        {/* An `open` run analysed nothing - it started a server for a
            repository that was already analysed - so calling it an analysis
            would be wrong on the one screen that has to be trustworthy. */}
        {succeeded
          ? opened
            ? "Repository opened"
            : "Analysis complete"
          : cancelled
            ? opened
              ? "Opening stopped"
              : "Analysis stopped"
            : opened
              ? "Could not open the repository"
              : "Analysis failed"}
      </h2>

      <p className="run-outcome__path" title={run.repositoryPath}>
        {run.repositoryPath}
      </p>

      {!succeeded && run.failedStage ? (
        <p className="run-outcome__stage">
          Stopped at: <strong>{stageLabel(run)}</strong>
        </p>
      ) : null}

      {run.failureMessage ? <p className="run-outcome__message">{run.failureMessage}</p> : null}

      {run.providersAttempted.length > 0 ? (
        <div className="run-outcome__providers">
          <p>Providers tried:</p>
          <ul>
            {run.providersAttempted.map((provider) => (
              <li key={provider}>{provider}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {run.discardedEverything ? (
        <p className="run-outcome__discarded">
          Nothing was kept from this run. Any stages shown as finished above were discarded — the
          analysis is only saved when every stage succeeds.
        </p>
      ) : null}

      <div className="run-outcome__actions">
        {succeeded && run.serverUrl && onOpen ? (
          <button type="button" className="run-outcome__open" onClick={onOpen}>
            Open documentation
          </button>
        ) : null}
        {!succeeded && onRetry ? (
          <button type="button" className="run-outcome__retry" onClick={onRetry} disabled={retrying}>
            {retrying ? "Starting…" : "Try again"}
          </button>
        ) : null}
        {onDismiss ? (
          <button type="button" className="run-outcome__dismiss" onClick={onDismiss}>
            Dismiss
          </button>
        ) : null}
      </div>
    </section>
  );
}

function stageLabel(run: RunSnapshot): string {
  const stage = run.stages.find((candidate) => candidate.name === run.failedStage);
  return stage ? stage.label : (run.failedStage ?? "unknown stage");
}

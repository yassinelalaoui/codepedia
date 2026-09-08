import type { RunSnapshot, StageState } from "../lib/hubApiClient";

/**
 * The ten stages of a run, and where it has got to (spec FR-014, FR-015).
 *
 * Two things this deliberately does that a simpler bar would not:
 *
 * - It shows **item counts inside a stage**, because summarization dominates a
 *   real run's wall clock. A bar that moved only between stages would sit still
 *   for the majority of an analysis, which is the "looks hung" problem this
 *   whole feature exists to fix (spec FR-015, SC-011).
 * - It shows **provider switches**, because constitution 2.3 requires an
 *   automatic switch never be silent in practice - and for a run started from
 *   the browser, this is the only place the person is looking (spec FR-017).
 */

function stageClass(stage: StageState): string {
  return `run-stage run-stage--${stage.status}`;
}

function stageProgress(stage: StageState): string | null {
  if (stage.completed == null || stage.total == null || stage.total <= 0) return null;
  return `${stage.completed} of ${stage.total}`;
}

function percent(stage: StageState): number | null {
  if (stage.completed == null || stage.total == null || stage.total <= 0) return null;
  return Math.min(100, Math.round((stage.completed / stage.total) * 100));
}

export interface RunProgressProps {
  run: RunSnapshot;
  onCancel?: () => void;
  cancelling?: boolean;
}

export function RunProgress({ run, onCancel, cancelling = false }: RunProgressProps): JSX.Element {
  const running = run.outcome === null;

  return (
    <section className="run-progress" aria-label="Analysis progress">
      <header className="run-progress__header">
        <div>
          <h2 className="run-progress__title">
            {run.kind === "open" ? "Bringing up to date" : "Analysing"}
          </h2>
          <p className="run-progress__path" title={run.repositoryPath}>
            {run.repositoryPath}
          </p>
        </div>
        {running && onCancel ? (
          <button className="run-progress__stop" type="button" onClick={onCancel} disabled={cancelling}>
            {cancelling ? "Stopping…" : "Stop"}
          </button>
        ) : null}
      </header>

      {run.catchup ? (
        <p className="run-progress__catchup">
          {run.catchup.phase === "embedding" ? "Re-embedding" : "Re-reading"}{" "}
          {run.catchup.completed} of {run.catchup.total}
          {run.catchup.path ? ` — ${run.catchup.path}` : ""}
        </p>
      ) : null}

      <ol className="run-progress__stages">
        {run.stages.map((stage) => {
          const progress = stageProgress(stage);
          const pct = percent(stage);
          return (
            <li
              key={stage.name}
              className={stageClass(stage)}
              aria-current={stage.status === "running" ? "step" : undefined}
            >
              <span className="run-stage__label">{stage.label}</span>
              {progress ? <span className="run-stage__count">{progress}</span> : null}
              {stage.elapsedSeconds != null ? (
                <span className="run-stage__elapsed">{stage.elapsedSeconds.toFixed(1)}s</span>
              ) : null}
              {pct != null ? (
                <span
                  className="run-stage__bar"
                  role="progressbar"
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${stage.label} progress`}
                >
                  <span className="run-stage__bar-fill" style={{ width: `${pct}%` }} />
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>

      {run.providerSwitches.length > 0 ? (
        <div className="run-progress__switches">
          <h3>Provider switches</h3>
          <ul>
            {run.providerSwitches.map((event, index) => (
              <li key={`${event.at}-${index}`}>
                {event.chain}: {event.fromProvider} → {event.toProvider}
                {event.reason ? ` (${event.reason})` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {run.notices.length > 0 ? (
        <ul className="run-progress__notices">
          {run.notices.map((notice, index) => (
            <li key={index}>{notice}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

import type { RunRecord } from "../lib/hubApiClient";

/**
 * Recent run outcomes, newest first (spec FR-026b).
 *
 * Backed by `~/.codepedia/runs.sqlite`, so these survive the hub being stopped
 * and started again - including runs marked `interrupted` by the startup sweep,
 * which are runs whose hub was killed while they were going (spec FR-026d). A
 * missing or unreadable log yields an empty list rather than an error, so this
 * simply renders nothing (spec FR-026e).
 */

function formatTimestamp(value: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function basename(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : path;
}

export interface RunLogListProps {
  runs: RunRecord[];
}

export function RunLogList({ runs }: RunLogListProps): JSX.Element | null {
  if (runs.length === 0) return null;

  return (
    <section className="run-log" aria-label="Recent runs">
      <h2 className="run-log__title">Recent runs</h2>
      <ul className="run-log__list">
        {runs.map((record) => (
          <li key={record.runId} className={`run-log__row run-log__row--${record.outcome ?? "running"}`}>
            <span className="run-log__outcome">{record.outcome ?? "running"}</span>
            <span className="run-log__path" title={record.repositoryPath}>
              {basename(record.repositoryPath)}
            </span>
            <span className="run-log__when">{formatTimestamp(record.endedAt ?? record.startedAt)}</span>
            {record.failedStage ? <span className="run-log__stage">at {record.failedStage}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

import type { HistoryEntry } from "../lib/hubApiClient";
import { HistoryRowMenu } from "./HistoryRowMenu";

/**
 * The analyse history (spec FR-028, FR-031b).
 *
 * A row whose folder is gone stays listed and is marked unavailable rather than
 * disappearing: its documentation is still perfectly readable, and hiding it
 * would strand generated output with no way to reach or remove it from the
 * homepage (spec FR-031b).
 */

function formatTimestamp(value: string | null): string {
  if (!value) return "never";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function basename(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : path;
}

export interface HistoryListProps {
  entries: HistoryEntry[];
  onOpen: (entry: HistoryEntry) => void;
  onRemove: (entry: HistoryEntry) => void;
  busy?: boolean;
}

export function HistoryList({ entries, onOpen, onRemove, busy = false }: HistoryListProps): JSX.Element {
  if (entries.length === 0) {
    return (
      <section className="history" aria-label="Analyse history">
        <h2 className="history__title">Analyse history</h2>
        <p className="history__empty">
          Nothing analysed yet. Enter a repository folder above to get started.
        </p>
      </section>
    );
  }

  return (
    <section className="history" aria-label="Analyse history">
      <h2 className="history__title">Analyse history</h2>
      <ul className="history__list">
        {entries.map((entry) => (
          <li key={entry.stateId} className={`history__row${entry.available ? "" : " history__row--unavailable"}`}>
            <button
              type="button"
              className="history__open"
              onClick={() => onOpen(entry)}
              disabled={busy}
              title={entry.repositoryPath}
            >
              <span className="history__name">{basename(entry.repositoryPath)}</span>
              <span className="history__path">{entry.repositoryPath}</span>
            </button>
            <span className="history__meta">
              <span className="history__when">Last analysed {formatTimestamp(entry.lastIndexedAt)}</span>
              {entry.available ? null : (
                <span className="history__unavailable" title="The folder is no longer on this machine">
                  folder missing
                </span>
              )}
            </span>
            <HistoryRowMenu
              entry={entry}
              onOpen={() => onOpen(entry)}
              onRemove={() => onRemove(entry)}
              disabled={busy}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

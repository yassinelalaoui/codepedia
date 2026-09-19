import { useEffect, useRef, useState } from "react";
import type { HistoryEntry } from "../lib/hubApiClient";

/**
 * A history row's overflow menu: Properties, Open, Close, Remove (spec FR-033).
 *
 * Close is offered only while this hub is serving a wiki for the row. Opening
 * a repository deliberately leaves its server running - returning to it is then
 * instant - and every child dies with the hub, so this is the one way to stop
 * one in between. Remove refuses while a server runs and says to close it
 * first, which was an instruction with nothing to press until this existed.
 *
 * There is deliberately **no re-analyse action**, and that absence is a
 * decision rather than an omission. Opening a repository already brings it up
 * to date - `serve`'s watcher reconciles everything that changed while it was
 * closed - so a re-analyse button would either duplicate Open or trigger a full
 * rebuild that constitution 2.5 says should not be the ordinary path. The index
 * bar remains the deliberate full-rebuild escape hatch (spec FR-013).
 *
 * Remove is confirmed inline and names the repository (spec FR-040), because it
 * deletes generated documentation that can cost many minutes to rebuild.
 */

export interface HistoryRowMenuProps {
  entry: HistoryEntry;
  onOpen: () => void;
  onClose: () => void;
  onRemove: () => void;
  disabled?: boolean;
}

export function HistoryRowMenu({
  entry,
  onOpen,
  onClose,
  onRemove,
  disabled = false,
}: HistoryRowMenuProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [showProperties, setShowProperties] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDocumentClick = (event: MouseEvent): void => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    const onEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocumentClick);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onDocumentClick);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  return (
    <div className="history-menu" ref={container}>
      <button
        type="button"
        className="history-menu__trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Actions for ${entry.repositoryPath}`}
        onClick={() => setOpen((value) => !value)}
        disabled={disabled}
      >
        ⋯
      </button>

      {open ? (
        <div className="history-menu__items" role="menu">
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setShowProperties(true);
              setOpen(false);
            }}
          >
            Properties
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onOpen();
            }}
          >
            Open
          </button>
          {entry.open ? (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onClose();
              }}
            >
              Close
            </button>
          ) : null}
          <button
            type="button"
            role="menuitem"
            className="history-menu__remove"
            onClick={() => {
              setOpen(false);
              setConfirming(true);
            }}
          >
            Remove
          </button>
        </div>
      ) : null}

      {showProperties ? (
        <div className="history-properties" role="dialog" aria-label="Repository properties">
          <dl>
            <dt>Path</dt>
            <dd>{entry.repositoryPath}</dd>
            <dt>Last analysed</dt>
            <dd>{entry.lastIndexedAt ?? "unknown"}</dd>
            <dt>Folder</dt>
            <dd>{entry.available ? "present" : "no longer on this machine"}</dd>
          </dl>
          <button type="button" onClick={() => setShowProperties(false)}>
            Close
          </button>
        </div>
      ) : null}

      {confirming ? (
        <div className="history-confirm" role="alertdialog" aria-label="Confirm removal">
          <p>
            Remove the stored analysis for <strong>{entry.repositoryPath}</strong>? This deletes its
            documentation, index and metadata. The repository's own files are not touched.
          </p>
          <button
            type="button"
            className="history-confirm__yes"
            onClick={() => {
              setConfirming(false);
              onRemove();
            }}
          >
            Remove
          </button>
          <button type="button" onClick={() => setConfirming(false)}>
            Cancel
          </button>
        </div>
      ) : null}
    </div>
  );
}

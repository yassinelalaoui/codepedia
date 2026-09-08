import { useState, type FormEvent } from "react";

/**
 * Type a repository path, press go (spec FR-008).
 *
 * A plain `<form>` so Enter submits and the button is reachable by keyboard
 * without any handler of our own - spec FR-008 asks for keyboard operability,
 * and the platform already provides it correctly here.
 *
 * The path is not validated in the browser beyond "not empty". The server owns
 * that (spec FR-009) because only the server can see the filesystem, and a
 * second, weaker copy of the rules here would only ever disagree with it.
 */

export interface IndexBarProps {
  onSubmit: (path: string) => Promise<void> | void;
  disabled?: boolean;
  error?: string | null;
  busyLabel?: string;
}

export function IndexBar({ onSubmit, disabled = false, error, busyLabel }: IndexBarProps): JSX.Element {
  const [path, setPath] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const trimmed = path.trim();
    if (!trimmed || submitting || disabled) return;
    setSubmitting(true);
    try {
      await onSubmit(trimmed);
    } finally {
      setSubmitting(false);
    }
  };

  const blocked = disabled || submitting;

  return (
    <form className="index-bar" onSubmit={submit} aria-label="Analyse a repository">
      <label className="index-bar__label" htmlFor="repository-path">
        Repository folder
      </label>
      <div className="index-bar__row">
        <input
          id="repository-path"
          className="index-bar__input"
          type="text"
          value={path}
          spellCheck={false}
          autoComplete="off"
          placeholder="C:\\path\\to\\your\\repository"
          onChange={(event) => setPath(event.target.value)}
          disabled={blocked}
          aria-describedby={error ? "index-bar-error" : undefined}
          aria-invalid={error ? true : undefined}
        />
        <button className="index-bar__submit" type="submit" disabled={blocked || !path.trim()}>
          {submitting ? "Starting…" : "Analyse"}
        </button>
      </div>
      {busyLabel ? (
        <p className="index-bar__busy">{busyLabel}</p>
      ) : null}
      {error ? (
        // `role="alert"` so the reason is announced rather than only shown -
        // this is the one place a person learns why nothing happened.
        <p className="index-bar__error" id="index-bar-error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}

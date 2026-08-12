import { useEffect, useState } from "react";
import { loadSearchIndex, queryIndex, type SearchIndexEntry } from "../lib/searchIndex";

type LoadState = "loading" | "ready" | "unavailable";

export function SearchWidget() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [entries, setEntries] = useState<SearchIndexEntry[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    loadSearchIndex()
      .then((loaded) => {
        if (cancelled) return;
        setEntries(loaded);
        setLoadState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setLoadState("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadState === "unavailable") {
    return <div className="wiki-search-widget wiki-chat-error">Search is unavailable.</div>;
  }

  const results = loadState === "ready" ? queryIndex(entries, query) : [];
  const trimmedQuery = query.trim();

  return (
    <div className="wiki-search-widget">
      <input
        type="search"
        aria-label="Search symbols and functions"
        placeholder="Search symbols and functions by name…"
        value={query}
        disabled={loadState === "loading"}
        onChange={(event) => setQuery(event.target.value)}
      />
      {trimmedQuery && results.length === 0 && loadState === "ready" && (
        <p className="wiki-search-meta">No results for "{trimmedQuery}".</p>
      )}
      {results.length > 0 && (
        <ul className="wiki-search-results">
          {results.map((entry) => (
            <li key={`${entry.kind}:${entry.symbolId}`}>
              <a href={entry.pageUrl}>{entry.name}</a>{" "}
              <span className="wiki-search-meta">
                ({entry.kind} — {entry.filePath})
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

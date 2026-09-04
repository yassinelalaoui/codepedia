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
    return <div className={`wiki-search-widget flex flex-col gap-1.5 ${"text-[#c4394a] text-[13px] px-[18px]"}`}>Search is unavailable.</div>;
  }

  const results = loadState === "ready" ? queryIndex(entries, query) : [];
  const trimmedQuery = query.trim();

  return (
    <div className="wiki-search-widget flex flex-col gap-1.5">
      <input
        type="search"
        aria-label="Search symbols and functions"
        placeholder="Search symbols and functions by name…"
        value={query}
        disabled={loadState === "loading"}
        onChange={(event) => setQuery(event.target.value)}
        className="w-full box-border py-[7px] px-2.5 bg-sunken border border-line rounded-md text-ink text-[13px] font-ui placeholder:text-ink-faint focus:outline-none focus:border-accent focus:bg-surface"
      />
      {trimmedQuery && results.length === 0 && loadState === "ready" && (
        <p className="wiki-search-meta text-ink-faint text-[11.5px] font-ui py-1 px-1.5">No results for "{trimmedQuery}".</p>
      )}
      {results.length > 0 && (
        <ul className="wiki-search-results list-none m-0 p-1 bg-surface border border-line rounded-md shadow-2 max-h-[280px] overflow-y-auto">
          {results.map((entry) => (
            <li key={`${entry.kind}:${entry.symbolId}`} className="p-0">
              <a href={entry.pageUrl} className="block py-[7px] px-2 rounded-sm text-ink font-mono text-[12.5px] hover:bg-sunken hover:no-underline">{entry.name}</a>{" "}
              <span className="wiki-search-meta text-ink-faint text-[11.5px] font-ui py-1 px-1.5">
                ({entry.kind} — {entry.filePath})
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

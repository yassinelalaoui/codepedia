export type SearchIndexEntryKind = "module" | "class" | "method" | "function";

export interface SearchIndexEntry {
  name: string;
  kind: SearchIndexEntryKind;
  symbolId: string;
  filePath: string;
  pageUrl: string;
}

interface SearchIndexDocument {
  generatedAt: string;
  entries: SearchIndexEntry[];
}

declare global {
  interface Window {
    __WIKI_UI_CONFIG__?: {
      searchIndexHref: string;
    };
  }
}

let cachedEntries: SearchIndexEntry[] | null = null;
let cachedError: Error | null = null;
let inflight: Promise<SearchIndexEntry[]> | null = null;

function searchIndexHref(): string {
  return window.__WIKI_UI_CONFIG__?.searchIndexHref ?? "assets/search-index.json";
}

/**
 * Fetches and caches `search-index.json`, page-relative to the current
 * document (contracts/search-index.md). Rejects on network failure or a
 * non-2xx response so callers can render the "unavailable" state
 * contracts/ui-mount-points.md requires.
 */
export async function loadSearchIndex(): Promise<SearchIndexEntry[]> {
  if (cachedEntries) return cachedEntries;
  if (cachedError) throw cachedError;
  if (inflight) return inflight;

  inflight = fetch(searchIndexHref())
    .then((response) => {
      if (!response.ok) {
        throw new Error(`search-index.json request failed with status ${response.status}`);
      }
      return response.json() as Promise<SearchIndexDocument>;
    })
    .then((document) => {
      cachedEntries = document.entries;
      return cachedEntries;
    })
    .catch((error: unknown) => {
      cachedError = error instanceof Error ? error : new Error(String(error));
      throw cachedError;
    })
    .finally(() => {
      inflight = null;
    });

  return inflight;
}

/** Test-only: reset the module-level cache between test cases. */
export function _resetSearchIndexCacheForTests(): void {
  cachedEntries = null;
  cachedError = null;
  inflight = null;
}

/**
 * Ranked substring match over symbol/function name (primary) and file path
 * (fallback), per contracts/search-index.md. Returns at most `limit`
 * entries, best match first.
 */
export function queryIndex(entries: SearchIndexEntry[], query: string, limit = 20): SearchIndexEntry[] {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return [];

  return entries
    .map((entry) => ({ entry, score: matchScore(entry, trimmed) }))
    .filter((match) => match.score > 0)
    .sort((a, b) => b.score - a.score || a.entry.name.localeCompare(b.entry.name))
    .slice(0, limit)
    .map((match) => match.entry);
}

function matchScore(entry: SearchIndexEntry, query: string): number {
  const name = entry.name.toLowerCase();
  if (name === query) return 100;
  if (name.startsWith(query)) return 80;
  if (name.includes(query)) return 60;
  if (entry.filePath.toLowerCase().includes(query)) return 20;
  return 0;
}

/** Finds an entry matching a chat citation, symbol id first then file path (research.md Decision 5). */
export function findByCitation(
  entries: SearchIndexEntry[],
  { symbolId, filePath }: { symbolId?: string; filePath?: string }
): SearchIndexEntry | undefined {
  if (symbolId) {
    const bySymbol = entries.find((entry) => entry.symbolId === symbolId);
    if (bySymbol) return bySymbol;
  }
  if (filePath) {
    return entries.find((entry) => entry.kind === "module" && entry.filePath === filePath);
  }
  return undefined;
}

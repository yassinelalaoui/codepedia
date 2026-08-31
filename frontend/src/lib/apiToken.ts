/**
 * This run's chat-API token, carried from the URL the server printed.
 *
 * The wiki is a static bundle generated before the server starts, so the token
 * cannot be baked into these pages: the server prints
 * `http://127.0.0.1:8000/?token=...` and the first page load moves the value
 * into `sessionStorage`, then strips it from the address bar with
 * `history.replaceState` - the same handling `?chatSession=` already gets in
 * ChatPanel, and for the same reason: a value that belongs to the session, not
 * to the page's identity.
 *
 * `sessionStorage`, not `localStorage`: the server mints a new token every run,
 * so a value that outlived the tab would only ever be a stale one.
 */

export const TOKEN_HEADER = "X-Codepedia-Token";
const TOKEN_PARAM = "token";
const STORAGE_KEY = "codepedia.apiToken";

function readStored(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(token: string): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Storage refused (a locked-down browser profile). Nothing else to try:
    // every wiki link is a full page load, so an in-memory copy would not
    // survive to the next page anyway. The API answers 401 and ChatPanel says
    // to reopen the printed URL.
  }
}

/**
 * Consumes `?token=` if present: stores it and removes it from the address bar
 * so it is not copied out of the URL, kept in history, or sent as a referrer.
 * Safe to call more than once.
 */
export function captureApiTokenFromUrl(): void {
  const url = new URL(window.location.href);
  const token = url.searchParams.get(TOKEN_PARAM);
  if (!token) return;
  writeStored(token);
  url.searchParams.delete(TOKEN_PARAM);
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

export function currentApiToken(): string | null {
  return readStored();
}

/** The auth header for an API request, or nothing when no token is known. */
export function apiTokenHeaders(): Record<string, string> {
  const token = currentApiToken();
  return token ? { [TOKEN_HEADER]: token } : {};
}

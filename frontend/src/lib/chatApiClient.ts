export interface ChatMessageView {
  role: "user" | "assistant";
  content: string;
  citedSymbolIds: string[];
  citedFilePaths: string[];
  timestamp: string;
}

export interface AskQuestionResponse {
  answer: string;
  citedSymbolIds: string[];
  citedFilePaths: string[];
}

export interface SessionHistoryResponse {
  sessionId: string;
  messages: ChatMessageView[];
}

import { apiTokenHeaders } from "./apiToken";

export interface ApiErrorResponse {
  code: string;
  message: string;
}

/** Thrown for 014's structured error responses (404/422/503), and — since
 * 026/027 — for a terminal SSE `error` event on an already-open stream. */
export class ChatApiError extends Error {
  code: string;
  status: number;

  constructor(body: ApiErrorResponse, status: number) {
    super(body.message);
    this.code = body.code;
    this.status = status;
  }
}

/**
 * Same-origin, root-relative requests against the chat API (014), reachable
 * from the same server that serves this bundle (015) — research.md
 * Decision 4. No base URL or CORS configuration needed.
 *
 * Every call carries this run's token (apiToken.ts). The wiki pages themselves
 * are served without it; the API is not, so a request made with no token comes
 * back 401 rather than answering.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...apiTokenHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = (await response.json()) as ApiErrorResponse;
    throw new ChatApiError(body, response.status);
  }
  return response.json() as Promise<T>;
}

export function createSession(): Promise<{ sessionId: string }> {
  return request("/sessions", { method: "POST" });
}

/** One parsed SSE event: an event name (defaults to "message" per the SSE
 * spec, used for `fragment` events, which are sent with no `event:` line)
 * plus its JSON `data:` payload. */
function parseSseBlock(block: string): { name: string; data: unknown } | null {
  let eventName = "message";
  let dataLine: string | null = null;
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLine = line.slice("data:".length).trim();
    }
  }
  if (dataLine === null) return null;
  return { name: eventName, data: JSON.parse(dataLine) };
}

/**
 * Submits a question and consumes the server's SSE stream (026) as it
 * arrives — `onFragment` is invoked once per `fragment` event, in order,
 * so a caller can render the answer progressively (027) instead of waiting
 * for the terminal `done` event this still resolves with.
 */
export async function askQuestion(
  sessionId: string,
  question: string,
  onFragment: (fragment: string) => void
): Promise<AskQuestionResponse> {
  // Not routed through `request()` (it consumes the body as JSON), so the
  // token header has to be added here too.
  const response = await fetch(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...apiTokenHeaders() },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) {
    // A failure known before any streaming began (unknown session, empty
    // question, engine unavailable) - a plain JSON error body, same as
    // every other non-streaming route.
    const body = (await response.json()) as ApiErrorResponse;
    throw new ChatApiError(body, response.status);
  }
  if (!response.body) {
    throw new Error("Expected a streaming response body for a successful ask request.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: AskQuestionResponse | null = null;

  while (done === null) {
    const { done: streamDone, value } = await reader.read();
    if (streamDone) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseSseBlock(block);
      if (event) {
        if (event.name === "error") {
          throw new ChatApiError(event.data as ApiErrorResponse, response.status);
        }
        if (event.name === "done") {
          done = event.data as AskQuestionResponse;
        } else {
          onFragment((event.data as { fragment: string }).fragment);
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  }

  if (done === null) {
    throw new Error("The answer stream ended without a terminal event.");
  }
  return done;
}

export function getHistory(sessionId: string): Promise<SessionHistoryResponse> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/messages`);
}

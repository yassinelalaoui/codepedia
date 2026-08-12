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

export interface ApiErrorResponse {
  code: string;
  message: string;
}

/** Thrown for 014's structured error responses (404/422/503). */
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
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
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

export function askQuestion(sessionId: string, question: string): Promise<AskQuestionResponse> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export function getHistory(sessionId: string): Promise<SessionHistoryResponse> {
  return request(`/sessions/${encodeURIComponent(sessionId)}/messages`);
}

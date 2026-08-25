import { afterEach, describe, expect, it, vi } from "vitest";
import { askQuestion, ChatApiError, listSessions } from "../src/lib/chatApiClient";

/** A mock `fetch` Response body exposing just the `getReader()` shape our
 * SSE-parsing code needs — avoids depending on a real `ReadableStream`
 * implementation being available/consistent across the jsdom test
 * environment; each entry in `chunks` becomes one `reader.read()` result. */
function sseBody(chunks: string[]) {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    getReader() {
      return {
        async read() {
          if (index >= chunks.length) {
            return { done: true, value: undefined };
          }
          const value = encoder.encode(chunks[index]);
          index += 1;
          return { done: false, value };
        },
      };
    },
  };
}

function sseResponse(events: string[]) {
  return { ok: true, status: 200, body: sseBody(events) };
}

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

describe("askQuestion", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("invokes onFragment once per fragment, in order, then resolves with the done payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        sseResponse([
          `data: ${JSON.stringify({ fragment: "Authentication" })}\n\n`,
          `data: ${JSON.stringify({ fragment: " is handled." })}\n\n`,
          `event: done\ndata: ${JSON.stringify({
            answer: "Authentication is handled.",
            citedSymbolIds: ["auth.authenticate_user"],
            citedFilePaths: ["src/auth/login.py"],
          })}\n\n`,
        ])
      )
    );

    const fragments: string[] = [];
    const result = await askQuestion("session-1", "where is auth handled?", (fragment) => {
      fragments.push(fragment);
    });

    expect(fragments).toEqual(["Authentication", " is handled."]);
    expect(result).toEqual({
      answer: "Authentication is handled.",
      citedSymbolIds: ["auth.authenticate_user"],
      citedFilePaths: ["src/auth/login.py"],
    });
  });

  it("resolves with an answer equal to every fragment concatenated in order", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        sseResponse([
          `data: ${JSON.stringify({ fragment: "one " })}\n\n`,
          `data: ${JSON.stringify({ fragment: "two " })}\n\n`,
          `data: ${JSON.stringify({ fragment: "three" })}\n\n`,
          `event: done\ndata: ${JSON.stringify({ answer: "one two three", citedSymbolIds: [], citedFilePaths: [] })}\n\n`,
        ])
      )
    );

    const fragments: string[] = [];
    const result = await askQuestion("session-1", "count?", (fragment) => fragments.push(fragment));

    expect(fragments.join("")).toBe(result.answer);
  });

  it("handles one SSE event split across multiple stream chunks", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        sseResponse([
          "data: {\"frag",
          `ment": "Authentication"}\n\n`,
          `event: done\ndata: ${JSON.stringify({ answer: "Authentication", citedSymbolIds: [], citedFilePaths: [] })}\n\n`,
        ])
      )
    );

    const fragments: string[] = [];
    const result = await askQuestion("session-1", "who?", (fragment) => fragments.push(fragment));

    expect(fragments).toEqual(["Authentication"]);
    expect(result.answer).toBe("Authentication");
  });

  it("rejects with ChatApiError on a terminal error event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        sseResponse([
          `data: ${JSON.stringify({ fragment: "Authentication is han" })}\n\n`,
          `event: error\ndata: ${JSON.stringify({ code: "generation_failed", message: "The model timed out." })}\n\n`,
        ])
      )
    );

    await expect(askQuestion("session-1", "who?", () => {})).rejects.toMatchObject({
      code: "generation_failed",
      message: "The model timed out.",
    });
  });

  it("rejects with ChatApiError for a pre-stream HTTP failure, without reading a body stream", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(503, { code: "local_dependency_unavailable", message: "Local LLM is unavailable." }))
    );

    await expect(askQuestion("session-1", "who?", () => {})).rejects.toBeInstanceOf(ChatApiError);
  });
});

describe("listSessions", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("performs a plain GET /sessions and resolves with the parsed list", async () => {
    const body = {
      sessions: [
        { sessionId: "session-1", createdAt: "2026-08-20T10:00:00Z", lastActivityAt: "2026-08-25T09:00:00Z" },
      ],
    };
    const fetchMock = vi.fn(async () => jsonResponse(200, body));
    vi.stubGlobal("fetch", fetchMock);

    const result = await listSessions();

    expect(result).toEqual(body);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/sessions");
    expect(init?.method ?? "GET").toBe("GET");
  });
});

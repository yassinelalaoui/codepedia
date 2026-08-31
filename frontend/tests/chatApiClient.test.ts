import { afterEach, describe, expect, it, vi } from "vitest";
import { askQuestion, ChatApiError, createSession, getHistory } from "../src/lib/chatApiClient";
import { captureApiTokenFromUrl, TOKEN_HEADER } from "../src/lib/apiToken";

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

describe("the API token", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
    window.history.replaceState(null, "", "/modules/m.html");
  });

  function withToken(token: string): void {
    window.history.replaceState(null, "", `/modules/m.html?token=${token}`);
    captureApiTokenFromUrl();
  }

  it("moves ?token= out of the address bar and into storage on first load", () => {
    withToken("sekret");

    expect(window.location.search).toBe("");
    expect(window.sessionStorage.getItem("codepedia.apiToken")).toBe("sekret");
  });

  it("keeps the rest of the query string and the hash intact", () => {
    window.history.replaceState(null, "", "/modules/m.html?chatSession=s1&token=sekret#anchor");
    captureApiTokenFromUrl();

    expect(window.location.search).toBe("?chatSession=s1");
    expect(window.location.hash).toBe("#anchor");
  });

  it("is sent on a plain JSON request", async () => {
    withToken("sekret");
    const fetchMock = vi.fn(async () => jsonResponse(201, { sessionId: "s1" }));
    vi.stubGlobal("fetch", fetchMock);

    await createSession();

    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>)[TOKEN_HEADER]).toBe("sekret");
  });

  it("is sent on the streaming ask request too", async () => {
    withToken("sekret");
    const fetchMock = vi.fn(async () =>
      sseResponse([
        `data: ${JSON.stringify({ fragment: "hi" })}\n\n`,
        `event: done\ndata: ${JSON.stringify({ answer: "hi", citedSymbolIds: [], citedFilePaths: [] })}\n\n`,
      ])
    );
    vi.stubGlobal("fetch", fetchMock);

    await askQuestion("s1", "who?", () => {});

    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>)[TOKEN_HEADER]).toBe("sekret");
  });

  it("sends no token header when the page was opened without one", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { sessionId: "s1", messages: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getHistory("s1");

    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers as Record<string, string>)[TOKEN_HEADER]).toBeUndefined();
  });
});

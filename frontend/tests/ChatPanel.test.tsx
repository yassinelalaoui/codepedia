import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ChatPanel } from "../src/components/ChatPanel";
import { _resetSearchIndexCacheForTests } from "../src/lib/searchIndex";

const SEARCH_ENTRIES = [
  {
    name: "authenticate_user",
    kind: "function",
    symbolId: "auth.authenticate_user",
    filePath: "src/auth/login.py",
    pageUrl: "modules/login-a1.html#function_a1",
  },
];

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

/** A mock `fetch` Response body exposing just the `getReader()` shape the
 * client's SSE parsing needs (see chatApiClient.test.ts for the same
 * helper, kept local here to avoid a cross-test-file import). */
function sseBody(events: string[]) {
  const encoder = new TextEncoder();
  let index = 0;
  return {
    getReader() {
      return {
        async read() {
          if (index >= events.length) return { done: true, value: undefined };
          const value = encoder.encode(events[index]);
          index += 1;
          return { done: false, value };
        },
      };
    },
  };
}

/** Builds an SSE-formatted ask-a-question response from a list of answer
 * fragments plus the terminal `done` payload — replaces the plain-JSON
 * mock this test file used before 027, which is why the frontend never
 * calling response.json() on an actual SSE body went undetected. */
function sseAskResponse(fragments: string[], done: { answer: string; citedSymbolIds: string[]; citedFilePaths: string[] }) {
  return {
    ok: true,
    status: 200,
    body: sseBody([
      ...fragments.map((fragment) => `data: ${JSON.stringify({ fragment })}\n\n`),
      `event: done\ndata: ${JSON.stringify(done)}\n\n`,
    ]),
  };
}

function installFetchRouter(handlers: {
  ask?: () => ReturnType<typeof jsonResponse> | ReturnType<typeof sseAskResponse>;
  history?: () => ReturnType<typeof jsonResponse> | Promise<ReturnType<typeof jsonResponse>>;
  onCreateSession?: () => void;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("search-index.json")) {
        return jsonResponse(200, { generatedAt: "2026-08-12T00:00:00Z", entries: SEARCH_ENTRIES });
      }
      if (url === "/sessions" && init?.method === "POST") {
        handlers.onCreateSession?.();
        return jsonResponse(201, { sessionId: "session-1" });
      }
      if (url.startsWith("/sessions/") && url.endsWith("/messages") && (!init?.method || init.method === "GET")) {
        return handlers.history ? handlers.history() : jsonResponse(200, { sessionId: "session-1", messages: [] });
      }
      if (url.startsWith("/sessions/") && init?.method === "POST") {
        return handlers.ask ? handlers.ask() : sseAskResponse([], { answer: "", citedSymbolIds: [], citedFilePaths: [] });
      }
      throw new Error(`unexpected fetch: ${url}`);
    })
  );
}

async function askQuestionThroughUi(question: string) {
  const input = await screen.findByLabelText("Ask a question about this repository");
  fireEvent.change(input, { target: { value: question } });
  fireEvent.submit(input.closest("form")!);
}

describe("ChatPanel", () => {
  beforeEach(() => {
    _resetSearchIndexCacheForTests();
    // Session id now lives on the page's own URL (028 US3) rather than in
    // localStorage - reset it between tests so one test's `chatSession`
    // param can't leak into the next.
    window.history.pushState({}, "", "/");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** A gated single-fragment SSE mock: the first fragment only becomes
   * readable once `release()` is called, letting a test observe state
   * that exists strictly before the first fragment arrives (028 US1). */
  function gatedSingleFragmentAskResponse(fragment: string, done: { answer: string; citedSymbolIds: string[]; citedFilePaths: string[] }) {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const encoder = new TextEncoder();
    let step = 0;
    const response = {
      ok: true,
      status: 200,
      body: {
        getReader() {
          return {
            async read() {
              if (step === 0) {
                await gate;
                step += 1;
                return { done: false, value: encoder.encode(`data: ${JSON.stringify({ fragment })}\n\n`) };
              }
              if (step === 1) {
                step += 1;
                return { done: false, value: encoder.encode(`event: done\ndata: ${JSON.stringify(done)}\n\n`) };
              }
              return { done: true, value: undefined };
            },
          };
        },
      },
    };
    return { response, release: () => release?.() };
  }

  it("shows a visible activity indicator immediately after a question is submitted, before any fragment arrives", async () => {
    const { response, release } = gatedSingleFragmentAskResponse("Handled.", {
      answer: "Handled.",
      citedSymbolIds: [],
      citedFilePaths: [],
    });
    installFetchRouter({ ask: () => response });
    render(<ChatPanel />);

    await askQuestionThroughUi("where is this handled?");

    expect(screen.getByRole("status", { name: /generating an answer/i })).toBeInTheDocument();

    release();
    await waitFor(() => {
      expect(screen.getByText("Handled.")).toBeInTheDocument();
    });
  });

  it("replaces the activity indicator with the answer content as soon as the first fragment arrives", async () => {
    const { response, release } = gatedSingleFragmentAskResponse("Handled.", {
      answer: "Handled.",
      citedSymbolIds: [],
      citedFilePaths: [],
    });
    installFetchRouter({ ask: () => response });
    render(<ChatPanel />);

    await askQuestionThroughUi("where is this handled?");
    expect(screen.getByRole("status", { name: /generating an answer/i })).toBeInTheDocument();

    release();

    await waitFor(() => {
      expect(screen.getByText("Handled.")).toBeInTheDocument();
    });
    expect(screen.queryByRole("status", { name: /generating an answer/i })).not.toBeInTheDocument();
  });

  it("replaces the indicator or a partial answer with a clear error message when the stream fails after starting", async () => {
    installFetchRouter({
      ask: () => {
        const encoder = new TextEncoder();
        let step = 0;
        return {
          ok: true,
          status: 200,
          body: {
            getReader() {
              return {
                async read() {
                  if (step === 0) {
                    step += 1;
                    return { done: false, value: encoder.encode(`data: ${JSON.stringify({ fragment: "Partial" })}\n\n`) };
                  }
                  if (step === 1) {
                    step += 1;
                    return {
                      done: false,
                      value: encoder.encode(
                        `event: error\ndata: ${JSON.stringify({ code: "local_dependency_unavailable", message: "Local LLM is unavailable." })}\n\n`
                      ),
                    };
                  }
                  return { done: true, value: undefined };
                },
              };
            },
          },
        };
      },
    });
    render(<ChatPanel />);

    await askQuestionThroughUi("where is this handled?");

    await waitFor(() => {
      expect(screen.getByText("Local LLM is unavailable.")).toBeInTheDocument();
    });
    expect(screen.queryByRole("status", { name: /generating an answer/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Partial")).not.toBeInTheDocument();
  });

  it("transitions cleanly from indicator to answer with no leftover indicator artifact when the first fragment arrives immediately", async () => {
    installFetchRouter({
      ask: () => sseAskResponse(["Handled elsewhere."], { answer: "Handled elsewhere.", citedSymbolIds: [], citedFilePaths: [] }),
    });
    render(<ChatPanel />);

    await askQuestionThroughUi("where is this handled?");

    await waitFor(() => {
      expect(screen.getByText("Handled elsewhere.")).toBeInTheDocument();
    });
    expect(screen.queryByRole("status", { name: /generating an answer/i })).not.toBeInTheDocument();
  });

  it("renders the generated answer with a resolvable citation as a working link", async () => {
    installFetchRouter({
      ask: () =>
        sseAskResponse(["Authentication is handled ", "by authenticate_user."], {
          answer: "Authentication is handled by authenticate_user.",
          citedSymbolIds: ["auth.authenticate_user"],
          citedFilePaths: ["src/auth/login.py"],
        }),
    });
    render(<ChatPanel />);

    await askQuestionThroughUi("where is authentication handled?");

    await waitFor(() => {
      expect(screen.getByText("Authentication is handled by authenticate_user.")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "authenticate_user" })).toHaveAttribute(
      "href",
      "modules/login-a1.html#function_a1"
    );
  });

  it("renders the answer progressively as fragments arrive, before citations are attached", async () => {
    let resolveSecondFragment: (() => void) | undefined;
    const secondFragmentGate = new Promise<void>((resolve) => {
      resolveSecondFragment = resolve;
    });
    installFetchRouter({
      ask: () => {
        const encoder = new TextEncoder();
        let step = 0;
        return {
          ok: true,
          status: 200,
          body: {
            getReader() {
              return {
                async read() {
                  if (step === 0) {
                    step += 1;
                    return { done: false, value: encoder.encode(`data: ${JSON.stringify({ fragment: "Authentication is" })}\n\n`) };
                  }
                  if (step === 1) {
                    await secondFragmentGate;
                    step += 1;
                    return {
                      done: false,
                      value: encoder.encode(
                        `event: done\ndata: ${JSON.stringify({
                          answer: "Authentication is handled by authenticate_user.",
                          citedSymbolIds: ["auth.authenticate_user"],
                          citedFilePaths: ["src/auth/login.py"],
                        })}\n\n`
                      ),
                    };
                  }
                  return { done: true, value: undefined };
                },
              };
            },
          },
        };
      },
    });
    render(<ChatPanel />);

    await askQuestionThroughUi("where is authentication handled?");

    await waitFor(() => {
      expect(screen.getByText("Authentication is")).toBeInTheDocument();
    });
    expect(screen.queryByRole("link", { name: "authenticate_user" })).not.toBeInTheDocument();

    resolveSecondFragment?.();

    await waitFor(() => {
      expect(screen.getByText("Authentication is handled by authenticate_user.")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "authenticate_user" })).toBeInTheDocument();
  });

  it("renders an unresolvable citation as a plain label, not a broken link", async () => {
    installFetchRouter({
      ask: () =>
        sseAskResponse(["Handled elsewhere."], {
          answer: "Handled elsewhere.",
          citedSymbolIds: ["unknown.symbol"],
          citedFilePaths: [],
        }),
    });
    render(<ChatPanel />);

    await askQuestionThroughUi("where is this handled?");

    await waitFor(() => {
      expect(screen.getByText("unknown.symbol")).toBeInTheDocument();
    });
    expect(screen.queryByRole("link", { name: "unknown.symbol" })).not.toBeInTheDocument();
  });

  it("renders a fenced code snippet as visually distinct, syntax-highlighted code", async () => {
    installFetchRouter({
      ask: () =>
        sseAskResponse(["```python\ndef authenticate_user():\n    pass\n```"], {
          answer: "```python\ndef authenticate_user():\n    pass\n```",
          citedSymbolIds: [],
          citedFilePaths: [],
        }),
    });
    const { container } = render(<ChatPanel />);

    await askQuestionThroughUi("show me the authentication function");

    await waitFor(() => {
      expect(container.querySelector(".wiki-chat-message.role-assistant pre code")).not.toBeNull();
    });
    const codeElement = container.querySelector(".wiki-chat-message.role-assistant pre code");
    expect(codeElement?.className).toMatch(/hljs/);
    expect(codeElement?.textContent).toContain("def authenticate_user");
  });

  it("renders an in-answer `path :: symbolId` reference as a clickable link to its documentation page", async () => {
    installFetchRouter({
      ask: () =>
        sseAskResponse(["Authentication is handled by `src/auth/login.py :: auth.authenticate_user`."], {
          answer: "Authentication is handled by `src/auth/login.py :: auth.authenticate_user`.",
          citedSymbolIds: ["auth.authenticate_user"],
          citedFilePaths: ["src/auth/login.py"],
        }),
    });
    const { container } = render(<ChatPanel />);

    await askQuestionThroughUi("where is authentication handled?");

    await waitFor(() => {
      const inAnswerLink = container.querySelector(
        '.wiki-chat-message.role-assistant p a[href="modules/login-a1.html#function_a1"]'
      );
      expect(inAnswerLink).not.toBeNull();
      expect(inAnswerLink?.textContent).toBe("authenticate_user");
    });
  });

  it("renders an unresolvable in-answer reference as plain inline code, not a broken link", async () => {
    installFetchRouter({
      ask: () =>
        sseAskResponse(["Handled by `src/unknown.py :: Unknown.thing`."], {
          answer: "Handled by `src/unknown.py :: Unknown.thing`.",
          citedSymbolIds: [],
          citedFilePaths: [],
        }),
    });
    const { container } = render(<ChatPanel />);

    await askQuestionThroughUi("where is this handled?");

    await waitFor(() => {
      expect(container.querySelector(".wiki-chat-message.role-assistant p code")).not.toBeNull();
    });
    const codeElement = container.querySelector(".wiki-chat-message.role-assistant p code");
    expect(codeElement?.textContent).toBe("src/unknown.py :: Unknown.thing");
    expect(container.querySelector(".wiki-chat-message.role-assistant a")).toBeNull();
  });

  it("renders a not-yet-closed code fence during streaming without crashing or breaking layout", async () => {
    let releaseDone: (() => void) | undefined;
    const doneGate = new Promise<void>((resolve) => {
      releaseDone = resolve;
    });
    installFetchRouter({
      ask: () => {
        const encoder = new TextEncoder();
        let step = 0;
        return {
          ok: true,
          status: 200,
          body: {
            getReader() {
              return {
                async read() {
                  if (step === 0) {
                    step += 1;
                    return {
                      done: false,
                      value: encoder.encode(`data: ${JSON.stringify({ fragment: "```python\ndef f():\n    " })}\n\n`),
                    };
                  }
                  if (step === 1) {
                    await doneGate;
                    step += 1;
                    return {
                      done: false,
                      value: encoder.encode(
                        `event: done\ndata: ${JSON.stringify({
                          answer: "```python\ndef f():\n    pass\n```",
                          citedSymbolIds: [],
                          citedFilePaths: [],
                        })}\n\n`
                      ),
                    };
                  }
                  return { done: true, value: undefined };
                },
              };
            },
          },
        };
      },
    });
    const { container } = render(<ChatPanel />);

    await askQuestionThroughUi("show me a function");

    await waitFor(() => {
      expect(container.querySelector(".wiki-chat-message.role-assistant")).not.toBeNull();
    });
    // The fence hasn't closed yet - rendering must not throw or blank the panel.
    expect(container.querySelector(".wiki-chat-panel")).not.toBeNull();

    releaseDone?.();

    await waitFor(() => {
      expect(container.querySelector(".wiki-chat-message.role-assistant pre code")).not.toBeNull();
    });
  });

  it("renders a truncated or malformed in-answer symbol reference as plain readable text without breaking the rest of the message", async () => {
    let releaseDone: (() => void) | undefined;
    const doneGate = new Promise<void>((resolve) => {
      releaseDone = resolve;
    });
    installFetchRouter({
      ask: () => {
        const encoder = new TextEncoder();
        let step = 0;
        return {
          ok: true,
          status: 200,
          body: {
            getReader() {
              return {
                async read() {
                  if (step === 0) {
                    step += 1;
                    return {
                      done: false,
                      value: encoder.encode(
                        `data: ${JSON.stringify({ fragment: "See `src/auth/login.py :: auth.authenticate" })}\n\n`
                      ),
                    };
                  }
                  if (step === 1) {
                    await doneGate;
                    step += 1;
                    return {
                      done: false,
                      value: encoder.encode(
                        `event: done\ndata: ${JSON.stringify({
                          answer: "See `src/auth/login.py :: auth.authenticate_user`.",
                          citedSymbolIds: ["auth.authenticate_user"],
                          citedFilePaths: ["src/auth/login.py"],
                        })}\n\n`
                      ),
                    };
                  }
                  return { done: true, value: undefined };
                },
              };
            },
          },
        };
      },
    });
    const { container } = render(<ChatPanel />);

    await askQuestionThroughUi("where is authentication handled?");

    await waitFor(() => {
      expect(container.querySelector(".wiki-chat-message.role-assistant")).not.toBeNull();
    });
    // The reference's closing backtick hasn't streamed in yet - it must
    // render as plain text, never as a broken/half-formed link.
    expect(container.querySelector(".wiki-chat-message.role-assistant a")).toBeNull();

    releaseDone?.();

    await waitFor(() => {
      const link = container.querySelector(
        '.wiki-chat-message.role-assistant p a[href="modules/login-a1.html#function_a1"]'
      );
      expect(link).not.toBeNull();
    });
  });

  it("shows a clear error message when the chat API returns a structured error", async () => {
    installFetchRouter({
      ask: () =>
        jsonResponse(503, { code: "local_dependency_unavailable", message: "Local LLM is unavailable." }),
    });
    render(<ChatPanel />);

    await askQuestionThroughUi("where is this handled?");

    await waitFor(() => {
      expect(screen.getByText("Local LLM is unavailable.")).toBeInTheDocument();
    });
  });

  it("resumes a session id carried in the page URL instead of creating a new one", async () => {
    window.history.pushState({}, "", "/?chatSession=session-1");
    let createSessionCalls = 0;
    installFetchRouter({
      onCreateSession: () => {
        createSessionCalls += 1;
      },
      history: () =>
        jsonResponse(200, {
          sessionId: "session-1",
          messages: [
            {
              role: "user",
              content: "where is authentication handled?",
              citedSymbolIds: [],
              citedFilePaths: [],
              timestamp: "2026-08-19T00:00:00Z",
            },
            {
              role: "assistant",
              content: "Authentication is handled by authenticate_user.",
              citedSymbolIds: ["auth.authenticate_user"],
              citedFilePaths: ["src/auth/login.py"],
              timestamp: "2026-08-19T00:00:01Z",
            },
          ],
        }),
    });

    render(<ChatPanel />);

    await waitFor(() => {
      expect(screen.getByText("Authentication is handled by authenticate_user.")).toBeInTheDocument();
    });
    expect(screen.getByText("where is authentication handled?")).toBeInTheDocument();
    expect(createSessionCalls).toBe(0);
  });

  it("writes the newly created session id onto the page URL when the first question is asked with no id present", async () => {
    let createSessionCalls = 0;
    installFetchRouter({
      onCreateSession: () => {
        createSessionCalls += 1;
      },
      ask: () => sseAskResponse(["Handled elsewhere."], { answer: "Handled elsewhere.", citedSymbolIds: [], citedFilePaths: [] }),
    });

    render(<ChatPanel />);
    expect(window.location.search).toBe("");

    await askQuestionThroughUi("where is this handled?");

    await waitFor(() => {
      expect(screen.getByText("Handled elsewhere.")).toBeInTheDocument();
    });
    expect(createSessionCalls).toBe(1);
    expect(window.location.search).toContain("chatSession=session-1");
  });

  it("clears an unresolvable session id from the URL and starts a fresh conversation", async () => {
    window.history.pushState({}, "", "/?chatSession=stale-session");
    let createSessionCalls = 0;
    installFetchRouter({
      onCreateSession: () => {
        createSessionCalls += 1;
      },
      history: () => jsonResponse(404, { code: "session_not_found", message: "No session with id 'stale-session'." }),
      ask: () => sseAskResponse(["Handled elsewhere."], { answer: "Handled elsewhere.", citedSymbolIds: [], citedFilePaths: [] }),
    });

    render(<ChatPanel />);

    const input = await screen.findByLabelText("Ask a question about this repository");
    await waitFor(() => {
      expect(input).not.toBeDisabled();
    });
    expect(window.location.search).not.toContain("stale-session");

    await askQuestionThroughUi("where is this handled?");

    await waitFor(() => {
      expect(screen.getByText("Handled elsewhere.")).toBeInTheDocument();
    });
    expect(createSessionCalls).toBe(1);
    expect(window.location.search).toContain("chatSession=session-1");
  });

  it("keeps the question input disabled until the mount-time history fetch for a present session id settles", async () => {
    window.history.pushState({}, "", "/?chatSession=session-1");
    let releaseHistory: (() => void) | undefined;
    const historyGate = new Promise<void>((resolve) => {
      releaseHistory = resolve;
    });
    installFetchRouter({
      history: () => historyGate.then(() => jsonResponse(200, { sessionId: "session-1", messages: [] })),
    });

    render(<ChatPanel />);

    const input = await screen.findByLabelText("Ask a question about this repository");
    expect(input).toBeDisabled();

    releaseHistory?.();

    await waitFor(() => {
      expect(input).not.toBeDisabled();
    });
  });
});

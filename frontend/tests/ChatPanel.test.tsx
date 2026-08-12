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

function installFetchRouter(handlers: {
  ask?: () => ReturnType<typeof jsonResponse>;
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("search-index.json")) {
        return jsonResponse(200, { generatedAt: "2026-08-12T00:00:00Z", entries: SEARCH_ENTRIES });
      }
      if (url === "/sessions" && init?.method === "POST") {
        return jsonResponse(201, { sessionId: "session-1" });
      }
      if (url.startsWith("/sessions/") && init?.method === "POST") {
        return handlers.ask ? handlers.ask() : jsonResponse(200, { answer: "", citedSymbolIds: [], citedFilePaths: [] });
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
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the generated answer with a resolvable citation as a working link", async () => {
    installFetchRouter({
      ask: () =>
        jsonResponse(200, {
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

  it("renders an unresolvable citation as a plain label, not a broken link", async () => {
    installFetchRouter({
      ask: () =>
        jsonResponse(200, {
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
});

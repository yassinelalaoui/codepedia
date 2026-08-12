import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SearchWidget } from "../src/components/SearchWidget";
import { _resetSearchIndexCacheForTests } from "../src/lib/searchIndex";

const SAMPLE_ENTRIES = [
  {
    name: "authenticate_user",
    kind: "function",
    symbolId: "function_a1",
    filePath: "src/auth/login.py",
    pageUrl: "modules/login-a1.html#function_a1",
  },
  {
    name: "authenticate_admin",
    kind: "function",
    symbolId: "function_b2",
    filePath: "src/auth/admin.py",
    pageUrl: "modules/admin-b2.html#function_b2",
  },
];

function mockFetchOk(entries: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ generatedAt: "2026-08-12T00:00:00Z", entries }),
    })
  );
}

describe("SearchWidget", () => {
  beforeEach(() => {
    _resetSearchIndexCacheForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("filters results as the user types and each result carries disambiguating context", async () => {
    mockFetchOk(SAMPLE_ENTRIES);
    render(<SearchWidget />);

    const input = await screen.findByLabelText("Search symbols and functions");
    fireEvent.change(input, { target: { value: "authenticate" } });

    await waitFor(() => {
      expect(screen.getAllByRole("link")).toHaveLength(2);
    });
    expect(screen.getByText(/src\/auth\/login\.py/)).toBeInTheDocument();
    expect(screen.getByText(/src\/auth\/admin\.py/)).toBeInTheDocument();
  });

  it("navigates to the selected result's pageUrl", async () => {
    mockFetchOk(SAMPLE_ENTRIES);
    render(<SearchWidget />);

    const input = await screen.findByLabelText("Search symbols and functions");
    fireEvent.change(input, { target: { value: "authenticate_user" } });

    await waitFor(() => {
      expect(screen.getByRole("link", { name: /authenticate_user/ })).toHaveAttribute(
        "href",
        "modules/login-a1.html#function_a1"
      );
    });
  });

  it("shows a clear no-results message for an unmatched query", async () => {
    mockFetchOk(SAMPLE_ENTRIES);
    render(<SearchWidget />);

    const input = await screen.findByLabelText("Search symbols and functions");
    fireEvent.change(input, { target: { value: "does-not-exist" } });

    await waitFor(() => {
      expect(screen.getByText(/No results for "does-not-exist"/)).toBeInTheDocument();
    });
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });
});

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { HistoryList } from "../src/components/HistoryList";
import type { HistoryEntry } from "../src/lib/hubApiClient";

/** Spec FR-028, FR-031b. */

function entry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    stateId: "0123456789abcdef",
    repositoryPath: "C:/code/project",
    lastIndexedAt: "2026-09-01T10:00:00",
    available: true,
    open: false,
    ...overrides,
  };
}

describe("HistoryList", () => {
  it("shows an empty state before anything has been analysed", () => {
    render(<HistoryList entries={[]} onOpen={vi.fn()} onCloseServer={vi.fn()} onRemove={vi.fn()} />);

    expect(screen.getByText(/Nothing analysed yet/)).toBeInTheDocument();
  });

  it("renders one row per analysed repository", () => {
    render(
      <HistoryList
        entries={[entry(), entry({ stateId: "fedcba9876543210", repositoryPath: "C:/code/other" })]}
        onOpen={vi.fn()}
        onCloseServer={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders rows in the order given, which is newest first", () => {
    render(
      <HistoryList
        entries={[
          entry({ stateId: "aaaaaaaaaaaaaaaa", repositoryPath: "C:/code/newest" }),
          entry({ stateId: "bbbbbbbbbbbbbbbb", repositoryPath: "C:/code/oldest" }),
        ]}
        onOpen={vi.fn()}
        onCloseServer={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("newest");
    expect(rows[1]).toHaveTextContent("oldest");
  });

  it("shows both the folder name and its full path", () => {
    render(<HistoryList entries={[entry()]} onOpen={vi.fn()} onCloseServer={vi.fn()} onRemove={vi.fn()} />);

    expect(screen.getByText("project")).toBeInTheDocument();
    expect(screen.getByText("C:/code/project")).toBeInTheDocument();
  });

  it("marks a repository whose folder is gone rather than hiding it", () => {
    // Spec FR-031b: its documentation is still readable, and hiding it would
    // strand generated output with no way to reach or remove it.
    render(<HistoryList entries={[entry({ available: false })]} onOpen={vi.fn()} onCloseServer={vi.fn()} onRemove={vi.fn()} />);

    expect(screen.getByText("folder missing")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("opens a repository when its row is activated", () => {
    const onOpen = vi.fn();
    const target = entry();
    render(<HistoryList entries={[target]} onOpen={onOpen} onCloseServer={vi.fn()} onRemove={vi.fn()} />);

    fireEvent.click(screen.getByTitle("C:/code/project"));

    expect(onOpen).toHaveBeenCalledWith(target);
  });

  it("disables activation while an analysis is running", () => {
    render(<HistoryList entries={[entry()]} onOpen={vi.fn()} onCloseServer={vi.fn()} onRemove={vi.fn()} busy />);

    expect(screen.getByTitle("C:/code/project")).toBeDisabled();
  });
});

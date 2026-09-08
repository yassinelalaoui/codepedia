import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { HistoryRowMenu } from "../src/components/HistoryRowMenu";
import type { HistoryEntry } from "../src/lib/hubApiClient";

/**
 * Spec FR-033, FR-034, FR-040.
 *
 * The absence of a re-analyse action is asserted, not merely omitted: opening a
 * repository already brings it up to date, so re-adding that action later would
 * be a regression rather than a feature.
 */

const ENTRY: HistoryEntry = {
  stateId: "0123456789abcdef",
  repositoryPath: "C:/code/project",
  lastIndexedAt: "2026-09-01T10:00:00",
  available: true,
};

function open(): void {
  fireEvent.click(screen.getByRole("button", { name: /Actions for/ }));
}

describe("HistoryRowMenu", () => {
  it("offers exactly Properties, Open and Remove", () => {
    render(<HistoryRowMenu entry={ENTRY} onOpen={vi.fn()} onRemove={vi.fn()} />);
    open();

    const items = screen.getAllByRole("menuitem");
    expect(items.map((item) => item.textContent)).toEqual(["Properties", "Open", "Remove"]);
  });

  it("offers no re-analyse action", () => {
    render(<HistoryRowMenu entry={ENTRY} onOpen={vi.fn()} onRemove={vi.fn()} />);
    open();

    expect(screen.queryByRole("menuitem", { name: /re-?analyse|re-?index/i })).not.toBeInTheDocument();
  });

  it("shows the full path and last-analysed time in Properties", () => {
    render(<HistoryRowMenu entry={ENTRY} onOpen={vi.fn()} onRemove={vi.fn()} />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Properties" }));

    const dialog = screen.getByRole("dialog", { name: "Repository properties" });
    expect(dialog).toHaveTextContent("C:/code/project");
    expect(dialog).toHaveTextContent("2026-09-01T10:00:00");
  });

  it("says so in Properties when the folder is gone", () => {
    render(
      <HistoryRowMenu entry={{ ...ENTRY, available: false }} onOpen={vi.fn()} onRemove={vi.fn()} />,
    );
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Properties" }));

    expect(screen.getByRole("dialog")).toHaveTextContent("no longer on this machine");
  });

  it("opens the repository from the menu", () => {
    const onOpen = vi.fn();
    render(<HistoryRowMenu entry={ENTRY} onOpen={onOpen} onRemove={vi.fn()} />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Open" }));

    expect(onOpen).toHaveBeenCalled();
  });

  it("never removes without a confirmation that names the repository", () => {
    const onRemove = vi.fn();
    render(<HistoryRowMenu entry={ENTRY} onOpen={vi.fn()} onRemove={onRemove} />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove" }));

    expect(onRemove).not.toHaveBeenCalled();
    const confirm = screen.getByRole("alertdialog", { name: "Confirm removal" });
    expect(confirm).toHaveTextContent("C:/code/project");
  });

  it("says what removal does and does not touch", () => {
    render(<HistoryRowMenu entry={ENTRY} onOpen={vi.fn()} onRemove={vi.fn()} />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove" }));

    const confirm = screen.getByRole("alertdialog");
    expect(confirm).toHaveTextContent(/documentation, index and metadata/);
    expect(confirm).toHaveTextContent(/repository's own files are not touched/);
  });

  it("removes once confirmed", () => {
    const onRemove = vi.fn();
    render(<HistoryRowMenu entry={ENTRY} onOpen={vi.fn()} onRemove={onRemove} />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it("deletes nothing when the confirmation is declined", () => {
    const onRemove = vi.fn();
    render(<HistoryRowMenu entry={ENTRY} onOpen={vi.fn()} onRemove={onRemove} />);
    open();
    fireEvent.click(screen.getByRole("menuitem", { name: "Remove" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onRemove).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("closes on Escape", () => {
    render(<HistoryRowMenu entry={ENTRY} onOpen={vi.fn()} onRemove={vi.fn()} />);
    open();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

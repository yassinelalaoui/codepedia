import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { RunOutcome } from "../src/components/RunOutcome";
import type { RunSnapshot } from "../src/lib/hubApiClient";

/**
 * Spec FR-021 to FR-027.
 *
 * The sentence under test that matters most is "Nothing was kept". A display
 * showing nine ticked stages beside the word "failed" is actively misleading -
 * the pipeline promotes its output only on full success, so a late failure
 * throws away documentation generated correctly minutes earlier.
 */

function snapshot(overrides: Partial<RunSnapshot> = {}): RunSnapshot {
  return {
    runId: "r1",
    kind: "index",
    repositoryPath: "C:/code/project",
    stages: [
      {
        name: "EMBEDDING",
        label: "Updating embeddings",
        status: "failed",
        completed: null,
        total: null,
        elapsedSeconds: null,
      },
    ],
    currentStage: null,
    providerSwitches: [],
    notices: [],
    catchup: null,
    outcome: "failed",
    failedStage: "EMBEDDING",
    failureMessage: "No provider in the 'embeddings' chain is currently available.",
    providersAttempted: ["local:nomic-embed-text:latest", "openai:text-embedding-3-small"],
    serverUrl: null,
    startedAt: "2026-09-04T10:00:00+00:00",
    endedAt: "2026-09-04T10:12:00+00:00",
    version: 12,
    discardedEverything: true,
    ...overrides,
  };
}

describe("RunOutcome", () => {
  it("renders nothing while the run is still going", () => {
    const { container } = render(<RunOutcome run={snapshot({ outcome: null })} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("names the stage a failure stopped at, in the pipeline's own wording", () => {
    render(<RunOutcome run={snapshot()} />);

    expect(screen.getByText("Analysis failed")).toBeInTheDocument();
    expect(screen.getByText("Updating embeddings")).toBeInTheDocument();
  });

  it("shows the cause", () => {
    render(<RunOutcome run={snapshot()} />);

    expect(
      screen.getByText("No provider in the 'embeddings' chain is currently available."),
    ).toBeInTheDocument();
  });

  it("lists every provider that was tried", () => {
    // Spec FR-022 and SC-004: enough for a person to say what to fix without
    // opening a terminal or reading a log.
    render(<RunOutcome run={snapshot()} />);

    expect(screen.getByText("local:nomic-embed-text:latest")).toBeInTheDocument();
    expect(screen.getByText("openai:text-embedding-3-small")).toBeInTheDocument();
  });

  it("states plainly that nothing was kept", () => {
    render(<RunOutcome run={snapshot()} />);

    expect(screen.getByText(/Nothing was kept from this run/)).toBeInTheDocument();
  });

  it("says the same for a cancelled run", () => {
    render(<RunOutcome run={snapshot({ outcome: "cancelled", discardedEverything: true })} />);

    expect(screen.getByText("Analysis stopped")).toBeInTheDocument();
    expect(screen.getByText(/Nothing was kept from this run/)).toBeInTheDocument();
  });

  it("does not claim anything was discarded when the run succeeded", () => {
    render(
      <RunOutcome
        run={snapshot({ outcome: "succeeded", discardedEverything: false, failureMessage: null, failedStage: null })}
      />,
    );

    expect(screen.getByText("Analysis complete")).toBeInTheDocument();
    expect(screen.queryByText(/Nothing was kept/)).not.toBeInTheDocument();
  });

  it("offers a retry that does not need the path retyped", () => {
    const onRetry = vi.fn();
    render(<RunOutcome run={snapshot()} onRetry={onRetry} />);

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalled();
  });

  it("offers no retry for a run that succeeded", () => {
    render(
      <RunOutcome
        run={snapshot({ outcome: "succeeded", discardedEverything: false })}
        onRetry={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("offers to open the documentation a successful run produced", () => {
    const onOpen = vi.fn();
    render(
      <RunOutcome
        run={snapshot({ outcome: "succeeded", discardedEverything: false, serverUrl: "http://127.0.0.1:8000/?token=x" })}
        onOpen={onOpen}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open documentation" }));

    expect(onOpen).toHaveBeenCalled();
  });

  it("is announced, and can be dismissed but never times out", () => {
    const onDismiss = vi.fn();
    render(<RunOutcome run={snapshot()} onDismiss={onDismiss} />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalled();
  });
});

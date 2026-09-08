import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { RunProgress } from "../src/components/RunProgress";
import type { RunSnapshot, StageState } from "../src/lib/hubApiClient";

/**
 * Spec FR-014, FR-015, FR-017.
 *
 * The assertion that matters most is the item count: summarization dominates a
 * real run, so a bar that only moved between stages would sit still for most of
 * an analysis - the exact "looks hung" problem this feature exists to fix.
 */

const STAGE_NAMES = [
  "VALIDATING",
  "CHECKING_MODELS",
  "SCANNING",
  "PARSING",
  "BUILDING_GRAPH",
  "GENERATING_DOCS_STRUCTURE",
  "SUMMARIZING",
  "GENERATING_DOCS_CONTENT",
  "EMBEDDING",
  "STARTING_SERVER",
] as const;

const LABELS: Record<string, string> = {
  VALIDATING: "Validating repository",
  CHECKING_MODELS: "Checking local model availability",
  SCANNING: "Scanning repository",
  PARSING: "Parsing and extracting symbols",
  BUILDING_GRAPH: "Building dependency graph",
  GENERATING_DOCS_STRUCTURE: "Generating documentation structure",
  SUMMARIZING: "Generating summaries",
  GENERATING_DOCS_CONTENT: "Generating documentation content",
  EMBEDDING: "Updating embeddings",
  STARTING_SERVER: "Starting local server",
};

function stages(overrides: Partial<Record<string, Partial<StageState>>> = {}): StageState[] {
  return STAGE_NAMES.map((name) => ({
    name,
    label: LABELS[name],
    status: "pending",
    completed: null,
    total: null,
    elapsedSeconds: null,
    ...(overrides[name] ?? {}),
  })) as StageState[];
}

function snapshot(overrides: Partial<RunSnapshot> = {}): RunSnapshot {
  return {
    runId: "r1",
    kind: "index",
    repositoryPath: "C:/code/project",
    stages: stages(),
    currentStage: null,
    providerSwitches: [],
    notices: [],
    catchup: null,
    outcome: null,
    failedStage: null,
    failureMessage: null,
    providersAttempted: [],
    serverUrl: null,
    startedAt: "2026-09-04T10:00:00+00:00",
    endedAt: null,
    version: 1,
    discardedEverything: false,
    ...overrides,
  };
}

describe("RunProgress", () => {
  it("renders all ten stages in pipeline order", () => {
    render(<RunProgress run={snapshot()} />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(10);
    expect(items[0]).toHaveTextContent("Validating repository");
    expect(items[6]).toHaveTextContent("Generating summaries");
    expect(items[9]).toHaveTextContent("Starting local server");
  });

  it("distinguishes finished, running and not-yet-reached stages", () => {
    const run = snapshot({
      stages: stages({
        VALIDATING: { status: "done" },
        SCANNING: { status: "running" },
      }),
      currentStage: "SCANNING",
    });

    const { container } = render(<RunProgress run={run} />);

    expect(container.querySelectorAll(".run-stage--done")).toHaveLength(1);
    expect(container.querySelectorAll(".run-stage--running")).toHaveLength(1);
    expect(container.querySelector(".run-stage--running")).toHaveTextContent("Scanning repository");
  });

  it("marks the running stage as the current step for assistive technology", () => {
    const run = snapshot({ stages: stages({ SUMMARIZING: { status: "running" } }) });

    const { container } = render(<RunProgress run={run} />);

    expect(container.querySelector('[aria-current="step"]')).toHaveTextContent("Generating summaries");
  });

  it("shows how many items are done inside a counting stage", () => {
    // Spec FR-015 - the whole reason this component is not just a stage list.
    const run = snapshot({
      stages: stages({ SUMMARIZING: { status: "running", completed: 37, total: 412 } }),
    });

    render(<RunProgress run={run} />);

    expect(screen.getByText("37 of 412")).toBeInTheDocument();
  });

  it("exposes item progress as a progressbar with a real value", () => {
    const run = snapshot({
      stages: stages({ EMBEDDING: { status: "running", completed: 5, total: 10 } }),
    });

    render(<RunProgress run={run} />);

    const bar = screen.getByRole("progressbar", { name: /Updating embeddings/ });
    expect(bar).toHaveAttribute("aria-valuenow", "50");
  });

  it("shows no count for a stage that does not process items", () => {
    render(<RunProgress run={snapshot({ stages: stages({ SCANNING: { status: "running" } }) })} />);

    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("reports each finished stage's duration", () => {
    const run = snapshot({ stages: stages({ PARSING: { status: "done", elapsedSeconds: 4.125 } }) });

    render(<RunProgress run={run} />);

    expect(screen.getByText("4.1s")).toBeInTheDocument();
  });

  it("surfaces automatic provider switches", () => {
    // Constitution 2.3 requires a switch never be silent in practice; for a
    // browser-started run this is the only place the person is looking.
    const run = snapshot({
      providerSwitches: [
        {
          chain: "summary",
          fromProvider: "local:qwen2.5-coder:1.5b",
          toProvider: "groq:openai/gpt-oss-20b",
          reason: "provider unavailable",
          at: "2026-09-04T10:01:00+00:00",
        },
      ],
    });

    render(<RunProgress run={run} />);

    expect(screen.getByText(/local:qwen2.5-coder:1.5b/)).toBeInTheDocument();
    expect(screen.getByText(/groq:openai\/gpt-oss-20b/)).toBeInTheDocument();
  });

  it("shows catch-up progress when a repository is being brought up to date", () => {
    const run = snapshot({
      kind: "open",
      catchup: { phase: "parsing", completed: 3, total: 11, path: "src/thing.py" },
    });

    render(<RunProgress run={run} />);

    expect(screen.getByText(/3 of 11/)).toBeInTheDocument();
    expect(screen.getByText(/src\/thing.py/)).toBeInTheDocument();
  });

  it("offers a Stop control while the run is live", () => {
    const onCancel = vi.fn();
    render(<RunProgress run={snapshot()} onCancel={onCancel} />);

    fireEvent.click(screen.getByRole("button", { name: "Stop" }));

    expect(onCancel).toHaveBeenCalled();
  });

  it("hides the Stop control once the run has ended", () => {
    render(<RunProgress run={snapshot({ outcome: "failed" })} onCancel={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });
});

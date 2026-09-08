import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { IndexBar } from "../src/components/IndexBar";

/** Spec FR-008, FR-010: type a path, press go, and be told when it is refused. */

describe("IndexBar", () => {
  it("renders a labelled field and a submit control", () => {
    render(<IndexBar onSubmit={vi.fn()} />);

    expect(screen.getByLabelText("Repository folder")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyse" })).toBeInTheDocument();
  });

  it("keeps submit disabled while the field is empty", () => {
    render(<IndexBar onSubmit={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Analyse" })).toBeDisabled();
  });

  it("keeps submit disabled for whitespace alone", () => {
    render(<IndexBar onSubmit={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Repository folder"), { target: { value: "   " } });

    expect(screen.getByRole("button", { name: "Analyse" })).toBeDisabled();
  });

  it("submits the trimmed path", () => {
    const onSubmit = vi.fn();
    render(<IndexBar onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Repository folder"), {
      target: { value: "  C:/code/project  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyse" }));

    expect(onSubmit).toHaveBeenCalledWith("C:/code/project");
  });

  it("submits on Enter, because a form should", () => {
    const onSubmit = vi.fn();
    const { container } = render(<IndexBar onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Repository folder"), { target: { value: "C:/code" } });
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);

    expect(onSubmit).toHaveBeenCalledWith("C:/code");
  });

  it("renders the server's rejection verbatim and announces it", () => {
    // Spec SC-004: the server's message is the useful one - it names what is
    // wrong with the path. Replacing it with a generic string here would throw
    // away the only part a person can act on.
    const message = "C:/code/thing.txt is a file, not a folder. Point this at the repository's folder.";
    render(<IndexBar onSubmit={vi.fn()} error={message} />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(message);
  });

  it("marks the field invalid and describes it when there is an error", () => {
    render(<IndexBar onSubmit={vi.fn()} error="nope" />);

    const field = screen.getByLabelText("Repository folder");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAttribute("aria-describedby", "index-bar-error");
  });

  it("disables the field and the button while an analysis is starting", () => {
    render(<IndexBar onSubmit={vi.fn()} disabled />);

    expect(screen.getByLabelText("Repository folder")).toBeDisabled();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("is reachable by keyboard alone", () => {
    render(<IndexBar onSubmit={vi.fn()} />);

    const field = screen.getByLabelText("Repository folder");
    field.focus();
    expect(document.activeElement).toBe(field);
  });
});

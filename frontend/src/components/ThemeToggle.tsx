import { useEffect, useState } from "react";
import {
  type ThemePreference,
  readPreference,
  setPreference,
  watchSystemTheme,
} from "../lib/theme";

/**
 * The reader's System / Light / Dark control (036 spec FR-001, FR-002).
 *
 * Segmented rather than a cycling icon button or a dropdown: the spec requires
 * three reachable states, System is the default every new reader starts in, and
 * FR-002 requires the current state to be readable *without* interacting - which
 * a dropdown cannot do and a cycle button only does one state at a time.
 *
 * Plain `<button aria-pressed>` rather than `role="radiogroup"`: a radiogroup
 * owes the reader roving-tabindex arrow-key handling, and getting that subtly
 * wrong is a worse accessibility outcome than three ordinary buttons that Tab
 * and Enter already operate correctly (FR-012, SC-009).
 *
 * The applying is not done here - `lib/theme.ts` owns that, because the
 * pre-paint script in `layout.html.jinja` has to do the same thing before this
 * component exists (FR-008).
 */

const OPTIONS: ReadonlyArray<{ value: ThemePreference; label: string }> = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function ThemeToggle(): JSX.Element {
  // Seeded from storage rather than defaulted to "system": the pre-paint script
  // has already applied the stored value, and starting from anything else would
  // render a control that disagrees with the page it sits on.
  const [preference, setPreferenceState] = useState<ThemePreference>(() => readPreference());

  useEffect(() => {
    // A System reader follows a live OS switch (FR-005). Installed here because
    // this component's lifetime is the page's lifetime; the teardown exists for
    // tests and StrictMode's double-mount.
    return watchSystemTheme();
  }, []);

  const choose = (value: ThemePreference): void => {
    setPreferenceState(value);
    setPreference(value);
  };

  return (
    <div
      className="theme-toggle flex items-center gap-0.5 p-0.5 rounded-sm bg-sunken border border-line"
      role="group"
      aria-label="Colour theme"
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          className="theme-toggle-option flex-1 py-1 px-1.5 rounded-[3px] text-[11.5px] text-ink-soft bg-transparent border-0 cursor-pointer hover:text-ink aria-pressed:bg-surface aria-pressed:text-ink aria-pressed:font-medium aria-pressed:shadow-1"
          aria-pressed={preference === option.value}
          onClick={() => choose(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

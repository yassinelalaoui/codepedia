import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { SearchWidget } from "./components/SearchWidget";
import { ChatPanel } from "./components/ChatPanel";
import { TocHighlighter } from "./components/TocHighlighter";
import { ThemeToggle } from "./components/ThemeToggle";
import { captureApiTokenFromUrl } from "./lib/apiToken";
import { enhanceDiagrams, installDiagramThemeSync } from "./lib/diagramViewport";
import { installFragmentScrolling } from "./lib/fragmentScroll";
import "./styles.css";

// Before anything mounts: ChatPanel fires a history request on its first
// render if the URL names a session, and that request needs the token.
captureApiTokenFromUrl();

function mount(elementId: string, node: ReactNode): void {
  const container = document.getElementById(elementId);
  if (!container) return;
  createRoot(container).render(<StrictMode>{node}</StrictMode>);
}

// The theme is already applied by the inline script in layout.html.jinja's
// <head> before this bundle parses (036 spec FR-008); this only renders the
// control that changes it, and installs the OS-change listener (FR-005).
mount("wiki-theme-root", <ThemeToggle />);
mount("wiki-search-root", <SearchWidget />);
mount("wiki-chat-root", <ChatPanel />);
// Headless: the rail is server-rendered, this only tracks the active section.
mount("wiki-toc-root", <TocHighlighter />);

// Not a React component, for the same reason TocHighlighter renders null: the
// diagrams are drawn into the page by the vendored Mermaid global, and this only
// wraps what is already there. Both wirings are needed and neither is redundant
// - the event can fire before this bundle finishes parsing, and this load-time
// sweep can run before Mermaid has drawn anything. `enhanceDiagrams` is
// idempotent, which is what makes running both safe.
document.addEventListener("wiki:mermaid-rendered", () => {
  enhanceDiagrams();
});
enhanceDiagrams();

// A theme change repaints the page from CSS tokens, but a Mermaid SVG has its
// colours baked in when it is drawn, so it has to be redrawn (036 spec FR-013).
// The reader's zoom and pan survive because only the <svg> is swapped, never
// the transformed wrapper holding that state (FR-013a).
installDiagramThemeSync();

// Fragment links need help now that page content scrolls inside `.main` rather
// than as the document; see lib/fragmentScroll.ts for why the initial page load
// is the case that actually breaks.
installFragmentScrolling();

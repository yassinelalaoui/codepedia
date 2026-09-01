import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { SearchWidget } from "./components/SearchWidget";
import { ChatPanel } from "./components/ChatPanel";
import { TocHighlighter } from "./components/TocHighlighter";
import { captureApiTokenFromUrl } from "./lib/apiToken";
import { enhanceDiagrams } from "./lib/diagramViewport";
import "./styles.css";

// Before anything mounts: ChatPanel fires a history request on its first
// render if the URL names a session, and that request needs the token.
captureApiTokenFromUrl();

function mount(elementId: string, node: ReactNode): void {
  const container = document.getElementById(elementId);
  if (!container) return;
  createRoot(container).render(<StrictMode>{node}</StrictMode>);
}

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

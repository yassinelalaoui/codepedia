import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { SearchWidget } from "./components/SearchWidget";
import { ChatPanel } from "./components/ChatPanel";
import { TocHighlighter } from "./components/TocHighlighter";
import { captureApiTokenFromUrl } from "./lib/apiToken";
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

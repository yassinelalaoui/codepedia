import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { SearchWidget } from "./components/SearchWidget";
import { ChatPanel } from "./components/ChatPanel";
import { TocHighlighter } from "./components/TocHighlighter";
import "./styles.css";

function mount(elementId: string, node: ReactNode): void {
  const container = document.getElementById(elementId);
  if (!container) return;
  createRoot(container).render(<StrictMode>{node}</StrictMode>);
}

mount("wiki-search-root", <SearchWidget />);
mount("wiki-chat-root", <ChatPanel />);
// Headless: the rail is server-rendered, this only tracks the active section.
mount("wiki-toc-root", <TocHighlighter />);

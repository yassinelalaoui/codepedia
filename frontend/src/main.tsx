import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { SearchWidget } from "./components/SearchWidget";
import { ChatPanel } from "./components/ChatPanel";
import "./styles.css";

function mount(elementId: string, node: ReactNode): void {
  const container = document.getElementById(elementId);
  if (!container) return;
  createRoot(container).render(<StrictMode>{node}</StrictMode>);
}

mount("wiki-search-root", <SearchWidget />);
mount("wiki-chat-root", <ChatPanel />);

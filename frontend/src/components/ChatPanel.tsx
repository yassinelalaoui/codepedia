import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { askQuestion, ChatApiError, createSession, getHistory } from "../lib/chatApiClient";
import { findByCitation, loadSearchIndex, type SearchIndexEntry } from "../lib/searchIndex";
import { createSymbolAwareCodeRenderer, rehypeHighlightOptions } from "../lib/markdownReferences";

/** Carries the session id on the page's own URL (028 US3) so a reload, a
 * copied link, or a different browser/device all resume the same
 * conversation via GET /sessions/{id}/messages - see
 * contracts/session-url-parameter.md. Replaces the localStorage-based
 * persistence (025), which couldn't survive a different browser/device. */
const CHAT_SESSION_PARAM = "chatSession";

type HistoryLoadState = "idle" | "loading" | "loaded" | "not-found";

function readSessionIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get(CHAT_SESSION_PARAM);
}

function writeSessionIdToUrl(sessionId: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set(CHAT_SESSION_PARAM, sessionId);
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

function clearSessionIdFromUrl(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete(CHAT_SESSION_PARAM);
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

type DeliveryState = "awaiting-first-fragment" | "streaming" | "complete" | "error";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  citedSymbolIds: string[];
  citedFilePaths: string[];
  deliveryState: DeliveryState;
}

interface Citation {
  label: string;
  pageUrl: string | null;
}

function resolveCitations(
  message: DisplayMessage,
  entries: SearchIndexEntry[]
): Citation[] {
  const citations: Citation[] = [];
  const coveredFilePaths = new Set<string>();

  for (const symbolId of message.citedSymbolIds) {
    const match = findByCitation(entries, { symbolId });
    if (match) coveredFilePaths.add(match.filePath);
    citations.push({ label: match ? match.name : symbolId, pageUrl: match ? match.pageUrl : null });
  }

  for (const filePath of message.citedFilePaths) {
    if (coveredFilePaths.has(filePath)) continue;
    const match = findByCitation(entries, { filePath });
    citations.push({ label: match ? match.name : filePath, pageUrl: match ? match.pageUrl : null });
  }

  return citations;
}

/** How close to the end still counts as "at the newest message".
 *
 * Sub-pixel rounding, a partially visible last line and fractional device pixel
 * ratios all leave a few pixels on the clock when the reader is, to their own
 * eyes, at the bottom. A strict `=== 0` test would report "scrolled away" for a
 * reader who has not scrolled at all, and then refuse to follow the answer. */
const PIN_TOLERANCE_PX = 40;

/** Composer height cap before it scrolls its own content, in rows. */
const MAX_COMPOSER_ROWS = 5;

export function ChatPanel() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [entries, setEntries] = useState<SearchIndexEntry[]>([]);
  const [isPinned, setIsPinned] = useState(true);
  const [historyLoadState, setHistoryLoadState] = useState<HistoryLoadState>(() =>
    readSessionIdFromUrl() ? "loading" : "idle"
  );
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const sessionIdRef = useRef<string | null>(null);
  const drawerToggleRef = useRef<HTMLButtonElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const symbolAwareCode = useMemo(() => createSymbolAwareCodeRenderer(entries), [entries]);

  /** Derived from the scroll position, never toggled.
   *
   * Auto-scrolling writes `scrollTop`, which fires `scroll`, which lands back
   * here - so this has to recompute from the container rather than flip a flag,
   * or the two would drive each other. A container that does not overflow yields
   * a non-positive distance and is therefore pinned, which is the right answer
   * for a short conversation. */
  function handleScroll(): void {
    const container = scrollRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    setIsPinned(distanceFromBottom <= PIN_TOLERANCE_PX);
  }

  /** Escape closes the drawer and hands focus back to the control that opened
   * it - without that a keyboard reader is dropped at the top of the document.
   * Closing changes nothing else: the same panel is being revealed, not rebuilt,
   * so the conversation, the pinned state and the composer all survive. */
  function handlePanelKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "Escape" || !isDrawerOpen) return;
    setIsDrawerOpen(false);
    drawerToggleRef.current?.focus();
  }

  function scrollToLatest(): void {
    const container = scrollRef.current;
    if (!container) return;
    // Not `scrollIntoView` or `scrollTo`: jsdom defines neither, and `scrollTop`
    // is the simplest thing that works in a real browser anyway.
    container.scrollTop = container.scrollHeight;
    setIsPinned(true);
  }

  // Before paint, so no intermediate scroll position is ever visible. Only while
  // pinned: a reader who has scrolled up to re-read something must not be
  // dragged back down by an answer still arriving.
  useLayoutEffect(() => {
    if (!isPinned) return;
    const container = scrollRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages, isPinned]);

  /** Grow to fit, capped, then scroll internally.
   *
   * Height is reset to `auto` before `scrollHeight` is read. Without that the
   * box can only ever grow: `scrollHeight` of an already-tall textarea reports
   * the tall height, so deleting text would never shrink it back. */
  useLayoutEffect(() => {
    const composer = composerRef.current;
    if (!composer) return;
    composer.style.height = "auto";
    const lineHeight = parseFloat(getComputedStyle(composer).lineHeight) || 20;
    const maxHeight = lineHeight * MAX_COMPOSER_ROWS;
    composer.style.height = `${Math.min(composer.scrollHeight, maxHeight)}px`;
    composer.style.overflowY = composer.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [question]);

  // `#wiki-chat-root` is emitted by the server-rendered layout, not by React, so
  // the open state has to be reflected onto it rather than expressed as a prop.
  // Same pattern TocHighlighter uses for the "On this page" rail: own no markup,
  // just toggle a class on markup the generator produced.
  useEffect(() => {
    const root = document.getElementById("wiki-chat-root");
    root?.classList.toggle("is-open", isDrawerOpen);
  }, [isDrawerOpen]);

  useEffect(() => {
    loadSearchIndex()
      .then(setEntries)
      .catch(() => setEntries([]));
  }, []);

  useEffect(() => {
    const urlSessionId = readSessionIdFromUrl();
    if (!urlSessionId) return;
    getHistory(urlSessionId)
      .then((history) => {
        sessionIdRef.current = urlSessionId;
        setMessages(
          history.messages.map((message) => ({
            role: message.role,
            content: message.content,
            citedSymbolIds: message.citedSymbolIds,
            citedFilePaths: message.citedFilePaths,
            deliveryState: "complete",
          }))
        );
        setHistoryLoadState("loaded");
      })
      .catch(() => {
        // The URL's session id no longer resolves (e.g. a fresh
        // index/repository) - drop it from the address and start a fresh
        // conversation instead of showing an error (FR-011).
        clearSessionIdFromUrl();
        setHistoryLoadState("not-found");
      });
  }, []);

  /** Enter sends; Shift+Enter inserts a newline.
   *
   * `preventDefault` is not optional on the send path: without it the question
   * is sent *and* the textarea inserts its newline, into the box that was just
   * cleared. */
  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    void handleSubmit(event);
  }

  async function handleSubmit(event: { preventDefault: () => void }) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || pending || historyLoadState === "loading") return;

    // Sending is a deliberate act whose whole point is to see the answer, so it
    // returns to the newest message even from a scrolled-up position - unlike an
    // answer merely arriving, which must leave the reader where they are.
    setIsPinned(true);
    setPending(true);
    setErrorMessage(null);
    // Added synchronously, before any await, so the activity indicator is
    // visible the instant the question is submitted (028 FR-001) rather
    // than only after the session-creation round trip resolves.
    setMessages((previous) => [
      ...previous,
      { role: "user", content: submittedQuestion, citedSymbolIds: [], citedFilePaths: [], deliveryState: "complete" },
      { role: "assistant", content: "", citedSymbolIds: [], citedFilePaths: [], deliveryState: "awaiting-first-fragment" },
    ]);
    setQuestion("");

    try {
      if (!sessionIdRef.current) {
        const session = await createSession();
        sessionIdRef.current = session.sessionId;
        writeSessionIdToUrl(session.sessionId);
      }

      const response = await askQuestion(sessionIdRef.current, submittedQuestion, (fragment) => {
        setMessages((previous) => {
          const next = [...previous];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + fragment, deliveryState: "streaming" };
          return next;
        });
      });
      setMessages((previous) => {
        const next = [...previous];
        next[next.length - 1] = {
          role: "assistant",
          content: response.answer,
          citedSymbolIds: response.citedSymbolIds,
          citedFilePaths: response.citedFilePaths,
          deliveryState: "complete",
        };
        return next;
      });
    } catch (error) {
      // Nothing is persisted server-side for a failed attempt (FR-007) -
      // drop the question/in-progress-answer pair optimistically rendered
      // above rather than leaving a stale indicator or partial answer.
      setMessages((previous) => previous.slice(0, -2));
      if (error instanceof ChatApiError && error.status === 401) {
        // The page loaded without the `?token=` the server printed - opening
        // any wiki page directly does that. The API's own message says as
        // much, but it is written for a caller, not for a reader.
        setErrorMessage(
          "This page was opened without the access token. Reopen the URL printed when the server started."
        );
      } else if (error instanceof ChatApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("The chat is unavailable right now. Please try again later.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      {/* Only visible below the narrow-window breakpoint, where the panel used
          to disappear outright. Rendered unconditionally rather than behind a
          matchMedia check: CSS decides visibility, so there is no JS branch to
          keep in step with the breakpoint - and jsdom defines no matchMedia. */}
      <button
        type="button"
        ref={drawerToggleRef}
        className="wiki-chat-drawer-toggle"
        aria-expanded={isDrawerOpen}
        onClick={() => setIsDrawerOpen((open) => !open)}
      >
        {isDrawerOpen ? "Close chat" : "Ask about this repository"}
      </button>
    <div className="wiki-chat-panel" onKeyDown={handlePanelKeyDown}>
      <div className="wiki-chat-panel-head">
        <h2>Ask about this repository</h2>
        <span className="wiki-chat-local-badge">
          <span className="led" aria-hidden="true" />
          Local only
        </span>
      </div>
      {/* One scroll container, always rendered, holding either state. The list
          used to be conditional, so a ref to it was null exactly when the first
          auto-scroll needed it, and the scroll listener had to be attached and
          torn down as the conversation appeared. */}
      <div className="wiki-chat-scroll" ref={scrollRef} onScroll={handleScroll}>
      {messages.length === 0 ? (
        <p className="wiki-chat-empty">
          Ask anything about this codebase — answers are grounded in the indexed code and cited.
        </p>
      ) : (
      <ul className="wiki-chat-messages">
        {messages.map((message, index) => (
          <li key={index} className={`wiki-chat-message role-${message.role}`}>
            {message.role === "assistant" && message.deliveryState === "awaiting-first-fragment" ? (
              <span className="wiki-chat-indicator" role="status" aria-label="Generating an answer…">
                <span className="wiki-chat-indicator-dot" />
                <span className="wiki-chat-indicator-dot" />
                <span className="wiki-chat-indicator-dot" />
                Generating an answer…
              </span>
            ) : message.role === "assistant" ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[[rehypeHighlight, rehypeHighlightOptions]]}
                components={{ code: symbolAwareCode }}
              >
                {message.content}
              </ReactMarkdown>
            ) : (
              <p>{message.content}</p>
            )}
            {message.role === "assistant" && (message.citedSymbolIds.length > 0 || message.citedFilePaths.length > 0) && (
              <ul className="wiki-chat-citations">
                {resolveCitations(message, entries).map((citation, citationIndex) => (
                  <li key={citationIndex}>
                    {citation.pageUrl ? <a href={citation.pageUrl}>{citation.label}</a> : <span>{citation.label}</span>}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      )}
      </div>
      {!isPinned && (
        <button
          type="button"
          className="wiki-chat-jump-latest"
          onClick={scrollToLatest}
        >
          Jump to latest
        </button>
      )}
      {errorMessage && <p className="wiki-chat-error">{errorMessage}</p>}
      <form onSubmit={handleSubmit}>
        <div className="wiki-chat-composer">
          <textarea
            ref={composerRef}
            rows={1}
            aria-label="Ask a question about this repository"
            placeholder="Ask a question about this repository…"
            value={question}
            disabled={pending || historyLoadState === "loading"}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleComposerKeyDown}
          />
          <button
            type="submit"
            className="wiki-chat-send"
            aria-label="Send question"
            disabled={pending || historyLoadState === "loading" || !question.trim()}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 12h15"/><path d="M13 6l6 6-6 6"/></svg>
          </button>
        </div>
        <p className="wiki-chat-foot-note">Runs on this machine — nothing is sent anywhere else.</p>
      </form>
    </div>
    </>
  );
}

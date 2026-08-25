import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
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

export function ChatPanel() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [entries, setEntries] = useState<SearchIndexEntry[]>([]);
  const [historyLoadState, setHistoryLoadState] = useState<HistoryLoadState>(() =>
    readSessionIdFromUrl() ? "loading" : "idle"
  );
  const sessionIdRef = useRef<string | null>(null);
  const symbolAwareCode = useMemo(() => createSymbolAwareCodeRenderer(entries), [entries]);

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

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || pending || historyLoadState === "loading") return;

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
      if (error instanceof ChatApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("The chat is unavailable right now. Please try again later.");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="wiki-chat-panel">
      <ul className="wiki-chat-messages">
        {messages.map((message, index) => (
          <li key={index} className={`wiki-chat-message role-${message.role}`}>
            {message.role === "assistant" && message.deliveryState === "awaiting-first-fragment" ? (
              <span className="wiki-chat-indicator" role="status" aria-label="Generating an answer…">
                <span className="wiki-chat-indicator-dot" />
                <span className="wiki-chat-indicator-dot" />
                <span className="wiki-chat-indicator-dot" />
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
      {errorMessage && <p className="wiki-chat-error">{errorMessage}</p>}
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          aria-label="Ask a question about this repository"
          placeholder="Ask a question about this repository…"
          value={question}
          disabled={pending || historyLoadState === "loading"}
          onChange={(event) => setQuestion(event.target.value)}
        />
      </form>
    </div>
  );
}

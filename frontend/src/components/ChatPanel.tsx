import { useEffect, useRef, useState, type FormEvent } from "react";
import { askQuestion, ChatApiError, createSession, getHistory } from "../lib/chatApiClient";
import { findByCitation, loadSearchIndex, type SearchIndexEntry } from "../lib/searchIndex";

/** Survives a wiki page reload (025) - the server-side session itself is
 * durable, but the browser still needs to remember which id to resume. */
const SESSION_STORAGE_KEY = "repo-scanner:chat-session-id";

interface DisplayMessage {
  role: "user" | "assistant";
  content: string;
  citedSymbolIds: string[];
  citedFilePaths: string[];
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
  const sessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    loadSearchIndex()
      .then(setEntries)
      .catch(() => setEntries([]));
  }, []);

  useEffect(() => {
    const storedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!storedSessionId) return;
    getHistory(storedSessionId)
      .then((history) => {
        sessionIdRef.current = storedSessionId;
        setMessages(
          history.messages.map((message) => ({
            role: message.role,
            content: message.content,
            citedSymbolIds: message.citedSymbolIds,
            citedFilePaths: message.citedFilePaths,
          }))
        );
      })
      .catch(() => {
        // The stored id no longer resolves (e.g. a fresh index/repository) -
        // fall back to creating a brand-new session on the next question.
        window.localStorage.removeItem(SESSION_STORAGE_KEY);
      });
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || pending) return;

    setPending(true);
    setErrorMessage(null);
    let placeholderAdded = false;
    try {
      if (!sessionIdRef.current) {
        const session = await createSession();
        sessionIdRef.current = session.sessionId;
        window.localStorage.setItem(SESSION_STORAGE_KEY, session.sessionId);
      }
      setMessages((previous) => [
        ...previous,
        { role: "user", content: submittedQuestion, citedSymbolIds: [], citedFilePaths: [] },
        { role: "assistant", content: "", citedSymbolIds: [], citedFilePaths: [] },
      ]);
      placeholderAdded = true;
      setQuestion("");

      const response = await askQuestion(sessionIdRef.current, submittedQuestion, (fragment) => {
        setMessages((previous) => {
          const next = [...previous];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + fragment };
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
        };
        return next;
      });
    } catch (error) {
      if (placeholderAdded) {
        // Nothing is persisted server-side for a failed attempt (FR-007) -
        // drop the question/in-progress-answer pair we optimistically
        // rendered rather than leaving a stray empty assistant bubble.
        setMessages((previous) => previous.slice(0, -2));
      }
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
            <p>{message.content}</p>
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
          disabled={pending}
          onChange={(event) => setQuestion(event.target.value)}
        />
      </form>
    </div>
  );
}

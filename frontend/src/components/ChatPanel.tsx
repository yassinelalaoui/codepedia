import { useEffect, useRef, useState, type FormEvent } from "react";
import { askQuestion, ChatApiError, createSession } from "../lib/chatApiClient";
import { findByCitation, loadSearchIndex, type SearchIndexEntry } from "../lib/searchIndex";

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

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || pending) return;

    setPending(true);
    setErrorMessage(null);
    try {
      if (!sessionIdRef.current) {
        const session = await createSession();
        sessionIdRef.current = session.sessionId;
      }
      const response = await askQuestion(sessionIdRef.current, submittedQuestion);
      setMessages((previous) => [
        ...previous,
        { role: "user", content: submittedQuestion, citedSymbolIds: [], citedFilePaths: [] },
        {
          role: "assistant",
          content: response.answer,
          citedSymbolIds: response.citedSymbolIds,
          citedFilePaths: response.citedFilePaths,
        },
      ]);
      setQuestion("");
    } catch (error) {
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

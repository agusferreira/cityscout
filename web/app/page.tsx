"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

// ── Pre-built test questions ──

const TEST_QUESTIONS = [
  {
    category: "Overview",
    questions: [
      "What are the main topics discussed across my emails?",
      "Summarize the most important conversations in my inbox",
      "What types of emails are in this collection?",
    ],
  },
  {
    category: "Search",
    questions: [
      "Are there any action items or tasks I need to follow up on?",
      "What meetings or events have been scheduled?",
      "Show me emails related to contracts or agreements",
    ],
  },
  {
    category: "People & Context",
    questions: [
      "Who are the most frequent senders?",
      "What is the date range of these emails?",
      "What companies or organizations appear most often?",
    ],
  },
];

// ── Types ──

interface Source {
  score: number;
  text: string;
  subject: string;
  from: string;
  date: string;
}

interface QueryResult {
  question: string;
  answer: string;
  sources: Source[];
}

interface IngestStatus {
  running: boolean;
  phase: string;
  total: number;
  processed: number;
  error: string | null;
}

// ── Components ──

function LoadingDots() {
  return (
    <span className="inline-flex gap-1">
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
    </span>
  );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const dateStr = source.date
    ? new Date(source.date).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "Unknown date";

  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start justify-between gap-2 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="shrink-0 rounded bg-accent/20 px-1.5 py-0.5 font-mono text-xs text-accent">
              #{index + 1}
            </span>
            <span className="truncate text-sm font-medium">
              {source.subject}
            </span>
          </div>
          <div className="mt-1 flex gap-3 text-xs text-muted">
            <span>{source.from}</span>
            <span>{dateStr}</span>
            <span className="text-accent">
              {(source.score * 100).toFixed(1)}% match
            </span>
          </div>
        </div>
        <span className="mt-0.5 shrink-0 text-muted transition-transform duration-200">
          {expanded ? "▲" : "▼"}
        </span>
      </button>
      {expanded && (
        <p className="mt-2 whitespace-pre-wrap border-t border-border pt-2 text-sm leading-relaxed text-muted">
          {source.text}
        </p>
      )}
    </div>
  );
}

function IngestPanel({
  status,
  onIngest,
}: {
  status: IngestStatus;
  onIngest: () => void;
}) {
  const pct =
    status.total > 0
      ? Math.round((status.processed / status.total) * 100)
      : 0;

  const phaseLabel: Record<string, string> = {
    idle: "Not started",
    parsing: "Parsing mbox emails...",
    embedding: `Embedding & uploading to Pinecone (${pct}%)`,
    done: `Complete — ${status.total} chunks indexed`,
    error: `Error: ${status.error}`,
  };

  const phaseColor: Record<string, string> = {
    idle: "text-muted",
    parsing: "text-warning",
    embedding: "text-accent",
    done: "text-success",
    error: "text-error",
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-wide uppercase text-muted">
          Data Pipeline
        </h3>
        <button
          onClick={onIngest}
          disabled={status.running}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status.running ? "Running..." : "Run Ingestion"}
        </button>
      </div>

      <p className={`text-sm ${phaseColor[status.phase] || "text-muted"}`}>
        {phaseLabel[status.phase] || status.phase}
      </p>

      {status.running && status.phase === "embedding" && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full bg-accent transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

// ── Main Page ──

export default function Home() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<QueryResult[]>([]);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus>({
    running: false,
    phase: "idle",
    total: 0,
    processed: 0,
    error: null,
  });

  const answerEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll ingestion status while running
  const pollIngestion = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/api/ingest/status`);
        const data: IngestStatus = await res.json();
        setIngestStatus(data);
        if (!data.running) {
          clearInterval(pollRef.current!);
          pollRef.current = null;
        }
      } catch {
        /* server may be down */
      }
    }, 2000);
  }, []);

  // Check ingestion status on mount
  useEffect(() => {
    fetch(`${API_URL}/api/ingest/status`)
      .then((r) => r.json())
      .then((data: IngestStatus) => {
        setIngestStatus(data);
        if (data.running) pollIngestion();
      })
      .catch(() => {});
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [pollIngestion]);

  const startIngestion = async () => {
    try {
      const res = await fetch(`${API_URL}/api/ingest`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setIngestStatus(data.state);
        pollIngestion();
      } else {
        setIngestStatus((prev) => ({
          ...prev,
          phase: "error",
          error: data.error,
        }));
      }
    } catch (err) {
      setIngestStatus((prev) => ({
        ...prev,
        phase: "error",
        error: err instanceof Error ? err.message : "Connection failed",
      }));
    }
  };

  const askQuestion = async (q: string) => {
    if (!q.trim() || loading) return;

    setLoading(true);
    const currentQuestion = q.trim();
    setQuestion("");

    try {
      const res = await fetch(`${API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: currentQuestion, topK: 5 }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Query failed");
      }

      const data = await res.json();
      setResults((prev) => [
        { question: currentQuestion, answer: data.answer, sources: data.sources },
        ...prev,
      ]);
    } catch (err) {
      setResults((prev) => [
        {
          question: currentQuestion,
          answer: `Error: ${err instanceof Error ? err.message : "Something went wrong"}`,
          sources: [],
        },
        ...prev,
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    askQuestion(question);
  };

  // Auto-scroll when new results come in
  useEffect(() => {
    answerEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [results]);

  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      {/* ── Sidebar: Test Suite + Ingestion ── */}
      <aside className="w-full shrink-0 border-b border-border bg-card/50 p-4 lg:w-80 lg:border-b-0 lg:border-r lg:p-6">
        <div className="mb-6">
          <h1 className="text-xl font-bold tracking-tight">
            <span className="text-accent">Email</span> RAG
          </h1>
          <p className="mt-1 text-sm text-muted">
            Semantic search & analysis over your emails
          </p>
        </div>

        <IngestPanel status={ingestStatus} onIngest={startIngestion} />

        <div className="mt-6">
          <h2 className="mb-3 text-sm font-semibold tracking-wide uppercase text-muted">
            Test Suite
          </h2>
          <div className="space-y-4">
            {TEST_QUESTIONS.map((group) => (
              <div key={group.category}>
                <p className="mb-1.5 text-xs font-medium text-accent/70">
                  {group.category}
                </p>
                <div className="space-y-1.5">
                  {group.questions.map((q) => (
                    <button
                      key={q}
                      onClick={() => askQuestion(q)}
                      disabled={loading}
                      className="w-full rounded-lg border border-border bg-card px-3 py-2 text-left text-sm text-foreground transition-colors hover:border-accent/50 hover:bg-card-hover disabled:opacity-50"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ── Main content: Query + Results ── */}
      <main className="flex flex-1 flex-col">
        {/* Query input bar */}
        <div className="sticky top-0 z-10 border-b border-border bg-background/80 p-4 backdrop-blur-md">
          <form onSubmit={handleSubmit} className="mx-auto flex max-w-3xl gap-2">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask anything about your emails..."
              className="flex-1 rounded-xl border border-border bg-card px-4 py-3 text-sm text-foreground placeholder-muted outline-none transition-colors focus:border-accent"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="rounded-xl bg-accent px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? <LoadingDots /> : "Ask"}
            </button>
          </form>
        </div>

        {/* Results feed */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="mx-auto max-w-3xl space-y-6">
            <div ref={answerEndRef} />

            {loading && (
              <div className="rounded-xl border border-border bg-card p-6">
                <p className="text-sm text-muted">
                  Searching emails and generating answer <LoadingDots />
                </p>
              </div>
            )}

            {results.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <div className="mb-4 text-5xl">📬</div>
                <h2 className="text-lg font-semibold">No queries yet</h2>
                <p className="mt-1 max-w-md text-sm text-muted">
                  Type a question above or click a test question from the
                  sidebar to get started. Make sure to run the ingestion
                  pipeline first.
                </p>
              </div>
            )}

            {results.map((result, idx) => (
              <div
                key={`${result.question}-${idx}`}
                className="rounded-xl border border-border bg-card"
              >
                {/* Question */}
                <div className="border-b border-border px-5 py-3">
                  <p className="text-sm font-medium text-accent">
                    {result.question}
                  </p>
                </div>

                {/* Answer */}
                <div className="px-5 py-4">
                  <div
                    className="prose-answer text-sm text-foreground/90"
                    dangerouslySetInnerHTML={{
                      __html: formatMarkdown(result.answer),
                    }}
                  />
                </div>

                {/* Sources */}
                {result.sources.length > 0 && (
                  <div className="border-t border-border px-5 py-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                      Sources ({result.sources.length})
                    </p>
                    <div className="space-y-2">
                      {result.sources.map((source, si) => (
                        <SourceCard
                          key={`${source.subject}-${si}`}
                          source={source}
                          index={si}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

/**
 * Lightweight markdown → HTML for LLM responses.
 * Handles: bold, italic, inline code, headers, lists, blockquotes, paragraphs.
 */
function formatMarkdown(md: string): string {
  return md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/^(\d+)\. (.+)$/gm, "<li>$2</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (m) =>
      `<ul>${m}</ul>`
    )
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br/>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
}

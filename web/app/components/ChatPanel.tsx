"use client";

import { useState, useRef, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  venues?: Venue[];
}

interface Venue {
  name: string;
  neighborhood: string;
  lat: number;
  lng: number;
  category: string;
}

interface ChatPanelProps {
  city: string;
  profile: string;
  userId: string | null;
  onNewVenues?: (venues: Venue[]) => void;
  initialGuide?: string;
}

function formatMarkdown(md: string): string {
  return md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold text-accent mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-semibold text-accent mt-4 mb-1">$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^- (.+)$/gm, '<li class="ml-4 text-sm">• $1</li>')
    .replace(/\n{2,}/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
}

const SUGGESTED_QUESTIONS = [
  "What about brunch spots?",
  "Best coffee near the center?",
  "What should I do tonight?",
  "Any hidden gems off the tourist trail?",
  "I have 3 hours free tomorrow morning",
  "Where should I eat on a budget?",
];

export default function ChatPanel({
  city,
  profile,
  userId,
  onNewVenues,
  initialGuide,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (initialGuide) {
      return [{ role: "assistant", content: initialGuide }];
    }
    return [];
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async (text?: string) => {
    const message = text || input.trim();
    if (!message || loading) return;

    setInput("");
    const userMessage: ChatMessage = { role: "user", content: message };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      // Build history for API (exclude initial guide from history)
      const history = messages
        .filter((_, i) => !(i === 0 && initialGuide))
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          city,
          profile,
          user_id: userId || undefined,
          history,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Chat failed");
      }

      const data = await res.json();
      const assistantMessage: ChatMessage = {
        role: "assistant",
        content: data.response,
        venues: data.venues,
      };
      setMessages((prev) => [...prev, assistantMessage]);

      // Send new venues to parent for map update
      if (data.venues?.length > 0 && onNewVenues) {
        onNewVenues(data.venues);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Sorry, I ran into an error: ${err instanceof Error ? err.message : "unknown error"}. Try again?`,
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const cityName = city.replace("-", " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">💬</span>
          <div>
            <h3 className="text-sm font-semibold">Chat with CityScout</h3>
            <p className="text-xs text-muted">Ask me anything about {cityName}</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="mb-4 text-4xl">🧭</div>
            <h3 className="mb-2 text-lg font-semibold">
              Your {cityName} guide is ready!
            </h3>
            <p className="mb-6 max-w-sm text-sm text-muted">
              Check out the pins on the map, or ask me anything — brunch spots,
              nightlife, hidden gems, or specific neighborhoods.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTED_QUESTIONS.slice(0, 4).map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted transition-colors hover:border-accent hover:text-foreground"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-4">
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-accent text-white"
                    : "border border-border bg-card"
                }`}
              >
                {msg.role === "assistant" ? (
                  <div
                    className="prose-chat text-sm leading-relaxed"
                    dangerouslySetInnerHTML={{
                      __html: formatMarkdown(msg.content),
                    }}
                  />
                ) : (
                  <p className="text-sm">{msg.content}</p>
                )}

                {/* Venue badges in assistant messages */}
                {msg.venues && msg.venues.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1 border-t border-border/50 pt-2">
                    {msg.venues.slice(0, 5).map((v, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent"
                      >
                        📍 {v.name}
                      </span>
                    ))}
                    {msg.venues.length > 5 && (
                      <span className="text-[10px] text-muted">
                        +{msg.venues.length - 5} more
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="rounded-2xl border border-border bg-card px-4 py-3">
                <div className="flex items-center gap-2 text-sm text-muted">
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent delay-75" />
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent delay-150" />
                  <span className="ml-1">Searching local knowledge...</span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested questions (show after first exchange) */}
      {messages.length > 0 && messages.length <= 4 && !loading && (
        <div className="border-t border-border/50 px-4 py-2">
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {SUGGESTED_QUESTIONS.filter(
              (q) => !messages.some((m) => m.content === q)
            )
              .slice(0, 3)
              .map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="shrink-0 rounded-full border border-border bg-card px-3 py-1 text-xs text-muted transition-colors hover:border-accent hover:text-foreground"
                >
                  {q}
                </button>
              ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-border bg-card p-3">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Ask about ${cityName}...`}
            disabled={loading}
            className="flex-1 rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted focus:border-accent focus:outline-none disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || loading}
            className="rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

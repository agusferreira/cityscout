"use client";

import { useState, useRef, useEffect } from "react";
import type { MapPin } from "./CityMap";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatPanelProps {
  city: string;
  profile: string;
  userId: string;
  initialGuide: string;
  onNewPins: (pins: MapPin[]) => void;
}

function formatMarkdown(md: string): string {
  return md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h4 class="chat-h4">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="chat-h3">$1</h3>')
    .replace(/^# (.+)$/gm, '<h3 class="chat-h3">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`)
    .replace(/\n{2,}/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
}

export default function ChatPanel({
  city,
  profile,
  userId,
  initialGuide,
  onNewPins,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: initialGuide },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    setInput("");
    const userMsg: ChatMessage = { role: "user", content: msg };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      // Build history (skip initial guide to keep context smaller)
      const history = messages.slice(1).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: msg,
          city,
          profile,
          user_id: userId || undefined,
          history: [...history, { role: "user", content: msg }],
        }),
      });

      if (!res.ok) throw new Error("Chat request failed");

      const data = await res.json();
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.message,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Add new pins from recommendations
      if (data.recommendations && data.recommendations.length > 0) {
        const newPins: MapPin[] = data.recommendations
          .filter((r: any) => r.lat && r.lng)
          .map((r: any) => ({
            name: r.name,
            lat: r.lat,
            lng: r.lng,
            category: r.category,
            why: r.why || "",
          }));
        if (newPins.length > 0) {
          onNewPins(newPins);
        }
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Sorry, I had trouble processing that. Could you try again?",
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const suggestions = [
    "What about brunch spots?",
    "Best area for nightlife?",
    "I have 3 hours free tomorrow morning",
    "Any hidden gems nearby?",
  ];

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <div className="shrink-0 border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold">
          🧭 CityScout{" "}
          <span className="text-muted">·</span>{" "}
          <span className="gradient-text">
            {city.replace("-", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          </span>
        </h3>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="space-y-4">
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-accent text-white rounded-br-sm"
                    : "bg-card border border-border text-foreground rounded-bl-sm"
                }`}
              >
                {msg.role === "assistant" ? (
                  <div
                    className="chat-message"
                    dangerouslySetInnerHTML={{
                      __html: formatMarkdown(msg.content),
                    }}
                  />
                ) : (
                  <p>{msg.content}</p>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-sm border border-border bg-card px-4 py-3">
                <div className="flex gap-1.5">
                  <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
                  <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
                  <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Quick Suggestions (show only when few messages) */}
      {messages.length <= 2 && !loading && (
        <div className="shrink-0 border-t border-border px-4 py-2">
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => {
                  // Directly send the suggestion as a message
                  const userMsg: ChatMessage = { role: "user", content: s };
                  setMessages((prev) => [...prev, userMsg]);
                  setLoading(true);
                  (async () => {
                    try {
                      const history = messages.slice(1).map((m) => ({
                        role: m.role,
                        content: m.content,
                      }));
                      const res = await fetch(`${API_URL}/api/chat`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          message: s,
                          city,
                          profile,
                          user_id: userId || undefined,
                          history: [...history, { role: "user", content: s }],
                        }),
                      });
                      if (!res.ok) throw new Error("Failed");
                      const data = await res.json();
                      setMessages((prev) => [
                        ...prev,
                        { role: "assistant", content: data.message },
                      ]);
                      if (data.recommendations?.length > 0) {
                        onNewPins(
                          data.recommendations
                            .filter((r: any) => r.lat && r.lng)
                            .map((r: any) => ({
                              name: r.name,
                              lat: r.lat,
                              lng: r.lng,
                              category: r.category,
                              why: r.why || "",
                            }))
                        );
                      }
                    } catch {
                      setMessages((prev) => [
                        ...prev,
                        {
                          role: "assistant",
                          content: "Sorry, something went wrong. Try again?",
                        },
                      ]);
                    } finally {
                      setLoading(false);
                    }
                  })();
                }}
                className="rounded-full border border-border bg-card px-3 py-1 text-xs text-muted transition-colors hover:border-accent hover:text-accent"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 border-t border-border p-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
          }}
          className="flex gap-2"
        >
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask me anything about the city..."
            disabled={loading}
            className="flex-1 rounded-xl border border-border bg-card px-4 py-2.5 text-sm text-foreground placeholder-muted outline-none transition-colors focus:border-accent disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-accent-hover disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}

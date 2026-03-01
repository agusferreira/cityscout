"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import GuideSection from "../components/GuideSection";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

// ── Types ──

interface Source {
  score: number;
  text: string;
  category: string;
  source_url: string;
  source_type: string;
  city: string;
  date: string;
}

interface Scores {
  faithfulness: number | null;
  context_precision: number | null;
  relevancy: number | null;
  error?: string;
}

interface GuideData {
  guide: string;
  sources: Source[];
  scores: Scores;
  city: string;
}

// ── Loading Animation ──

function LoadingDots() {
  return (
    <span className="inline-flex gap-1">
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
    </span>
  );
}

// ── Loading States ──

const LOADING_MESSAGES = [
  { text: "Searching local knowledge base...", emoji: "🔍" },
  { text: "Finding places that match your vibe...", emoji: "🎯" },
  { text: "Cross-referencing Reddit posts and blogs...", emoji: "📚" },
  { text: "Crafting your personalized guide...", emoji: "✍️" },
  { text: "Running quality evaluation...", emoji: "📊" },
];

function GuidePageContent() {
  const searchParams = useSearchParams();
  const city = searchParams.get("city") || "";
  const profile = searchParams.get("profile") || "";

  const [loading, setLoading] = useState(true);
  const [loadingStep, setLoadingStep] = useState(0);
  const [guideData, setGuideData] = useState<GuideData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!city || !profile) {
      setError("Missing city or profile. Please start from the quiz.");
      setLoading(false);
      return;
    }

    // Animate loading messages
    const msgInterval = setInterval(() => {
      setLoadingStep((prev) =>
        prev < LOADING_MESSAGES.length - 1 ? prev + 1 : prev
      );
    }, 3000);

    // Fetch guide
    const fetchGuide = async () => {
      try {
        const res = await fetch(`${API_URL}/api/guide`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            profile,
            city,
            top_k: 8,
          }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Failed to generate guide");
        }

        const data = await res.json();
        setGuideData(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Something went wrong"
        );
      } finally {
        setLoading(false);
        clearInterval(msgInterval);
      }
    };

    fetchGuide();

    return () => clearInterval(msgInterval);
  }, [city, profile]);

  // Loading state
  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="mb-8 text-center">
          <div className="mb-6 text-6xl">
            {LOADING_MESSAGES[loadingStep].emoji}
          </div>
          <h2 className="mb-3 text-2xl font-bold">
            Building your{" "}
            <span className="gradient-text">
              {city.replace("-", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </span>{" "}
            guide
          </h2>
          <p className="text-muted">
            {LOADING_MESSAGES[loadingStep].text} <LoadingDots />
          </p>
        </div>

        {/* Loading progress */}
        <div className="w-full max-w-sm">
          <div className="space-y-2">
            {LOADING_MESSAGES.map((msg, i) => (
              <div
                key={i}
                className={`flex items-center gap-3 rounded-lg px-4 py-2 text-sm transition-all duration-300 ${
                  i < loadingStep
                    ? "text-success"
                    : i === loadingStep
                      ? "text-accent"
                      : "text-muted/40"
                }`}
              >
                <span>
                  {i < loadingStep
                    ? "✓"
                    : i === loadingStep
                      ? msg.emoji
                      : "○"}
                </span>
                <span>{msg.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="text-center">
          <div className="mb-4 text-5xl">😵</div>
          <h2 className="mb-2 text-2xl font-bold">Something went wrong</h2>
          <p className="mb-6 text-muted">{error}</p>
          <a
            href="/"
            className="rounded-xl bg-accent px-6 py-3 font-semibold text-white transition-all hover:bg-accent-hover"
          >
            Start Over
          </a>
        </div>
      </div>
    );
  }

  // Guide display
  if (!guideData) return null;

  return (
    <div className="min-h-screen py-12">
      {/* Back button */}
      <div className="mx-auto mb-8 max-w-3xl px-4">
        <a
          href="/"
          className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground"
        >
          ← Back to quiz
        </a>
      </div>

      <GuideSection
        guide={guideData.guide}
        sources={guideData.sources}
        scores={guideData.scores}
        city={guideData.city}
      />

      {/* Footer */}
      <div className="mx-auto mt-12 max-w-3xl border-t border-border px-4 pt-8 text-center">
        <p className="text-sm text-muted">
          Generated by CityScout RAG • Sources retrieved from Pinecone •
          Quality evaluated with RAGAS
        </p>
        <a
          href="/"
          className="mt-4 inline-block rounded-xl border border-border px-6 py-2 text-sm text-muted transition-colors hover:border-accent hover:text-foreground"
        >
          Generate Another Guide
        </a>
      </div>
    </div>
  );
}

export default function GuidePage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center">
        <LoadingDots />
      </div>
    }>
      <GuidePageContent />
    </Suspense>
  );
}

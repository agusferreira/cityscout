"use client";

import { useState, useEffect, Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import ChatPanel from "../components/ChatPanel";

// Dynamic import for MapView (Leaflet needs window)
const MapView = dynamic(() => import("../components/MapView"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center bg-card">
      <div className="text-muted">Loading map...</div>
    </div>
  ),
});

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

// ── Types ──

interface Venue {
  name: string;
  neighborhood: string;
  lat: number;
  lng: number;
  category: string;
  source_url?: string;
  source_type?: string;
}

interface GuideData {
  guide: string;
  venues: Venue[];
  map_center: { lat: number; lng: number; zoom?: number };
  enhanced: boolean;
  scores: {
    faithfulness: number | null;
    context_precision: number | null;
    relevancy: number | null;
    error?: string;
  };
}

// ── Loading ──

function LoadingDots() {
  return (
    <span className="inline-flex gap-1">
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
    </span>
  );
}

const LOADING_STEPS = [
  { text: "Searching local knowledge base...", emoji: "🔍" },
  { text: "Matching your taste profile...", emoji: "🎯" },
  { text: "Mapping venue coordinates...", emoji: "📍" },
  { text: "Crafting personalized recommendations...", emoji: "✍️" },
  { text: "Running quality evaluation...", emoji: "📊" },
];

// ── Source badges ──

const SOURCE_EMOJI: Record<string, string> = {
  spotify: "🎵",
  youtube: "📺",
  google_maps: "📍",
  instagram: "📸",
};

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  if (value === null || value === undefined) return null;
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "bg-success" : value >= 0.5 ? "bg-warning" : "bg-error";
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 text-xs text-muted">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-border">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right font-mono text-xs">{pct}%</span>
    </div>
  );
}

function GuidePageContent() {
  const searchParams = useSearchParams();
  const city = searchParams.get("city") || "";
  const profile = searchParams.get("profile") || "";
  const userId = searchParams.get("user_id") || "";

  const [loading, setLoading] = useState(true);
  const [loadingStep, setLoadingStep] = useState(0);
  const [guideData, setGuideData] = useState<GuideData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chatVenues, setChatVenues] = useState<Venue[]>([]);
  const [showScores, setShowScores] = useState(false);

  // Combine guide venues + chat-discovered venues
  const allVenues = useMemo(() => {
    const base = guideData?.venues || [];
    // Deduplicate by name
    const seen = new Set(base.map((v) => v.name));
    const extra = chatVenues.filter((v) => !seen.has(v.name));
    return [...base, ...extra];
  }, [guideData?.venues, chatVenues]);

  useEffect(() => {
    if (!city || !profile) {
      setError("Missing city or profile. Please start from the beginning.");
      setLoading(false);
      return;
    }

    // Animate loading steps
    const msgInterval = setInterval(() => {
      setLoadingStep((prev) => (prev < LOADING_STEPS.length - 1 ? prev + 1 : prev));
    }, 2500);

    const fetchGuide = async () => {
      try {
        const res = await fetch(`${API_URL}/api/guide`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            profile,
            city,
            top_k: 8,
            user_id: userId || undefined,
          }),
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Failed to generate guide");
        }

        const data = await res.json();
        setGuideData(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong");
      } finally {
        setLoading(false);
        clearInterval(msgInterval);
      }
    };

    fetchGuide();
    return () => clearInterval(msgInterval);
  }, [city, profile, userId]);

  const cityName = city
    .replace("-", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  // ── Loading state ──
  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="mb-8 text-center">
          <div className="mb-4 text-6xl">{LOADING_STEPS[loadingStep].emoji}</div>
          <h2 className="mb-3 text-2xl font-bold">
            Building your{" "}
            <span className="gradient-text">{cityName}</span> guide
          </h2>
          <p className="text-muted">
            {LOADING_STEPS[loadingStep].text} <LoadingDots />
          </p>
        </div>
        <div className="w-full max-w-sm">
          <div className="space-y-2">
            {LOADING_STEPS.map((step, i) => (
              <div
                key={i}
                className={`flex items-center gap-3 rounded-lg px-4 py-2 text-sm transition-all ${
                  i < loadingStep
                    ? "text-success"
                    : i === loadingStep
                      ? "text-accent"
                      : "text-muted/40"
                }`}
              >
                <span>{i < loadingStep ? "✓" : i === loadingStep ? step.emoji : "○"}</span>
                <span>{step.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ── Error state ──
  if (error) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="text-center">
          <div className="mb-4 text-5xl">😵</div>
          <h2 className="mb-2 text-2xl font-bold">Something went wrong</h2>
          <p className="mb-6 text-muted">{error}</p>
          <a
            href="/"
            className="rounded-xl bg-accent px-6 py-3 font-semibold text-white hover:bg-accent-hover"
          >
            Start Over
          </a>
        </div>
      </div>
    );
  }

  if (!guideData) return null;

  // ── Split View: Map + Chat ──
  return (
    <div className="flex h-screen flex-col">
      {/* Top bar */}
      <div className="flex items-center justify-between border-b border-border bg-card px-4 py-3">
        <div className="flex items-center gap-3">
          <a href="/" className="text-muted hover:text-foreground" title="Back">
            ← 
          </a>
          <div className="flex items-center gap-2">
            <span className="text-xl">🧭</span>
            <h1 className="text-lg font-bold">
              <span className="gradient-text">{cityName}</span>
            </h1>
          </div>
          {guideData.enhanced && (
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent">
              ✨ Enhanced
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Venue count */}
          <span className="text-xs text-muted">
            📍 {allVenues.length} places
          </span>

          {/* RAGAS scores toggle */}
          {!guideData.scores.error && (
            <button
              onClick={() => setShowScores(!showScores)}
              className="rounded-lg border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-accent hover:text-foreground"
            >
              📊 Quality
            </button>
          )}
        </div>
      </div>

      {/* RAGAS scores panel (collapsible) */}
      {showScores && !guideData.scores.error && (
        <div className="border-b border-border bg-card px-4 py-3">
          <div className="mx-auto flex max-w-lg flex-col gap-2">
            <ScoreBar label="Faithfulness" value={guideData.scores.faithfulness} />
            <ScoreBar label="Precision" value={guideData.scores.context_precision} />
            <ScoreBar label="Relevancy" value={guideData.scores.relevancy} />
            <p className="text-[10px] text-muted">
              RAGAS evaluation — how well recommendations are grounded in source data
            </p>
          </div>
        </div>
      )}

      {/* Split view */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Map */}
        <div className="hidden w-1/2 border-r border-border md:block">
          <MapView
            center={guideData.map_center}
            venues={allVenues}
          />
        </div>

        {/* Right: Chat */}
        <div className="flex w-full flex-col md:w-1/2">
          <ChatPanel
            city={city}
            profile={profile}
            userId={userId || null}
            initialGuide={guideData.guide}
            onNewVenues={(venues) => {
              setChatVenues((prev) => {
                const newVenues = venues.filter(
                  (v) => !prev.some((p) => p.name === v.name)
                );
                return [...prev, ...newVenues];
              });
            }}
          />
        </div>
      </div>

      {/* Mobile: Map toggle (shown on small screens) */}
      <MobileMapToggle
        center={guideData.map_center}
        venues={allVenues}
      />
    </div>
  );
}

// Mobile map as a bottom sheet toggle
function MobileMapToggle({
  center,
  venues,
}: {
  center: { lat: number; lng: number; zoom?: number };
  venues: Venue[];
}) {
  const [showMap, setShowMap] = useState(false);

  return (
    <>
      {/* Mobile map toggle button */}
      <button
        onClick={() => setShowMap(!showMap)}
        className="fixed bottom-4 left-4 z-50 rounded-full bg-accent px-4 py-2.5 text-sm font-medium text-white shadow-lg md:hidden"
      >
        {showMap ? "💬 Chat" : `📍 Map (${venues.length})`}
      </button>

      {/* Mobile map overlay */}
      {showMap && (
        <div className="fixed inset-0 z-40 md:hidden">
          <MapView center={center} venues={venues} />
          <button
            onClick={() => setShowMap(false)}
            className="absolute right-4 top-4 rounded-full bg-card px-3 py-1.5 text-sm font-medium text-foreground shadow-lg"
          >
            ✕ Close
          </button>
        </div>
      )}
    </>
  );
}

export default function GuidePage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <LoadingDots />
        </div>
      }
    >
      <GuidePageContent />
    </Suspense>
  );
}

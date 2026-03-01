"use client";

import { useState, useEffect, Suspense, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import ChatPanel from "../components/ChatPanel";
import type { MapPin } from "../components/CityMap";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

// Dynamic import for Leaflet (SSR incompatible)
const CityMap = dynamic(() => import("../components/CityMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center bg-[#1a1a2e]">
      <div className="text-center">
        <div className="mb-3 text-4xl">🗺️</div>
        <p className="text-sm text-muted">Loading map...</p>
      </div>
    </div>
  ),
});

// ── Types ──

interface Venue {
  name: string;
  lat: number;
  lng: number;
  category: string;
  why?: string;
  source_url?: string;
  source_type?: string;
}

interface GuideResponse {
  guide: string;
  sources: any[];
  venues: Venue[];
  map_center: { lat: number; lng: number; zoom: number };
  city: string;
  enhanced: boolean;
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

const LOADING_MESSAGES = [
  { text: "Searching local knowledge base...", emoji: "🔍" },
  { text: "Finding places that match your vibe...", emoji: "🎯" },
  { text: "Cross-referencing sources...", emoji: "📚" },
  { text: "Mapping your personalized spots...", emoji: "📍" },
  { text: "Crafting your guide...", emoji: "✍️" },
];

// ── Legend Component ──

const CATEGORY_LEGEND = [
  { key: "coffee", emoji: "☕", label: "Coffee", color: "#8B4513" },
  { key: "food", emoji: "🍽️", label: "Food", color: "#DC143C" },
  { key: "nightlife", emoji: "🌙", label: "Nightlife", color: "#9B59B6" },
  { key: "culture", emoji: "🎨", label: "Culture", color: "#3498DB" },
  { key: "fitness", emoji: "🏃", label: "Fitness", color: "#27AE60" },
  { key: "neighborhoods", emoji: "🏘️", label: "Areas", color: "#F39C12" },
];

function MapLegend() {
  return (
    <div className="absolute bottom-4 left-4 z-[1000] rounded-xl border border-border bg-background/90 p-3 backdrop-blur-sm">
      <div className="flex flex-wrap gap-2.5">
        {CATEGORY_LEGEND.map((cat) => (
          <div key={cat.key} className="flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: cat.color }}
            />
            <span className="text-[10px] text-muted">{cat.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Content ──

function ResultsContent() {
  const searchParams = useSearchParams();
  const city = searchParams.get("city") || "";
  const profile = searchParams.get("profile") || "";
  const userId = searchParams.get("user_id") || "";

  const [loading, setLoading] = useState(true);
  const [loadingStep, setLoadingStep] = useState(0);
  const [guideData, setGuideData] = useState<GuideResponse | null>(null);
  const [pins, setPins] = useState<MapPin[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!city || !profile) {
      setError("Missing city or profile. Please start over.");
      setLoading(false);
      return;
    }

    const msgInterval = setInterval(() => {
      setLoadingStep((prev) =>
        prev < LOADING_MESSAGES.length - 1 ? prev + 1 : prev
      );
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

        const data: GuideResponse = await res.json();
        setGuideData(data);

        // Convert venues to map pins
        const initialPins: MapPin[] = (data.venues || [])
          .filter((v) => v.lat && v.lng)
          .map((v) => ({
            name: v.name,
            lat: v.lat,
            lng: v.lng,
            category: v.category,
            why: v.why || "",
            source_url: v.source_url,
          }));
        setPins(initialPins);
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
  }, [city, profile, userId]);

  const handleNewPins = useCallback((newPins: MapPin[]) => {
    setPins((prev) => {
      const existingNames = new Set(prev.map((p) => p.name));
      const unique = newPins.filter((p) => !existingNames.has(p.name));
      return [...prev, ...unique];
    });
  }, []);

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
              {city
                .replace("-", " ")
                .replace(/\b\w/g, (c) => c.toUpperCase())}
            </span>{" "}
            guide
          </h2>
          <p className="text-muted">
            {LOADING_MESSAGES[loadingStep].text} <LoadingDots />
          </p>
        </div>
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

  if (!guideData) return null;

  // Split view: Map + Chat
  return (
    <div className="flex h-screen w-full">
      {/* Left: Map (60%) */}
      <div className="relative h-full w-[60%] border-r border-border">
        <CityMap center={guideData.map_center} pins={pins} />
        <MapLegend />

        {/* Pin count badge */}
        <div className="absolute right-4 top-4 z-[1000] rounded-lg border border-border bg-background/90 px-3 py-1.5 text-xs backdrop-blur-sm">
          <span className="font-semibold text-accent">{pins.length}</span>{" "}
          <span className="text-muted">spots mapped</span>
        </div>

        {/* Back button */}
        <a
          href="/"
          className="absolute left-4 top-4 z-[1000] rounded-lg border border-border bg-background/90 px-3 py-1.5 text-xs text-muted backdrop-blur-sm transition-colors hover:text-foreground"
        >
          ← Back
        </a>
      </div>

      {/* Right: Chat (40%) */}
      <div className="h-full w-[40%]">
        <ChatPanel
          city={city}
          profile={profile}
          userId={userId}
          initialGuide={guideData.guide}
          onNewPins={handleNewPins}
        />
      </div>
    </div>
  );
}

export default function ResultsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <LoadingDots />
        </div>
      }
    >
      <ResultsContent />
    </Suspense>
  );
}

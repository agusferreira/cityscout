"use client";

import { useState, useEffect, useCallback } from "react";
import DataUpload from "./components/DataUpload";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

// ── Types ──

interface City {
  slug: string;
  name: string;
  chunk_count: number;
  categories: string[];
  center: { lat: number; lng: number; zoom: number };
}

interface IngestStatus {
  running: boolean;
  phase: string;
  total: number;
  processed: number;
  error: string | null;
}

type AppState = "connect" | "destination" | "generating";

const CITY_EMOJI: Record<string, string> = {
  "buenos-aires": "🇦🇷",
  barcelona: "🇪🇸",
  lisbon: "🇵🇹",
};

const CITY_PHOTOS: Record<string, string> = {
  "buenos-aires": "🏙️",
  barcelona: "🏖️",
  lisbon: "🌇",
};

// ── Inline Loading Component ──

function LoadingDots() {
  return (
    <span className="inline-flex gap-1">
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
      <span className="loading-dot inline-block h-2 w-2 rounded-full bg-accent" />
    </span>
  );
}

// ── Ingest Panel ──

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
    idle: "Not indexed yet",
    loading: "Loading city data...",
    indexing: "Creating Pinecone index...",
    embedding: `Embedding & indexing (${pct}%)`,
    done: `✓ ${status.total} chunks indexed`,
    error: `Error: ${status.error}`,
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Data Pipeline
        </h3>
        <button
          onClick={onIngest}
          disabled={status.running}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status.running ? "Running..." : "Index Data"}
        </button>
      </div>
      <p className={`text-sm ${status.phase === "done" ? "text-success" : status.phase === "error" ? "text-error" : "text-muted"}`}>
        {phaseLabel[status.phase] || status.phase}
      </p>
      {status.running && status.phase === "embedding" && (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border">
          <div
            className="progress-active h-full rounded-full bg-accent transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

// ── Main Page ──

export default function Home() {
  const [appState, setAppState] = useState<AppState>("connect");
  const [userId, setUserId] = useState<string>("");
  const [uploadedSources, setUploadedSources] = useState<string[]>([]);
  const [cities, setCities] = useState<City[]>([]);
  const [profile, setProfile] = useState<string>("");
  const [profileLoading, setProfileLoading] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus>({
    running: false,
    phase: "idle",
    total: 0,
    processed: 0,
    error: null,
  });

  useEffect(() => {
    fetch(`${API_URL}/api/cities`)
      .then((r) => r.json())
      .then((data) => setCities(data.cities || []))
      .catch(() => {});

    fetch(`${API_URL}/api/ingest/status`)
      .then((r) => r.json())
      .then((data: IngestStatus) => {
        setIngestStatus(data);
        if (data.running) pollIngestion();
      })
      .catch(() => {});
  }, []);

  const pollIngestion = useCallback(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/api/ingest/status`);
        const data: IngestStatus = await res.json();
        setIngestStatus(data);
        if (!data.running) clearInterval(interval);
      } catch {}
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const startIngestion = async () => {
    try {
      const res = await fetch(`${API_URL}/api/ingest`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setIngestStatus(data.state);
        pollIngestion();
      }
    } catch (err) {
      setIngestStatus((prev) => ({
        ...prev,
        phase: "error",
        error: err instanceof Error ? err.message : "Connection failed",
      }));
    }
  };

  const generateProfile = async () => {
    if (!userId) return;
    setProfileLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/profile/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
      });
      const data = await res.json();
      if (data.profile) {
        setProfile(data.profile);
      }
    } catch {
      // Fallback profile
      setProfile(
        "A curious traveler who loves authentic local experiences and hidden gems."
      );
    } finally {
      setProfileLoading(false);
    }
  };

  const handleContinue = async () => {
    // Generate profile from uploaded data, then go to destination selection
    await generateProfile();
    setAppState("destination");
  };

  const handleCitySelect = (citySlug: string) => {
    setAppState("generating");
    const params = new URLSearchParams({
      city: citySlug,
      profile: profile,
    });
    if (userId) params.set("user_id", userId);
    window.location.href = `/guide?${params.toString()}`;
  };

  // ── Page 1: Connect Your Data ──
  if (appState === "connect") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
        {/* Hero */}
        <div className="mb-10 text-center">
          <div className="mb-4 text-6xl">🧭</div>
          <h1 className="mb-3 text-4xl font-bold tracking-tight md:text-5xl">
            City<span className="gradient-text">Scout</span>
          </h1>
          <p className="mx-auto max-w-lg text-lg text-muted">
            Connect your music, maps, and social data — we&apos;ll build your
            travel personality and create a city guide just for you.
          </p>
        </div>

        {/* Data Upload */}
        <DataUpload
          userId={userId}
          onUserIdChange={(id) => setUserId(id)}
          onUploadComplete={(result) => {
            setUploadedSources((prev) => {
              const next = [...prev];
              if (!next.includes(result.source)) next.push(result.source);
              return next;
            });
          }}
          onAllDemoLoaded={() => {
            // Auto-advance after demo loads
          }}
        />

        {/* Continue button */}
        {uploadedSources.length > 0 && (
          <div className="mt-8 text-center fade-in">
            <button
              onClick={handleContinue}
              disabled={profileLoading}
              className="rounded-2xl bg-accent px-8 py-4 text-lg font-semibold text-white transition-all hover:scale-105 hover:bg-accent-hover disabled:opacity-50"
            >
              {profileLoading ? (
                <span className="inline-flex items-center gap-2">
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  Analyzing your taste...
                </span>
              ) : (
                "Continue — Where are you going? →"
              )}
            </button>
          </div>
        )}

        {/* Tech stack + ingest (subtle) */}
        <div className="mt-12 flex flex-col items-center gap-3 text-sm text-muted">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-accent/50" />
            <span>Powered by RAG + Pinecone + OpenAI</span>
          </div>
        </div>

        <div className="mt-6 w-full max-w-md">
          <IngestPanel status={ingestStatus} onIngest={startIngestion} />
        </div>
      </div>
    );
  }

  // ── Page 2: Where are you going? ──
  if (appState === "destination") {
    return (
      <div className="flex min-h-screen flex-col justify-center py-12">
        <div className="fade-in mx-auto max-w-2xl px-4">
          {/* Profile summary */}
          {profile && (
            <div className="mb-8 rounded-2xl border border-accent/30 bg-accent/5 p-6 text-center">
              <div className="mb-2 flex flex-wrap items-center justify-center gap-2">
                <span className="text-xl">✨</span>
                <span className="text-sm font-semibold text-accent">
                  Your Travel DNA
                </span>
                {uploadedSources.map((src) => (
                  <span
                    key={src}
                    className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] text-accent"
                  >
                    {{ spotify: "🎵", youtube: "📺", google_maps: "📍", instagram: "📸" }[src] || "📊"}{" "}
                    {src.replace("_", " ")}
                  </span>
                ))}
              </div>
              <p className="text-sm leading-relaxed text-foreground/80">
                {profile}
              </p>
            </div>
          )}

          {/* City selection */}
          <div className="mb-8 text-center">
            <h2 className="mb-2 text-3xl font-bold">
              Where are you <span className="gradient-text">headed</span>?
            </h2>
            <p className="text-muted">
              Pick a city and we&apos;ll create your personalized guide with
              an interactive map
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {cities.map((city) => (
              <button
                key={city.slug}
                onClick={() => handleCitySelect(city.slug)}
                disabled={ingestStatus.phase !== "done"}
                className="quiz-option group rounded-xl border border-border p-6 text-center disabled:cursor-not-allowed disabled:opacity-50"
              >
                <div className="mb-3 text-5xl">
                  {CITY_EMOJI[city.slug] || "🌍"}
                </div>
                <div className="mb-1 text-lg font-semibold group-hover:text-accent">
                  {city.name}
                </div>
                <div className="text-sm text-muted">
                  {city.chunk_count} local tips
                </div>
                <div className="mt-2 flex flex-wrap justify-center gap-1">
                  {city.categories.slice(0, 4).map((cat) => (
                    <span
                      key={cat}
                      className={`rounded-full px-2 py-0.5 text-[10px] badge-${cat}`}
                    >
                      {cat}
                    </span>
                  ))}
                </div>
              </button>
            ))}
          </div>

          {ingestStatus.phase !== "done" && (
            <div className="mt-6 text-center">
              <p className="mb-3 text-sm text-warning">
                ⚠️ City data needs to be indexed first
              </p>
              <IngestPanel status={ingestStatus} onIngest={startIngestion} />
            </div>
          )}

          {/* Back button */}
          <div className="mt-8 text-center">
            <button
              onClick={() => setAppState("connect")}
              className="text-sm text-muted hover:text-foreground"
            >
              ← Back to data upload
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Generating (brief transition) ──
  if (appState === "generating") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="text-center">
          <div className="mb-6 text-6xl">🗺️</div>
          <h2 className="mb-3 text-2xl font-bold">
            Building your guide <LoadingDots />
          </h2>
          <p className="text-muted">
            Searching local knowledge and matching with your profile...
          </p>
        </div>
      </div>
    );
  }

  return null;
}

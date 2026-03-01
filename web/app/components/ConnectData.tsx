"use client";

import { useState, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

interface UploadSource {
  id: string;
  label: string;
  emoji: string;
  description: string;
}

const SOURCES: UploadSource[] = [
  {
    id: "spotify",
    label: "Spotify",
    emoji: "🎵",
    description: "Listening history & top artists",
  },
  {
    id: "youtube",
    label: "YouTube",
    emoji: "📺",
    description: "Subscriptions & watch history",
  },
  {
    id: "google_maps",
    label: "Google Maps",
    emoji: "📍",
    description: "Saved & starred places",
  },
  {
    id: "instagram",
    label: "Instagram",
    emoji: "📸",
    description: "Liked posts & saved content",
  },
];

const SAMPLE_FILES: Record<string, string> = {
  spotify: "spotify-history.json",
  youtube: "youtube-subscriptions.json",
  google_maps: "maps-saved-places.json",
  instagram: "instagram-likes.json",
};

interface ConnectDataProps {
  onComplete: (userId: string, sources: string[]) => void;
}

export default function ConnectData({ onComplete }: ConnectDataProps) {
  const [userId, setUserId] = useState("");
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [loadingDemo, setLoadingDemo] = useState(false);

  const uploadedSources = Object.keys(uploaded);
  const totalSignals = Object.values(uploaded).reduce((a, b) => a + b, 0);

  const handleFileUpload = async (source: string, file: File) => {
    setUploading(source);
    setError(null);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const res = await fetch(`${API_URL}/api/profile/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, data, user_id: userId || undefined }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }
      const result = await res.json();
      if (!userId && result.user_id) setUserId(result.user_id);
      setUploaded((prev) => ({ ...prev, [source]: result.chunks_stored }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(null);
    }
  };

  const handleSampleUpload = async (source: string) => {
    setUploading(source);
    setError(null);
    try {
      const sampleFile = SAMPLE_FILES[source];
      const sampleRes = await fetch(`/sample-data/${sampleFile}`);
      if (!sampleRes.ok) throw new Error("Sample file not found");
      const data = await sampleRes.json();
      const res = await fetch(`${API_URL}/api/profile/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, data, user_id: userId || undefined }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }
      const result = await res.json();
      if (!userId && result.user_id) setUserId(result.user_id);
      setUploaded((prev) => ({ ...prev, [source]: result.chunks_stored }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sample");
    } finally {
      setUploading(null);
    }
  };

  const handleTryDemo = async () => {
    setLoadingDemo(true);
    setError(null);
    try {
      let currentUserId = userId;
      for (const source of SOURCES) {
        const sampleFile = SAMPLE_FILES[source.id];
        const sampleRes = await fetch(`/sample-data/${sampleFile}`);
        if (!sampleRes.ok) continue;
        const data = await sampleRes.json();
        const res = await fetch(`${API_URL}/api/profile/upload`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source: source.id,
            data,
            user_id: currentUserId || undefined,
          }),
        });
        if (res.ok) {
          const result = await res.json();
          if (!currentUserId && result.user_id) {
            currentUserId = result.user_id;
            setUserId(result.user_id);
          }
          setUploaded((prev) => ({
            ...prev,
            [source.id]: result.chunks_stored,
          }));
        }
      }
      if (currentUserId) {
        onComplete(
          currentUserId,
          SOURCES.map((s) => s.id)
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo loading failed");
    } finally {
      setLoadingDemo(false);
    }
  };

  const canProceed = uploadedSources.length > 0;

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="mx-auto w-full max-w-2xl">
        {/* Header */}
        <div className="mb-10 text-center">
          <div className="mb-4 text-6xl">🧭</div>
          <h1 className="mb-3 text-4xl font-bold tracking-tight md:text-5xl">
            City<span className="gradient-text">Scout</span>
          </h1>
          <p className="mx-auto max-w-lg text-lg text-muted">
            Discover any city through your unique lens. Connect your data
            for hyper-personalized recommendations powered by AI.
          </p>
        </div>

        {/* Data Source Cards */}
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {SOURCES.map((source) => {
            const isUploaded = source.id in uploaded;
            const isUploading = uploading === source.id;

            return (
              <div
                key={source.id}
                className={`rounded-xl border p-4 transition-all ${
                  isUploaded
                    ? "border-success/50 bg-success/5"
                    : "border-border bg-card hover:border-accent/30"
                }`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-2xl">{source.emoji}</span>
                  <span className="font-semibold">{source.label}</span>
                  {isUploaded && (
                    <span className="ml-auto text-xs text-success">
                      ✓ {uploaded[source.id]} signals
                    </span>
                  )}
                </div>
                <p className="mb-3 text-xs text-muted">{source.description}</p>

                {isUploading ? (
                  <div className="flex items-center gap-2 text-sm text-accent">
                    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                    Processing...
                  </div>
                ) : isUploaded ? (
                  <span className="text-xs text-success/70">Connected</span>
                ) : (
                  <div className="flex gap-2">
                    <label className="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:border-accent hover:text-foreground">
                      Upload JSON
                      <input
                        type="file"
                        accept=".json"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) handleFileUpload(source.id, file);
                        }}
                      />
                    </label>
                    <button
                      onClick={() => handleSampleUpload(source.id)}
                      className="rounded-lg bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20"
                    >
                      Use Sample
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-error/30 bg-error/10 p-3 text-sm text-error">
            {error}
          </div>
        )}

        {/* Summary */}
        {totalSignals > 0 && (
          <div className="mb-6 rounded-xl border border-accent/30 bg-accent/5 p-4 text-center">
            <p className="text-sm">
              <span className="font-semibold text-accent">
                {totalSignals} preference signals
              </span>{" "}
              extracted from{" "}
              <span className="font-semibold">
                {uploadedSources.length} source
                {uploadedSources.length > 1 ? "s" : ""}
              </span>
            </p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col items-center gap-4">
          {canProceed ? (
            <button
              onClick={() => onComplete(userId, uploadedSources)}
              className="rounded-2xl bg-accent px-8 py-4 text-lg font-semibold text-white transition-all hover:scale-105 hover:bg-accent-hover"
            >
              Choose Your City →
            </button>
          ) : (
            <>
              <div className="flex items-center gap-4 text-sm text-muted">
                <div className="h-px flex-1 bg-border" />
                <span>or</span>
                <div className="h-px flex-1 bg-border" />
              </div>
              <button
                onClick={handleTryDemo}
                disabled={loadingDemo}
                className="rounded-2xl bg-accent px-8 py-4 text-lg font-semibold text-white transition-all hover:scale-105 hover:bg-accent-hover disabled:opacity-50"
              >
                {loadingDemo ? (
                  <span className="flex items-center gap-2">
                    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Loading demo data...
                  </span>
                ) : (
                  "🚀 Try Demo — Load Sample Data"
                )}
              </button>
              <p className="text-center text-xs text-muted">
                Connect at least 1 source or try the demo to get started
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

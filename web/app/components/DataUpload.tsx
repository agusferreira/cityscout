"use client";

import { useState, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

interface UploadSource {
  id: string;
  label: string;
  emoji: string;
  description: string;
  accept: string;
  sampleFile?: string;
}

const SOURCES: UploadSource[] = [
  {
    id: "spotify",
    label: "Spotify",
    emoji: "🎵",
    description: "Listening history & top artists (JSON from Spotify privacy export)",
    accept: ".json",
    sampleFile: "spotify-history.json",
  },
  {
    id: "youtube",
    label: "YouTube",
    emoji: "📺",
    description: "Subscriptions & watch history (JSON from Google Takeout)",
    accept: ".json",
    sampleFile: "youtube-subscriptions.json",
  },
  {
    id: "google_maps",
    label: "Google Maps",
    emoji: "📍",
    description: "Saved & starred places (JSON from Google Takeout)",
    accept: ".json",
    sampleFile: "maps-saved-places.json",
  },
  {
    id: "instagram",
    label: "Instagram",
    emoji: "📸",
    description: "Liked posts & saved content (JSON from Instagram data export)",
    accept: ".json",
    sampleFile: "instagram-likes.json",
  },
];

interface UploadResult {
  source: string;
  chunks_stored: number;
  categories: string[];
  signals: { type: string; category: string; preview: string }[];
}

interface DataUploadProps {
  userId: string;
  onUploadComplete: (result: UploadResult) => void;
  onUserIdChange: (userId: string) => void;
}

export default function DataUpload({
  userId,
  onUploadComplete,
  onUserIdChange,
}: DataUploadProps) {
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<Record<string, UploadResult>>({});
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeSource, setActiveSource] = useState<string | null>(null);

  const handleFileUpload = async (source: string, file: File) => {
    setUploading(source);
    setError(null);

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      const res = await fetch(`${API_URL}/api/profile/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source,
          data,
          user_id: userId || undefined,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }

      const result = await res.json();

      // Update userId if this is the first upload
      if (!userId && result.user_id) {
        onUserIdChange(result.user_id);
      }

      setUploaded((prev) => ({ ...prev, [source]: result }));
      onUploadComplete(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to upload"
      );
    } finally {
      setUploading(null);
      setActiveSource(null);
    }
  };

  const handleUseSample = async (source: string) => {
    setUploading(source);
    setError(null);

    try {
      // Fetch sample file from our data directory via API
      const sampleFile = SOURCES.find((s) => s.id === source)?.sampleFile;
      if (!sampleFile) throw new Error("No sample file available");

      // Load sample data directly
      const sampleRes = await fetch(`/sample-data/${sampleFile}`);
      if (!sampleRes.ok) {
        // If direct fetch fails, try via the API
        throw new Error("Sample file not found at /sample-data/");
      }
      const data = await sampleRes.json();

      const res = await fetch(`${API_URL}/api/profile/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source,
          data,
          user_id: userId || undefined,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }

      const result = await res.json();

      if (!userId && result.user_id) {
        onUserIdChange(result.user_id);
      }

      setUploaded((prev) => ({ ...prev, [source]: result }));
      onUploadComplete(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load sample"
      );
    } finally {
      setUploading(null);
    }
  };

  const totalChunks = Object.values(uploaded).reduce(
    (sum, r) => sum + r.chunks_stored,
    0
  );

  return (
    <div className="fade-in mx-auto max-w-2xl px-4">
      <div className="mb-6 text-center">
        <h3 className="mb-2 text-xl font-bold">
          <span className="gradient-text">Enhance</span> Your Profile
        </h3>
        <p className="text-sm text-muted">
          Connect your data for hyper-personalized recommendations.
          Upload real exports or try with sample data.
        </p>
      </div>

      {/* Upload cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {SOURCES.map((source) => {
          const isUploaded = source.id in uploaded;
          const isUploading = uploading === source.id;
          const result = uploaded[source.id];

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
                    ✓ {result.chunks_stored} signals
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
                <div className="space-y-1">
                  {result.signals?.slice(0, 2).map((sig, i) => (
                    <p key={i} className="text-xs text-muted">
                      • {sig.preview.slice(0, 80)}...
                    </p>
                  ))}
                </div>
              ) : (
                <div className="flex gap-2">
                  <label className="cursor-pointer rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:border-accent hover:text-foreground">
                    Upload JSON
                    <input
                      type="file"
                      accept={source.accept}
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleFileUpload(source.id, file);
                      }}
                    />
                  </label>
                  <button
                    onClick={() => handleUseSample(source.id)}
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
        <div className="mt-4 rounded-lg border border-error/30 bg-error/10 p-3 text-sm text-error">
          {error}
        </div>
      )}

      {/* Summary */}
      {totalChunks > 0 && (
        <div className="mt-4 rounded-xl border border-accent/30 bg-accent/5 p-4 text-center">
          <p className="text-sm">
            <span className="font-semibold text-accent">{totalChunks} preference signals</span>
            {" "}extracted from{" "}
            <span className="font-semibold">
              {Object.keys(uploaded).length} source{Object.keys(uploaded).length > 1 ? "s" : ""}
            </span>
          </p>
          <p className="mt-1 text-xs text-muted">
            Your guide will use dual-corpus RAG: city knowledge + your personal data
          </p>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept=".json"
      />
    </div>
  );
}

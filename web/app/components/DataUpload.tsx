"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

interface UploadSource {
  id: string;
  label: string;
  emoji: string;
  description: string;
  accept: string;
  sampleFile: string;
}

const SOURCES: UploadSource[] = [
  {
    id: "spotify",
    label: "Spotify",
    emoji: "🎵",
    description: "Listening history & top artists",
    accept: ".json",
    sampleFile: "spotify-history.json",
  },
  {
    id: "youtube",
    label: "YouTube",
    emoji: "📺",
    description: "Subscriptions & watch history",
    accept: ".json",
    sampleFile: "youtube-subscriptions.json",
  },
  {
    id: "google_maps",
    label: "Google Maps",
    emoji: "📍",
    description: "Saved & starred places",
    accept: ".json",
    sampleFile: "maps-saved-places.json",
  },
  {
    id: "instagram",
    label: "Instagram",
    emoji: "📸",
    description: "Liked & saved posts",
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
  onUserIdChange: (userId: string) => void;
  onUploadComplete: (result: UploadResult) => void;
  onAllDemoLoaded?: () => void;
}

export default function DataUpload({
  userId,
  onUserIdChange,
  onUploadComplete,
  onAllDemoLoaded,
}: DataUploadProps) {
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<Record<string, UploadResult>>({});
  const [error, setError] = useState<string | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);

  const uploadSource = async (
    source: string,
    data: any,
    currentUserId: string
  ): Promise<{ result: UploadResult; user_id: string }> => {
    const res = await fetch(`${API_URL}/api/profile/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source,
        data,
        user_id: currentUserId || undefined,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Upload failed");
    }

    const result = await res.json();
    return { result, user_id: result.user_id };
  };

  const handleFileUpload = async (source: string, file: File) => {
    setUploading(source);
    setError(null);

    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const { result, user_id } = await uploadSource(source, data, userId);

      if (!userId && user_id) onUserIdChange(user_id);
      setUploaded((prev) => ({ ...prev, [source]: result }));
      onUploadComplete(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload");
    } finally {
      setUploading(null);
    }
  };

  const handleUseSample = async (source: string) => {
    setUploading(source);
    setError(null);

    try {
      const sampleFile = SOURCES.find((s) => s.id === source)?.sampleFile;
      if (!sampleFile) throw new Error("No sample file");

      const sampleRes = await fetch(`/sample-data/${sampleFile}`);
      if (!sampleRes.ok) throw new Error("Sample file not found");
      const data = await sampleRes.json();

      const { result, user_id } = await uploadSource(source, data, userId);

      if (!userId && user_id) onUserIdChange(user_id);
      setUploaded((prev) => ({ ...prev, [source]: result }));
      onUploadComplete(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sample");
    } finally {
      setUploading(null);
    }
  };

  const handleTryDemo = async () => {
    setDemoLoading(true);
    setError(null);
    let currentUserId = userId;

    try {
      for (const source of SOURCES) {
        if (uploaded[source.id]) continue; // skip already uploaded

        const sampleRes = await fetch(`/sample-data/${source.sampleFile}`);
        if (!sampleRes.ok) continue;
        const data = await sampleRes.json();

        const { result, user_id } = await uploadSource(
          source.id,
          data,
          currentUserId
        );

        if (!currentUserId && user_id) {
          currentUserId = user_id;
          onUserIdChange(user_id);
        }

        setUploaded((prev) => ({ ...prev, [source.id]: result }));
        onUploadComplete(result);
      }

      if (onAllDemoLoaded) onAllDemoLoaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo loading failed");
    } finally {
      setDemoLoading(false);
    }
  };

  const totalChunks = Object.values(uploaded).reduce(
    (sum, r) => sum + r.chunks_stored,
    0
  );
  const allUploaded = SOURCES.every((s) => s.id in uploaded);

  return (
    <div className="fade-in mx-auto max-w-2xl px-4">
      <div className="mb-8 text-center">
        <div className="mb-4 text-6xl">🔗</div>
        <h2 className="mb-3 text-3xl font-bold tracking-tight">
          Connect Your <span className="gradient-text">Data</span>
        </h2>
        <p className="mx-auto max-w-md text-muted">
          We analyze your digital footprint to understand your travel personality.
          Upload your data exports or try a demo.
        </p>
      </div>

      {/* Try Demo button (prominent) */}
      {!allUploaded && (
        <div className="mb-6 text-center">
          <button
            onClick={handleTryDemo}
            disabled={demoLoading}
            className="rounded-2xl bg-accent px-8 py-4 text-lg font-semibold text-white transition-all hover:scale-105 hover:bg-accent-hover disabled:opacity-50"
          >
            {demoLoading ? (
              <span className="inline-flex items-center gap-2">
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Loading demo data...
              </span>
            ) : (
              "🚀 Try Demo — Load Sample Data"
            )}
          </button>
          <p className="mt-2 text-xs text-muted">
            Loads sample Spotify, YouTube, Maps & Instagram data instantly
          </p>
        </div>
      )}

      {/* Source cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {SOURCES.map((source) => {
          const isUploaded = source.id in uploaded;
          const isUploading = uploading === source.id;
          const result = uploaded[source.id];

          return (
            <div
              key={source.id}
              className={`rounded-xl border p-4 text-center transition-all ${
                isUploaded
                  ? "border-success/50 bg-success/5"
                  : "border-border bg-card"
              }`}
            >
              <div className="mb-2 text-3xl">{source.emoji}</div>
              <div className="mb-1 text-sm font-semibold">{source.label}</div>

              {isUploading ? (
                <div className="flex items-center justify-center gap-1 text-xs text-accent">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                </div>
              ) : isUploaded ? (
                <div className="text-xs text-success">
                  ✓ {result.chunks_stored} signals
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  <label className="cursor-pointer rounded-lg border border-border px-2 py-1 text-[10px] font-medium text-muted transition-colors hover:border-accent hover:text-foreground">
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
                    className="rounded-lg bg-accent/10 px-2 py-1 text-[10px] font-medium text-accent transition-colors hover:bg-accent/20"
                  >
                    Sample
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
            <span className="font-semibold text-accent">
              {totalChunks} preference signals
            </span>{" "}
            from{" "}
            <span className="font-semibold">
              {Object.keys(uploaded).length} source
              {Object.keys(uploaded).length > 1 ? "s" : ""}
            </span>
          </p>
        </div>
      )}
    </div>
  );
}

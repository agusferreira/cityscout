"use client";

interface ProfileCardProps {
  profile: string;
  quizAnswers: Record<string, string>;
  enhanced?: boolean;
  dataSources?: string[];
}

const EMOJI_MAP: Record<string, string> = {
  coffee: "☕",
  food: "🍽️",
  activity: "🏃",
  nightlife: "🌙",
  neighborhood: "🏘️",
  budget: "💰",
};

const LABEL_MAP: Record<string, string> = {
  coffee: "Coffee",
  food: "Food",
  activity: "Activity",
  nightlife: "Nightlife",
  neighborhood: "Neighborhood",
  budget: "Budget",
};

const SOURCE_EMOJI: Record<string, string> = {
  spotify: "🎵",
  youtube: "📺",
  google_maps: "📍",
  instagram: "📸",
};

const SOURCE_LABEL: Record<string, string> = {
  spotify: "Spotify",
  youtube: "YouTube",
  google_maps: "Google Maps",
  instagram: "Instagram",
};

export default function ProfileCard({
  profile,
  quizAnswers,
  enhanced = false,
  dataSources = [],
}: ProfileCardProps) {
  return (
    <div className="fade-in mx-auto max-w-2xl px-4">
      {/* Profile text */}
      <div className="gradient-border mb-8 rounded-2xl p-8">
        <div className="mb-4 text-center">
          <span className="text-5xl">{enhanced ? "✨" : "🧭"}</span>
        </div>
        <h2 className="mb-4 text-center text-xl font-bold">
          Your{" "}
          {enhanced ? (
            <span className="gradient-text">Enhanced Travel DNA</span>
          ) : (
            <span className="gradient-text">Travel DNA</span>
          )}
        </h2>
        <p className="text-center text-lg leading-relaxed text-foreground/90">
          {profile}
        </p>

        {/* Enhanced badge */}
        {enhanced && dataSources.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            <span className="text-xs text-muted">Powered by:</span>
            {dataSources.map((src) => (
              <span
                key={src}
                className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2.5 py-0.5 text-xs text-accent"
              >
                {SOURCE_EMOJI[src] || "📊"} {SOURCE_LABEL[src] || src}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Quiz summary chips */}
      <div className="mb-6 flex flex-wrap justify-center gap-2">
        {Object.entries(quizAnswers).map(([key, value]) => (
          <span
            key={key}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-sm"
          >
            <span>{EMOJI_MAP[key] || "✨"}</span>
            <span className="text-muted">{LABEL_MAP[key] || key}:</span>
            <span className="font-medium">{value}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

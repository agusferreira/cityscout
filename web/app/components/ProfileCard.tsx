"use client";

interface ProfileCardProps {
  profile: string;
  quizAnswers: Record<string, string>;
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

export default function ProfileCard({ profile, quizAnswers }: ProfileCardProps) {
  return (
    <div className="fade-in mx-auto max-w-2xl px-4">
      {/* Profile text */}
      <div className="gradient-border mb-8 rounded-2xl p-8">
        <div className="mb-4 text-center">
          <span className="text-5xl">🧭</span>
        </div>
        <h2 className="mb-4 text-center text-xl font-bold">
          Your <span className="gradient-text">Travel DNA</span>
        </h2>
        <p className="text-center text-lg leading-relaxed text-foreground/90">
          {profile}
        </p>
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

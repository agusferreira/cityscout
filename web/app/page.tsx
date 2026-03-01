"use client";

import { useState, useEffect, useCallback } from "react";
import QuizStep, { QuizStepData } from "./components/QuizStep";
import ProfileCard from "./components/ProfileCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

// ── Quiz Data ──

const QUIZ_STEPS: QuizStepData[] = [
  {
    id: "coffee",
    title: "What's your coffee vibe?",
    subtitle: "How you start your morning says everything about you.",
    options: [
      {
        id: "Specialty pour-over",
        label: "Third Wave Temple",
        emoji: "☕",
        description:
          "Single-origin pour-overs, light roasts, and baristas who geek out about extraction",
      },
      {
        id: "Cozy café regular",
        label: "Cozy Corner Regular",
        emoji: "🛋️",
        description:
          "Warm atmosphere, great lattes, a book and a pastry — the perfect morning",
      },
      {
        id: "Quick espresso standing up",
        label: "Quick Espresso",
        emoji: "⚡",
        description:
          "Knock back an espresso at the counter like a local — no fuss, all fuel",
      },
      {
        id: "Laptop café worker",
        label: "Digital Nomad HQ",
        emoji: "💻",
        description:
          "Reliable wifi, power outlets, great coffee, and nobody rushing you out",
      },
    ],
  },
  {
    id: "food",
    title: "How do you eat?",
    subtitle: "Your food style reveals your true travel personality.",
    options: [
      {
        id: "Street food and markets",
        label: "Street Food Hunter",
        emoji: "🌮",
        description:
          "Hole-in-the-wall spots, food markets, and eating standing up at a counter",
      },
      {
        id: "Fine dining and tasting menus",
        label: "Fine Dining Explorer",
        emoji: "🍷",
        description:
          "Tasting menus, wine pairings, and chefs who tell stories through food",
      },
      {
        id: "Local traditional cuisine",
        label: "Tradition Keeper",
        emoji: "🥘",
        description:
          "The dish grandma makes, the 100-year-old restaurant, the recipe that hasn't changed",
      },
      {
        id: "Vegetarian and health-conscious",
        label: "Plant-Forward",
        emoji: "🥬",
        description:
          "Organic markets, creative vegetarian cuisine, smoothie bowls, and acai",
      },
    ],
  },
  {
    id: "activity",
    title: "What gets you moving?",
    subtitle: "How you spend your days shapes your ideal itinerary.",
    options: [
      {
        id: "Walking tours and street art",
        label: "Urban Explorer",
        emoji: "🚶",
        description:
          "Get lost in neighborhoods, discover street art, stumble into hidden gems",
      },
      {
        id: "Museums and galleries",
        label: "Culture Vulture",
        emoji: "🎨",
        description:
          "World-class museums, local galleries, architecture walks, and bookshops",
      },
      {
        id: "Outdoor sports and fitness",
        label: "Active Adventurer",
        emoji: "🏄",
        description:
          "Running routes, surf spots, hiking trails, gym drop-ins, and yoga classes",
      },
      {
        id: "Shopping and relaxing",
        label: "Leisure & Style",
        emoji: "🛍️",
        description:
          "Boutique shopping, spa days, scenic parks, and leisurely brunches",
      },
    ],
  },
  {
    id: "nightlife",
    title: "When the sun goes down...",
    subtitle: "Your nightlife style is the ultimate travel personality test.",
    options: [
      {
        id: "Cocktail bars and speakeasies",
        label: "Speakeasy Seeker",
        emoji: "🍸",
        description:
          "Hidden doors, craft cocktails, moody lighting, and bartenders who are artists",
      },
      {
        id: "Live music and dancing",
        label: "Live & Loud",
        emoji: "🎵",
        description:
          "Jazz clubs, local bands, late-night dancing, and feeling the bass in your chest",
      },
      {
        id: "Wine bars and dinner",
        label: "Wine & Dine",
        emoji: "🍷",
        description:
          "Natural wine bars, long dinners, local vintages, and great conversation",
      },
      {
        id: "Early to bed, early to rise",
        label: "Sunrise > Sunset",
        emoji: "🌅",
        description:
          "A quiet drink then early to bed — you'll catch the sunrise while everyone's sleeping",
      },
    ],
  },
  {
    id: "neighborhood",
    title: "Your ideal neighborhood?",
    subtitle: "Where you stay defines your whole trip experience.",
    options: [
      {
        id: "Artsy and bohemian",
        label: "Artsy & Bohemian",
        emoji: "🎭",
        description:
          "Street art, independent shops, creative energy, and locals who express themselves",
      },
      {
        id: "Historic and charming",
        label: "Old Soul",
        emoji: "🏛️",
        description:
          "Cobblestone streets, centuries-old buildings, history around every corner",
      },
      {
        id: "Trendy and upscale",
        label: "Trendy & Polished",
        emoji: "✨",
        description:
          "The hottest restaurants, design boutiques, and the neighborhood everyone's talking about",
      },
      {
        id: "Local and residential",
        label: "Deep Local",
        emoji: "🏘️",
        description:
          "Where tourists don't go, real neighborhood life, corner bars, and morning markets",
      },
    ],
  },
  {
    id: "budget",
    title: "What's your budget vibe?",
    subtitle: "No judgment — every budget has its own adventure style.",
    options: [
      {
        id: "Backpacker budget",
        label: "Budget Explorer",
        emoji: "🎒",
        description:
          "Street food, free activities, happy hours, and making every dollar count",
      },
      {
        id: "Mid-range comfort",
        label: "Smart Spender",
        emoji: "💳",
        description:
          "Great restaurants, comfortable stays, occasional splurge on something special",
      },
      {
        id: "Treat yourself",
        label: "Treat Yourself",
        emoji: "💎",
        description:
          "Life's too short for bad wine. Nice hotels, great meals, premium experiences",
      },
      {
        id: "No budget, full experience",
        label: "Money Is No Object",
        emoji: "🥂",
        description:
          "Michelin stars, private tours, the best of everything — you're here to experience it all",
      },
    ],
  },
];

// ── Types ──

interface City {
  slug: string;
  name: string;
  chunk_count: number;
  categories: string[];
}

interface IngestStatus {
  running: boolean;
  phase: string;
  total: number;
  processed: number;
  error: string | null;
}

type AppState = "landing" | "quiz" | "profile" | "city-select" | "loading-guide";

// ── City Emojis ──
const CITY_EMOJI: Record<string, string> = {
  "buenos-aires": "🇦🇷",
  barcelona: "🇪🇸",
  lisbon: "🇵🇹",
};

// ── Loading Component ──

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

  const phaseColor: Record<string, string> = {
    idle: "text-muted",
    loading: "text-warning",
    indexing: "text-warning",
    embedding: "text-accent",
    done: "text-success",
    error: "text-error",
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
      <p className={`text-sm ${phaseColor[status.phase] || "text-muted"}`}>
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
  const [appState, setAppState] = useState<AppState>("landing");
  const [quizStep, setQuizStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [profile, setProfile] = useState("");
  const [profileLoading, setProfileLoading] = useState(false);
  const [cities, setCities] = useState<City[]>([]);
  const [selectedCity, setSelectedCity] = useState<string | null>(null);
  const [ingestStatus, setIngestStatus] = useState<IngestStatus>({
    running: false,
    phase: "idle",
    total: 0,
    processed: 0,
    error: null,
  });

  // Fetch cities and ingest status on mount
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
      } catch {
        /* server may be down */
      }
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

  const handleQuizSelect = async (optionId: string) => {
    const currentStep = QUIZ_STEPS[quizStep];
    const newAnswers = { ...answers, [currentStep.id]: optionId };
    setAnswers(newAnswers);

    // Auto-advance after brief delay
    setTimeout(async () => {
      if (quizStep < QUIZ_STEPS.length - 1) {
        setQuizStep(quizStep + 1);
      } else {
        // Quiz complete — generate profile
        setAppState("profile");
        setProfileLoading(true);
        try {
          const res = await fetch(`${API_URL}/api/profile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ quiz_answers: newAnswers }),
          });
          const data = await res.json();
          setProfile(data.profile);
        } catch (err) {
          setProfile(
            "A curious traveler who loves discovering local gems and authentic experiences."
          );
        } finally {
          setProfileLoading(false);
        }
      }
    }, 300);
  };

  const handleCitySelect = (citySlug: string) => {
    setSelectedCity(citySlug);
    // Navigate to guide page with state
    const params = new URLSearchParams({
      city: citySlug,
      profile: profile,
    });
    window.location.href = `/guide?${params.toString()}`;
  };

  // ── Landing Page ──
  if (appState === "landing") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-4">
        <div className="mb-12 text-center">
          <div className="mb-6 text-7xl">🧭</div>
          <h1 className="mb-4 text-5xl font-bold tracking-tight md:text-6xl">
            City<span className="gradient-text">Scout</span>
          </h1>
          <p className="mx-auto max-w-lg text-lg text-muted">
            Discover any city through your unique lens. Answer a few questions,
            get a personalized guide powered by local knowledge.
          </p>
        </div>

        <button
          onClick={() => setAppState("quiz")}
          className="mb-8 rounded-2xl bg-accent px-8 py-4 text-lg font-semibold text-white transition-all hover:scale-105 hover:bg-accent-hover"
        >
          Start Your Taste Quiz →
        </button>

        <div className="mt-4 flex flex-col items-center gap-3 text-sm text-muted">
          <span>⏱️ Takes about 60 seconds</span>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-accent/50" />
            <span>Powered by RAG + Pinecone + OpenAI</span>
          </div>
        </div>

        {/* Admin: Ingest Panel */}
        <div className="mt-12 w-full max-w-md">
          <IngestPanel status={ingestStatus} onIngest={startIngestion} />
        </div>
      </div>
    );
  }

  // ── Quiz ──
  if (appState === "quiz") {
    return (
      <div className="flex min-h-screen flex-col justify-center py-12">
        <QuizStep
          step={QUIZ_STEPS[quizStep]}
          selected={answers[QUIZ_STEPS[quizStep].id] || null}
          onSelect={handleQuizSelect}
          stepIndex={quizStep}
          totalSteps={QUIZ_STEPS.length}
        />
        {quizStep > 0 && (
          <button
            onClick={() => setQuizStep(quizStep - 1)}
            className="mx-auto mt-6 text-sm text-muted hover:text-foreground"
          >
            ← Back
          </button>
        )}
      </div>
    );
  }

  // ── Profile ──
  if (appState === "profile") {
    return (
      <div className="flex min-h-screen flex-col justify-center py-12">
        {profileLoading ? (
          <div className="text-center">
            <div className="mb-4 text-5xl">🔮</div>
            <p className="text-lg text-muted">
              Analyzing your travel DNA <LoadingDots />
            </p>
          </div>
        ) : (
          <>
            <ProfileCard profile={profile} quizAnswers={answers} />

            <div className="mx-auto mt-8 text-center">
              <p className="mb-4 text-muted">Does this look right?</p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={() => setAppState("city-select")}
                  className="rounded-xl bg-accent px-6 py-3 font-semibold text-white transition-all hover:scale-105 hover:bg-accent-hover"
                >
                  That&apos;s me! Pick a city →
                </button>
                <button
                  onClick={() => {
                    setQuizStep(0);
                    setAnswers({});
                    setAppState("quiz");
                  }}
                  className="rounded-xl border border-border px-6 py-3 text-muted transition-colors hover:border-accent hover:text-foreground"
                >
                  Retake Quiz
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    );
  }

  // ── City Selection ──
  if (appState === "city-select") {
    return (
      <div className="flex min-h-screen flex-col justify-center py-12">
        <div className="fade-in mx-auto max-w-2xl px-4">
          <div className="mb-8 text-center">
            <h2 className="mb-2 text-3xl font-bold">
              Where are you <span className="gradient-text">headed</span>?
            </h2>
            <p className="text-muted">
              Pick a city and we&apos;ll create your personalized guide
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
        </div>
      </div>
    );
  }

  return null;
}

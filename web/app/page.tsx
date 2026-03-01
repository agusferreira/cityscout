"use client";

import { useState, useEffect, useCallback } from "react";
import ConnectData from "./components/ConnectData";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

// ── Types ──

interface City {
  slug: string;
  name: string;
  chunk_count: number;
  categories: string[];
}

type AppState = "connect" | "city-select";

const CITY_EMOJI: Record<string, string> = {
  "buenos-aires": "🇦🇷",
  barcelona: "🇪🇸",
  lisbon: "🇵🇹",
};

const CITY_DESCRIPTIONS: Record<string, string> = {
  "buenos-aires": "Tango, steak, and late-night magic",
  barcelona: "Gaudí, tapas, and Mediterranean vibes",
  lisbon: "Tiles, fado, and pastéis de nata",
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

// ── Main Page ──

export default function Home() {
  const [appState, setAppState] = useState<AppState>("connect");
  const [userId, setUserId] = useState("");
  const [uploadedSources, setUploadedSources] = useState<string[]>([]);
  const [cities, setCities] = useState<City[]>([]);
  const [profileSummary, setProfileSummary] = useState("");
  const [profileLoading, setProfileLoading] = useState(false);
  const [citySearch, setCitySearch] = useState("");

  // Fetch cities on mount
  useEffect(() => {
    fetch(`${API_URL}/api/cities`)
      .then((r) => r.json())
      .then((data) => setCities(data.cities || []))
      .catch(() => {});
  }, []);

  // Generate profile when arriving at city select
  const generateProfile = useCallback(
    async (uid: string) => {
      setProfileLoading(true);
      try {
        // Use the enhance endpoint to generate a profile from uploaded data
        const res = await fetch(`${API_URL}/api/profile/enhance`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            quiz_answers: {
              coffee: "Not specified",
              food: "Not specified",
              activity: "Not specified",
              nightlife: "Not specified",
              neighborhood: "Not specified",
              budget: "Not specified",
            },
            user_id: uid,
          }),
        });

        if (res.ok) {
          const data = await res.json();
          setProfileSummary(data.profile || "");
        }
      } catch {
        // Profile generation is optional — we can still proceed
      } finally {
        setProfileLoading(false);
      }
    },
    []
  );

  const handleDataComplete = (uid: string, sources: string[]) => {
    setUserId(uid);
    setUploadedSources(sources);
    setAppState("city-select");
    generateProfile(uid);
  };

  const handleCitySelect = (citySlug: string) => {
    const activeProfile =
      profileSummary ||
      "A curious traveler who loves discovering local gems and authentic experiences.";
    const params = new URLSearchParams({
      city: citySlug,
      profile: activeProfile,
    });
    if (userId) {
      params.set("user_id", userId);
    }
    window.location.href = `/results?${params.toString()}`;
  };

  // Filter cities by search
  const filteredCities = citySearch
    ? cities.filter(
        (c) =>
          c.name.toLowerCase().includes(citySearch.toLowerCase()) ||
          c.slug.includes(citySearch.toLowerCase().replace(/\s+/g, "-"))
      )
    : cities;

  // ── Page 1: Connect Your Data ──
  if (appState === "connect") {
    return (
      <ConnectData onComplete={handleDataComplete} />
    );
  }

  // ── Page 2: City Selection ──
  if (appState === "city-select") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
        <div className="mx-auto w-full max-w-2xl">
          {/* Profile Summary */}
          {(profileSummary || profileLoading) && (
            <div className="fade-in mb-8 rounded-xl border border-accent/20 bg-accent/5 p-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-accent">
                🧬 Your Taste Profile
              </h3>
              {profileLoading ? (
                <p className="text-sm text-muted">
                  Analyzing your data <LoadingDots />
                </p>
              ) : (
                <p className="text-sm leading-relaxed text-foreground/80">
                  {profileSummary}
                </p>
              )}
            </div>
          )}

          {/* Header */}
          <div className="mb-8 text-center">
            <h2 className="mb-2 text-3xl font-bold">
              Where are you{" "}
              <span className="gradient-text">headed</span>?
            </h2>
            <p className="text-muted">
              Pick a city and we'll create your personalized map & guide
            </p>
          </div>

          {/* Search Input */}
          <div className="mb-6">
            <input
              type="text"
              value={citySearch}
              onChange={(e) => setCitySearch(e.target.value)}
              placeholder="Search cities..."
              className="w-full rounded-xl border border-border bg-card px-4 py-3 text-foreground placeholder-muted outline-none transition-colors focus:border-accent"
            />
          </div>

          {/* City Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {filteredCities.map((city) => (
              <button
                key={city.slug}
                onClick={() => handleCitySelect(city.slug)}
                className="quiz-option group rounded-xl border border-border p-6 text-center"
              >
                <div className="mb-3 text-5xl">
                  {CITY_EMOJI[city.slug] || "🌍"}
                </div>
                <div className="mb-1 text-lg font-semibold group-hover:text-accent">
                  {city.name}
                </div>
                <div className="mb-2 text-xs text-muted">
                  {CITY_DESCRIPTIONS[city.slug] || `${city.chunk_count} local tips`}
                </div>
                <div className="flex flex-wrap justify-center gap-1">
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

          {filteredCities.length === 0 && citySearch && (
            <div className="mt-6 text-center text-muted">
              <p>No cities match "{citySearch}"</p>
              <p className="text-xs mt-1">
                Available: Buenos Aires, Barcelona, Lisbon
              </p>
            </div>
          )}

          {/* Back button */}
          <div className="mt-8 text-center">
            <button
              onClick={() => setAppState("connect")}
              className="text-sm text-muted hover:text-foreground"
            >
              ← Back to data connection
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
}

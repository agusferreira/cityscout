"use client";

interface RecommendationCardProps {
  name: string;
  neighborhood: string;
  category: string;
  reason: string;
  details: string[];
  sourceType: string;
  sourceUrl: string;
}

export default function RecommendationCard({
  name,
  neighborhood,
  category,
  reason,
  details,
  sourceType,
  sourceUrl,
}: RecommendationCardProps) {
  const badgeClass = `badge-${category}`;

  return (
    <div className="rounded-xl border border-border bg-card p-5 transition-colors hover:border-accent/30">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h4 className="text-lg font-semibold">{name}</h4>
          <span className="text-sm text-muted">({neighborhood})</span>
        </div>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badgeClass}`}
        >
          {category}
        </span>
      </div>

      <p className="mb-3 text-sm leading-relaxed text-foreground/80">
        <span className="font-medium text-accent">Why it&apos;s for you:</span>{" "}
        {reason}
      </p>

      {details.length > 0 && (
        <ul className="mb-3 space-y-1">
          {details.map((detail, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-muted">
              <span className="mt-1 text-accent">•</span>
              {detail}
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-2 border-t border-border pt-3 text-xs text-muted">
        <span className="rounded bg-card-hover px-1.5 py-0.5 font-mono">
          {sourceType}
        </span>
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="truncate text-accent hover:underline"
        >
          {sourceUrl}
        </a>
      </div>
    </div>
  );
}

"use client";

interface Source {
  score: number;
  text: string;
  category: string;
  source_url: string;
  source_type: string;
  city: string;
  date: string;
}

interface Scores {
  faithfulness: number | null;
  context_precision: number | null;
  relevancy: number | null;
  error?: string;
}

interface GuideSectionProps {
  guide: string;
  sources: Source[];
  scores: Scores;
  city: string;
}

function formatMarkdown(md: string): string {
  return md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/^(\d+)\. (.+)$/gm, "<li>$2</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`)
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br/>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
}

function ScoreBar({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  if (value === null || value === undefined) return null;
  const pct = Math.round(value * 100);
  const color =
    value >= 0.8
      ? "bg-success"
      : value >= 0.5
        ? "bg-warning"
        : "bg-error";

  return (
    <div className="flex items-center gap-3">
      <span className="w-36 text-sm text-muted">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-border">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-12 text-right font-mono text-sm">{pct}%</span>
    </div>
  );
}

function CategoryBadge({ category }: { category: string }) {
  const badgeClass = `badge-${category}`;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${badgeClass}`}
    >
      {category}
    </span>
  );
}

export default function GuideSection({
  guide,
  sources,
  scores,
  city,
}: GuideSectionProps) {
  return (
    <div className="fade-in mx-auto max-w-3xl px-4">
      {/* Header */}
      <div className="mb-8 text-center">
        <h1 className="mb-2 text-3xl font-bold md:text-4xl">
          Your <span className="gradient-text">{city.replace("-", " ").replace(/\b\w/g, c => c.toUpperCase())}</span> Guide
        </h1>
        <p className="text-muted">
          Personalized recommendations based on your taste profile
        </p>
      </div>

      {/* Guide content */}
      <div className="mb-8 rounded-xl border border-border bg-card p-6 md:p-8">
        <div
          className="prose-guide"
          dangerouslySetInnerHTML={{ __html: formatMarkdown(guide) }}
        />
      </div>

      {/* RAGAS Scores */}
      {!scores.error && (
        <div className="mb-8 rounded-xl border border-border bg-card p-6">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
            RAG Quality Scores (RAGAS)
          </h3>
          <div className="space-y-3">
            <ScoreBar label="Faithfulness" value={scores.faithfulness} />
            <ScoreBar label="Context Precision" value={scores.context_precision} />
            <ScoreBar label="Relevancy" value={scores.relevancy} />
          </div>
          <p className="mt-3 text-xs text-muted">
            Evaluated using RAGAS framework — measures how well the guide is grounded in retrieved sources.
          </p>
        </div>
      )}

      {/* Sources */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          Sources ({sources.length} chunks retrieved)
        </h3>
        <div className="space-y-3">
          {sources.map((source, idx) => (
            <SourceCard key={idx} source={source} index={idx} />
          ))}
        </div>
      </div>
    </div>
  );
}

function SourceCard({ source, index }: { source: Source; index: number }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="shrink-0 rounded bg-accent/20 px-1.5 py-0.5 font-mono text-xs text-accent">
              #{index + 1}
            </span>
            <CategoryBadge category={source.category} />
            <span className="text-xs text-muted">
              {source.source_type}
            </span>
            <span className="text-xs text-accent">
              {(source.score * 100).toFixed(1)}% match
            </span>
          </div>
          <p className="line-clamp-2 text-sm text-muted">
            {source.text.slice(0, 150)}...
          </p>
          {source.source_url && (
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-block text-xs text-accent hover:underline"
            >
              {source.source_url.slice(0, 60)}...
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

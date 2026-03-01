"use client";

export interface QuizOption {
  id: string;
  label: string;
  emoji: string;
  description: string;
}

export interface QuizStepData {
  id: string;
  title: string;
  subtitle: string;
  options: QuizOption[];
}

interface QuizStepProps {
  step: QuizStepData;
  selected: string | null;
  onSelect: (optionId: string) => void;
  stepIndex: number;
  totalSteps: number;
}

export default function QuizStep({
  step,
  selected,
  onSelect,
  stepIndex,
  totalSteps,
}: QuizStepProps) {
  return (
    <div className="fade-in mx-auto max-w-2xl px-4">
      {/* Progress */}
      <div className="mb-8">
        <div className="mb-2 flex items-center justify-between text-sm text-muted">
          <span>
            {stepIndex + 1} of {totalSteps}
          </span>
          <span>{Math.round(((stepIndex + 1) / totalSteps) * 100)}%</span>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full bg-accent transition-all duration-500 ease-out"
            style={{
              width: `${((stepIndex + 1) / totalSteps) * 100}%`,
            }}
          />
        </div>
      </div>

      {/* Question */}
      <div className="mb-8 text-center">
        <h2 className="mb-2 text-2xl font-bold tracking-tight md:text-3xl">
          {step.title}
        </h2>
        <p className="text-muted">{step.subtitle}</p>
      </div>

      {/* Options Grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {step.options.map((option) => (
          <button
            key={option.id}
            onClick={() => onSelect(option.id)}
            className={`quiz-option rounded-xl border p-5 text-left ${
              selected === option.id
                ? "selected border-accent"
                : "border-border"
            }`}
          >
            <div className="mb-2 text-3xl">{option.emoji}</div>
            <div className="mb-1 font-semibold">{option.label}</div>
            <div className="text-sm text-muted">{option.description}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

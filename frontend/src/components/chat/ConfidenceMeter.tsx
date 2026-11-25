import {
  type ConfidenceCategory,
  designTokens,
} from "../../styles/design-tokens";

interface ConfidenceMeterProps {
  category: ConfidenceCategory;
  score: number;
  stairLevel?: string;
}

export function ConfidenceMeter({
  category,
  score,
  stairLevel = "L1",
}: ConfidenceMeterProps) {
  const style = designTokens.confidenceStyles[category] || designTokens.confidenceStyles.None;
  const pct = Math.round(Math.min(1, Math.max(0, score)) * 100);

  return (
    <div className="flex flex-wrap items-center gap-3 rounded border border-console-border bg-console-bg px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
          RETRIEVAL CONFIDENCE
        </span>
        <span
          style={{
            color: style.color,
            backgroundColor: style.bg,
            borderColor: style.border,
          }}
          className="rounded border px-2 py-0.5 font-mono text-[11px] font-semibold tracking-wide"
        >
          {style.label}
        </span>
      </div>

      <div className="flex min-w-[120px] flex-1 items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-console-elevated">
          <div
            style={{ width: `${pct}%`, backgroundColor: style.color }}
            className="h-full transition-all duration-300"
          />
        </div>
        <span className="font-mono text-[11px] tabular-nums text-ink-secondary">
          {(score * 100).toFixed(0)}%
        </span>
      </div>

      <span className="rounded border border-console-border px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
        STAIR {stairLevel}
      </span>
    </div>
  );
}

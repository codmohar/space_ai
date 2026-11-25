interface PhasePlaceholderPageProps {
  code: string;
  title: string;
  description: string;
}

export function PhasePlaceholderPage({
  code,
  title,
  description,
}: PhasePlaceholderPageProps) {
  return (
    <div className="flex h-full items-center justify-center bg-console-bg p-6">
      <div className="max-w-lg rounded border border-console-border bg-console-surface p-6">
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-signal-amber">
          {code} // SCHEDULED FOR PHASE 2+
        </span>
        <h2 className="mt-2 text-lg font-semibold text-ink-primary">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-secondary">
          {description}
        </p>
        <div className="mt-4 rounded border border-console-border bg-console-bg px-3 py-2 font-mono text-xs text-ink-muted">
          Status: Schema & shared retrieval/citation foundations ready in Phase 1.
        </div>
      </div>
    </div>
  );
}

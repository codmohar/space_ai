import { useQuery } from "@tanstack/react-query";
import { Activity, Terminal } from "lucide-react";
import { api } from "../api/client";

export function EvaluationPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["eval-results"],
    queryFn: api.evalResults,
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-console-bg font-mono text-xs text-ink-muted">
        Loading measured evaluation outputs...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="rounded border border-status-conflict/50 bg-status-conflict/10 p-4 font-mono text-xs text-status-conflict">
          Failed to fetch evaluation results: {(error as Error).message}
        </div>
      </div>
    );
  }

  const isEvaluated = data?.status === "evaluated" && (data.methods?.length ?? 0) > 0;

  return (
    <div className="h-full overflow-y-auto bg-console-bg p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-console-border pb-4">
          <div>
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-signal-amber">
              EVL-06 // BENCHMARK TELEMETRY
            </span>
            <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink-primary">
              Retrieval & STAIR Evaluation Dashboard
            </h2>
            <p className="mt-1 text-sm text-ink-secondary">
              Displays only metrics measured by <code className="font-mono text-xs">scripts/evaluate_retrieval.py</code>. Unmeasured metrics never appear as results.
            </p>
          </div>
          <span
            className={`rounded border px-2.5 py-1 font-mono text-xs uppercase ${
              isEvaluated
                ? "border-status-verified/40 bg-status-verified/10 text-status-verified"
                : "border-console-borderStrong bg-console-surface text-ink-secondary"
            }`}
          >
            {data?.status || "Not yet evaluated"}
          </span>
        </div>

        {!isEvaluated ? (
          <div className="rounded border border-console-border bg-console-surface p-6">
            <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-signal-amber">
              <Activity className="h-4 w-4" />
              NOT YET EVALUATED
            </div>
            <p className="mt-2 text-sm text-ink-secondary">
              No measured benchmark output was found at{" "}
              <code className="font-mono text-xs text-ink-primary">
                data/evaluation/retrieval_results.json
              </code>
              . Run the evaluation script against your seeded database to populate
              Recall@1/3/5, MRR, nDCG@5, invalid-section rate, and latency comparisons:
            </p>
            <div className="mt-4 flex items-center gap-2 rounded border border-console-border bg-console-bg px-4 py-3 font-mono text-xs text-ink-primary">
              <Terminal className="h-4 w-4 shrink-0 text-signal-amber" />
              <span>
                python scripts/evaluate_retrieval.py --questions data/evaluation/questions.jsonl
              </span>
            </div>
          </div>
        ) : (
          <>
            {/* Summary Strip */}
            <div className="grid grid-cols-12 gap-4">
              <SummaryCell
                label="Questions Dataset"
                value={String(data.total_questions)}
                sub={`${data.answerable_questions} answerable · ${data.unanswerable_questions} unanswerable`}
              />
              <SummaryCell
                label="Methods Compared"
                value={String(data.methods.length)}
                sub="BM25, Dense, Hybrid, STAIR"
              />
              <SummaryCell
                label="Top Recall@5"
                value={`${(Math.max(...data.methods.map((m) => m.recall_at_5)) * 100).toFixed(1)}%`}
                sub="Best across evaluated runs"
              />
              <SummaryCell
                label="Run Timestamp"
                value={data.generated_at ? data.generated_at.slice(0, 10) : "Recorded"}
                sub={data.dataset_path || "questions.jsonl"}
              />
            </div>

            {/* Bar Comparison Charts (Recall@1/3/5, MRR, nDCG@5) */}
            <div className="rounded border border-console-border bg-console-surface p-4">
              <h3 className="mb-4 font-mono text-xs uppercase tracking-wider text-ink-primary">
                Baseline vs STAIR Retrieval Comparison
              </h3>
              <div className="space-y-4">
                {data.methods.map((m) => (
                  <div
                    key={m.method}
                    className="rounded border border-console-border bg-console-bg p-3"
                  >
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-semibold uppercase text-signal-amber">
                          {m.method}
                        </span>
                        <span className="rounded border border-console-borderStrong px-1.5 py-0.5 font-mono text-[10px] text-ink-secondary">
                          {m.stair_level}
                        </span>
                      </div>
                      <span className="font-mono text-[11px] tabular-nums text-ink-muted">
                        avg {m.avg_latency_ms} ms · p95 {m.p95_latency_ms} ms · invalid-sec{" "}
                        {(m.invalid_section_rate * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
                      <MetricBar label="R@1" value={m.recall_at_1} />
                      <MetricBar label="R@3" value={m.recall_at_3} />
                      <MetricBar label="R@5" value={m.recall_at_5} />
                      <MetricBar label="MRR" value={m.mrr} />
                      <MetricBar label="nDCG@5" value={m.ndcg_at_5} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function SummaryCell({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div className="col-span-12 rounded border border-console-border bg-console-surface px-4 py-3 sm:col-span-6 lg:col-span-3">
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
        {label}
      </span>
      <div className="mt-1 font-mono text-xl font-semibold tabular-nums text-ink-primary">
        {value}
      </div>
      <p className="mt-0.5 font-mono text-[11px] text-ink-secondary">{sub}</p>
    </div>
  );
}

function MetricBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div>
      <div className="flex justify-between font-mono text-[10px] tabular-nums text-ink-secondary">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-console-elevated">
        <div
          style={{ width: `${pct}%` }}
          className="h-full bg-signal-amber transition-all duration-300"
        />
      </div>
    </div>
  );
}

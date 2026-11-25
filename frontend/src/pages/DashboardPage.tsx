import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpen, Database, FileSearch, ShieldCheck } from "lucide-react";
import { api } from "../api/client";
import { useWorkspaceStore } from "../stores/workspaceStore";

export function DashboardPage() {
  const setActiveRoute = useWorkspaceStore((s) => s.setActiveRoute);

  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery({
    queryKey: ["corpus-stats"],
    queryFn: api.stats,
  });

  const { data: docs } = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
  });

  return (
    <div className="h-full overflow-y-auto bg-console-bg p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Header Strip */}
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-console-border pb-4">
          <div>
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-signal-amber">
              SYSTEM OVERVIEW // PHASE 1
            </span>
            <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink-primary">
              Mission Engineering Knowledge Console
            </h2>
            <p className="mt-1 text-sm text-ink-secondary">
              Evidence-grounded retrieval across public NASA, ISRO, and ESA mishap and review archives.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setActiveRoute("assistant")}
              className="inline-flex items-center gap-2 rounded border border-signal-amber bg-signal-amber px-3.5 py-2 text-xs font-semibold uppercase tracking-wide text-console-base hover:bg-signal-amber/90"
            >
              <FileSearch className="h-4 w-4" />
              Open Research Assistant
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setActiveRoute("documents")}
              className="inline-flex items-center gap-2 rounded border border-console-borderStrong bg-console-surface px-3.5 py-2 text-xs font-medium uppercase tracking-wide text-ink-primary hover:bg-console-elevated"
            >
              <BookOpen className="h-4 w-4 text-ink-secondary" />
              Browse Reports
            </button>
          </div>
        </div>

        {/* Real Corpus Telemetry Cards (12-col grid) */}
        <div className="grid grid-cols-12 gap-4">
          <StatCard
            span="col-span-12 sm:col-span-6 lg:col-span-3"
            label="Ingested Reports"
            value={statsLoading ? "…" : String(stats?.document_count ?? 0)}
            sub="Public domain PDFs with licence"
          />
          <StatCard
            span="col-span-12 sm:col-span-6 lg:col-span-3"
            label="Hierarchical Sections"
            value={statsLoading ? "…" : String(stats?.section_count ?? 0)}
            sub="STAIR L1 ToC / heading index"
          />
          <StatCard
            span="col-span-12 sm:col-span-6 lg:col-span-3"
            label="Indexed Evidence Chunks"
            value={statsLoading ? "…" : String(stats?.chunk_count ?? 0)}
            sub={`${stats?.ocr_chunk_count ?? 0} OCR-extracted chunks`}
          />
          <StatCard
            span="col-span-12 sm:col-span-6 lg:col-span-3"
            label="Logged Queries"
            value={statsLoading ? "…" : String(stats?.retrieval_log_count ?? 0)}
            sub="Full stage scores persisted"
          />
        </div>

        {statsError && (
          <div className="rounded border border-status-conflict/40 bg-status-conflict/10 px-4 py-3 font-mono text-xs text-status-conflict">
            Failed to fetch live telemetry: {(statsError as Error).message}
          </div>
        )}

        {/* Evaluation & Architecture Honesty Grid */}
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-12 rounded border border-console-border bg-console-surface p-4 lg:col-span-7">
            <div className="flex items-center justify-between border-b border-console-border pb-2.5">
              <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-ink-primary">
                <Database className="h-4 w-4 text-signal-amber" />
                Seeded Mission Archives
              </span>
              <span className="font-mono text-[11px] text-ink-muted">
                {docs?.length ?? 0} ACTIVE
              </span>
            </div>
            <div className="mt-3 divide-y divide-console-border">
              {(docs || []).map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-center justify-between gap-4 py-2.5 text-sm"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-signal-amber">
                        {doc.doc_code}
                      </span>
                      <span className="truncate font-medium text-ink-primary">
                        {doc.title}
                      </span>
                    </div>
                    <p className="mt-0.5 font-mono text-[11px] text-ink-muted">
                      {doc.mission} · {doc.page_count} pages · {doc.chunk_count} chunks ·{" "}
                      {doc.licence}
                    </p>
                  </div>
                  <span className="shrink-0 rounded border border-status-verified/40 bg-status-verified/10 px-2 py-0.5 font-mono text-[10px] uppercase text-status-verified">
                    {doc.ingestion_status}
                  </span>
                </div>
              ))}
              {(!docs || docs.length === 0) && (
                <p className="py-4 font-mono text-xs text-ink-muted">
                  No documents ingested yet. Run scripts/ingest_documents.py to seed reports.
                </p>
              )}
            </div>
          </div>

          <div className="col-span-12 rounded border border-console-border bg-console-surface p-4 lg:col-span-5">
            <div className="flex items-center justify-between border-b border-console-border pb-2.5">
              <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-ink-primary">
                <ShieldCheck className="h-4 w-4 text-status-verified" />
                Evaluation & STAIR Status
              </span>
              <span className="rounded border border-console-borderStrong px-2 py-0.5 font-mono text-[10px] text-ink-secondary">
                {stats?.evaluation_status || "Not yet evaluated"}
              </span>
            </div>
            <div className="mt-3 space-y-2.5 text-xs text-ink-secondary">
              <div className="flex items-center justify-between rounded border border-console-border bg-console-bg px-3 py-2">
                <span>Retrieval Benchmarks (BM25 / Dense / STAIR)</span>
                <span className="font-mono text-ink-muted">Not yet evaluated</span>
              </div>
              <div className="flex items-center justify-between rounded border border-console-border bg-console-bg px-3 py-2">
                <span>RAG Groundedness & Abstention (40-Q Set)</span>
                <span className="font-mono text-ink-muted">Not yet evaluated</span>
              </div>
              <div className="flex items-center justify-between rounded border border-console-border bg-console-bg px-3 py-2">
                <span>STAIR Pipeline Level</span>
                <span className="font-mono text-signal-amber">L1 Index Active</span>
              </div>
              <p className="pt-1 font-mono text-[11px] leading-relaxed text-ink-muted">
                Per platform policy, unmeasured benchmark metrics are never displayed as results.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  span,
  label,
  value,
  sub,
}: {
  span: string;
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div
      className={`${span} rounded border border-console-border bg-console-surface px-4 py-3.5`}
    >
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </span>
      <div className="mt-1.5 font-mono text-2xl font-semibold tabular-nums text-ink-primary">
        {value}
      </div>
      <p className="mt-1 text-[11px] text-ink-secondary">{sub}</p>
    </div>
  );
}

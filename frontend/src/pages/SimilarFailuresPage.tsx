import { type FormEvent, useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  Database,
  Eye,
  GitBranch,
  Layers,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";
import {
  api,
  type CitationOut,
  type SimilarFailuresSearchResponse,
  type SimilarIncidentOut,
} from "../api/client";
import { CitationViewer } from "../components/viewer/CitationViewer";
import { useWorkspaceStore } from "../stores/workspaceStore";
import { designTokens } from "../styles/design-tokens";

const SAMPLE_PROBLEMS = [
  "Novel dual-stage hypergolic descent engine with pulse-width modulation valves and ground software trajectory scaling",
  "Composite cryogenic oxygen tank with integrated immersion heater thermostat switches and Teflon insulated wiring",
  "Autonomous touchdown detection logic using multi-redundant laser altimeters and landing leg compression switches",
  "Ground software thruster impulse unit mismatch causing trajectory altitude error at Mars",
  "Spurious Hall effect landing leg sensor transient triggering premature descent engine shutdown",
];

export function SimilarFailuresPage() {
  const [problem, setProblem] = useState(SAMPLE_PROBLEMS[0]);
  const [searchResult, setSearchResult] =
    useState<SimilarFailuresSearchResponse | null>(null);
  const [activePdfCit, setActivePdfCit] = useState<CitationOut | null>(null);

  const setFailureChainDocId = useWorkspaceStore((s) => s.setFailureChainDocId);
  const setActiveRoute = useWorkspaceStore((s) => s.setActiveRoute);
  const prefillSimilarQuery = useWorkspaceStore((s) => s.prefillSimilarQuery);
  const setPrefillSimilarQuery = useWorkspaceStore((s) => s.setPrefillSimilarQuery);

  const searchMutation = useMutation({
    mutationFn: (problem_description: string) =>
      api.searchSimilarFailures({ problem_description, top_k: 6 }),
    onSuccess: (data) => setSearchResult(data),
  });

  useEffect(() => {
    if (prefillSimilarQuery) {
      setProblem(prefillSimilarQuery);
      setPrefillSimilarQuery(null);
      searchMutation.mutate(prefillSimilarQuery);
    }
  }, [prefillSimilarQuery, setPrefillSimilarQuery, searchMutation]);

  const reindexMutation = useMutation({
    mutationFn: () => api.indexKnowledgeGraph(null, true),
    onSuccess: () => {
      if (problem.trim().length >= 4) {
        searchMutation.mutate(problem.trim());
      }
    },
  });

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    if (problem.trim().length < 4 || searchMutation.isPending) return;
    searchMutation.mutate(problem.trim());
  };

  const openPdf = (inc: SimilarIncidentOut) => {
    setActivePdfCit({
      document_id: inc.document_id,
      doc_code: inc.doc_code,
      document_title: inc.document_title,
      source_url: inc.source_url,
      licence: inc.licence,
      section: inc.section,
      page_number: inc.page_number,
      chunk_id: inc.chunk_id,
      quote: inc.evidence_text,
      bbox_json: inc.bbox_json,
      verified: inc.verification_status === "verified",
    });
  };

  const jumpToFailureChain = (docId: string) => {
    setFailureChainDocId(docId);
    setActiveRoute("failures");
  };

  return (
    <div className="flex h-full overflow-hidden bg-console-bg">
      {/* Main Search & Incident Cards Column */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="border-b border-console-border bg-console-surface px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-signal-amber">
                SIM-05 // ENGINEERING ANALOGY RETRIEVAL
              </span>
              <h2 className="mt-0.5 text-lg font-semibold text-ink-primary">
                Similar Past Failures
              </h2>
            </div>

            <button
              type="button"
              disabled={reindexMutation.isPending}
              onClick={() => reindexMutation.mutate()}
              className="inline-flex items-center gap-1.5 rounded border border-console-borderStrong bg-console-bg px-3 py-1.5 font-mono text-xs text-ink-secondary hover:border-signal-amber hover:text-ink-primary disabled:opacity-40"
            >
              <Database className="h-3.5 w-3.5 text-signal-amber" />
              {reindexMutation.isPending
                ? "Indexing Reports..."
                : "Rebuild Incident Index"}
            </button>
          </div>

          <form onSubmit={handleSearch} className="mt-3 flex flex-col gap-2">
            <textarea
              rows={3}
              value={problem}
              onChange={(e) => setProblem(e.target.value)}
              placeholder="Describe a novel engineering design proposal, subsystem architecture, or historical anomaly symptom to find historical failure precedents across all mission reports..."
              className="w-full rounded border border-console-borderStrong bg-console-bg px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:border-signal-amber focus:outline-none resize-none font-sans"
            />
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-mono text-[10px] text-ink-muted">
                Tip: Enter detailed engineering proposals to evaluate cross-mission risk precedents & failure mechanisms.
              </span>
              <button
                type="submit"
                disabled={searchMutation.isPending || problem.trim().length < 4}
                className="inline-flex items-center justify-center gap-1.5 rounded border border-signal-amber bg-signal-amber px-4 py-2 font-mono text-xs font-semibold uppercase tracking-wide text-console-base hover:bg-signal-amber/90 disabled:opacity-40"
              >
                <Search className="h-3.5 w-3.5" />
                {searchMutation.isPending ? "Searching All Reports..." : "Analyze Precedents & Risks"}
              </button>
            </div>
          </form>

          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {SAMPLE_PROBLEMS.map((sp) => (
              <button
                key={sp}
                type="button"
                onClick={() => {
                  setProblem(sp);
                  searchMutation.mutate(sp);
                }}
                className="rounded border border-console-border bg-console-bg px-2.5 py-1 font-mono text-[10px] text-ink-secondary hover:border-signal-amber/60 hover:text-ink-primary"
              >
                {sp.slice(0, 56)}…
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          {searchResult && (
            <div className="flex flex-wrap items-center gap-2 rounded border border-console-border bg-console-surface px-3.5 py-2 font-mono text-[11px]">
              <span className="text-ink-muted">EXTRACTED PROFILE:</span>
              {searchResult.extracted_subsystems.map((sub) => (
                <span
                  key={sub}
                  className="rounded border border-signal-amber/50 bg-signal-amberDim px-2 py-0.5 text-signal-amber"
                >
                  {sub}
                </span>
              ))}
              {searchResult.extracted_mechanisms.map((m) => (
                <span
                  key={m}
                  className="rounded border border-status-verified/40 bg-status-verified/10 px-2 py-0.5 text-status-verified"
                >
                  {m}
                </span>
              ))}
              {searchResult.extracted_subsystems.length === 0 &&
                searchResult.extracted_mechanisms.length === 0 && (
                  <span className="text-ink-secondary">
                    {searchResult.extracted_keywords.join(", ")}
                  </span>
                )}
            </div>
          )}

          {/* Design Risk Summary & Architectural Precedents */}
          {searchResult?.design_risk_summary && (
            <div className="rounded border border-signal-amber/40 bg-signal-amberDim/40 p-4">
              <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-signal-amber">
                <ShieldAlert className="h-4 w-4" />
                SYSTEM DESIGN RISK SUMMARY & ARCHITECTURAL PRECEDENTS
              </div>
              <p className="mt-2 text-xs leading-relaxed text-ink-primary font-mono">
                {searchResult.design_risk_summary}
              </p>
            </div>
          )}

          {/* Inferred Risk Hypotheses */}
          {searchResult?.risk_hypotheses && searchResult.risk_hypotheses.length > 0 && (
            <div className="rounded border border-console-border bg-console-surface p-3 space-y-1.5 font-mono text-xs">
              <div className="text-[10px] uppercase tracking-wider text-ink-muted">
                INFERRED RISK HYPOTHESES (SYSTEM INFERENCE):
              </div>
              <ul className="list-disc list-inside space-y-1 text-ink-secondary text-[11px]">
                {searchResult.risk_hypotheses.map((rh, idx) => (
                  <li key={idx} className="leading-relaxed">
                    <span className="text-signal-amber font-semibold">{rh.slice(0, 10)}</span>
                    {rh.slice(10)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {searchMutation.isError && (
            <div className="rounded border border-status-conflict/40 bg-status-conflict/10 p-3 font-mono text-xs text-status-conflict">
              {(searchMutation.error as Error).message}
            </div>
          )}

          {!searchResult && !searchMutation.isPending && (
            <div className="rounded border border-console-border bg-console-surface p-8 text-center">
              <Layers className="mx-auto h-8 w-8 text-console-borderStrong" />
              <p className="mt-2 font-mono text-xs text-ink-secondary">
                Describe an engineering problem above to search indexed mission anomalies
                using hybrid embeddings + BM25 + cross-encoder reranking + subsystem match boost.
              </p>
            </div>
          )}

          {searchResult && searchResult.results.length === 0 && (
            <div className="rounded border border-console-border bg-console-surface p-6 font-mono text-xs text-ink-secondary">
              No matching incidents found. Click &quot;Rebuild Incident Index&quot; to index
              ingested reports first.
            </div>
          )}

          {(searchResult?.results || []).map((inc) => {
            const badge =
              designTokens.evidenceClassificationLabels[inc.evidence_classification] ||
              designTokens.evidenceClassificationLabels.explicitly_stated;
            return (
              <article
                key={inc.incident_id}
                className="rounded border border-console-border bg-console-surface p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded border border-signal-amber/40 bg-signal-amberDim px-2 py-0.5 font-mono text-[11px] font-semibold text-signal-amber">
                        {inc.mission}
                      </span>
                      <span className="rounded border border-console-borderStrong px-2 py-0.5 font-mono text-[11px] text-ink-primary">
                        {inc.subsystem}
                      </span>
                      <span className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase ${badge.tone}`}>
                        {badge.label}
                      </span>
                      <span className="font-mono text-[11px] text-ink-muted">
                        [{inc.doc_code} · p.{inc.page_number}]
                      </span>
                    </div>
                    <h3 className="mt-2 text-base font-semibold text-ink-primary">
                      {inc.anomaly_title}
                    </h3>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <span className="rounded border border-status-verified/40 bg-status-verified/10 px-2.5 py-1 font-mono text-xs font-semibold tabular-nums text-status-verified">
                      {(inc.relevance.total_relevance * 100).toFixed(0)}% MATCH
                    </span>
                    <button
                      type="button"
                      onClick={() => openPdf(inc)}
                      className="inline-flex items-center gap-1 rounded border border-console-borderStrong bg-console-bg px-2.5 py-1 font-mono text-xs text-ink-primary hover:border-signal-amber"
                    >
                      <Eye className="h-3.5 w-3.5" />
                      Open PDF
                    </button>
                    <button
                      type="button"
                      onClick={() => jumpToFailureChain(inc.document_id)}
                      className="inline-flex items-center gap-1 rounded border border-signal-amber bg-signal-amber px-2.5 py-1 font-mono text-xs font-semibold text-console-base hover:bg-signal-amber/90"
                    >
                      <GitBranch className="h-3.5 w-3.5" />
                      Reconstruct chain
                    </button>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
                  <div className="rounded border border-console-border bg-console-bg p-2.5">
                    <span className="font-mono text-[10px] uppercase text-ink-muted">
                      ROOT CAUSE
                    </span>
                    <p className="mt-1 leading-relaxed text-ink-primary">
                      {inc.root_cause}
                    </p>
                  </div>
                  <div className="rounded border border-console-border bg-console-bg p-2.5">
                    <span className="font-mono text-[10px] uppercase text-ink-muted">
                      CONSEQUENCE
                    </span>
                    <p className="mt-1 leading-relaxed text-ink-primary">
                      {inc.consequence}
                    </p>
                  </div>
                  <div className="rounded border border-console-border bg-console-bg p-2.5">
                    <span className="font-mono text-[10px] uppercase text-ink-muted">
                      CORRECTIVE ACTION
                    </span>
                    <p className="mt-1 leading-relaxed text-ink-primary">
                      {inc.corrective_action}
                    </p>
                  </div>
                </div>

                {/* Transparent Relevance Breakdown */}
                <div className="mt-3 grid grid-cols-2 gap-2 rounded border border-console-border bg-console-bg px-3 py-2 font-mono text-[10px] tabular-nums sm:grid-cols-5">
                  <div>
                    <span className="text-ink-muted">SEMANTIC</span>
                    <div className="text-ink-primary">
                      {(inc.relevance.semantic_score * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div>
                    <span className="text-ink-muted">KEYWORD (BM25)</span>
                    <div className="text-ink-primary">
                      {(inc.relevance.keyword_score * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div>
                    <span className="text-ink-muted">CROSS-ENCODER</span>
                    <div className="text-ink-primary">
                      {(inc.relevance.rerank_score * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div>
                    <span className="text-ink-muted">SUBSYSTEM BOOST</span>
                    <div className="text-signal-amber">
                      +{(inc.relevance.subsystem_match_score * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="col-span-2 sm:col-span-1">
                    <span className="text-ink-muted">MATCHED</span>
                    <div className="truncate text-ink-secondary">
                      {inc.relevance.matched_terms.join(", ") || "semantic"}
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </div>

      {/* Optional Slide-Over PDF Evidence Drawer */}
      {activePdfCit && (
        <div className="flex w-[46%] min-w-[360px] flex-col border-l border-console-border bg-doc-paper">
          <div className="flex items-center justify-between border-b border-console-border bg-console-surface px-3 py-2">
            <span className="font-mono text-xs text-signal-amber">
              SOURCE EVIDENCE · {activePdfCit.doc_code} p.{activePdfCit.page_number}
            </span>
            <button
              type="button"
              onClick={() => setActivePdfCit(null)}
              className="rounded p-1 text-ink-secondary hover:text-ink-primary"
              aria-label="Close PDF drawer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            <CitationViewer citation={activePdfCit} />
          </div>
        </div>
      )}
    </div>
  );
}

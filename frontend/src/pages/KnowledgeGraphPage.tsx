import { type FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  type Edge,
  MarkerType,
  type Node,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Database, Eye, Network, Search, X } from "lucide-react";
import {
  api,
  type CitationOut,
  type KGNodeOut,
  type KGQueryResponse,
} from "../api/client";
import { CitationChip } from "../components/chat/CitationChip";
import { CitationViewer } from "../components/viewer/CitationViewer";

const ENTITY_X_COLUMN: Record<string, number> = {
  mission: 40,
  subsystem: 320,
  component: 600,
  anomaly: 880,
  root_cause: 1180,
  corrective_action: 1480,
};

const ENTITY_COLORS: Record<string, string> = {
  mission: "#F2A33A",
  subsystem: "#60A5FA",
  component: "#A78BFA",
  anomaly: "#E5534B",
  root_cause: "#F59E0B",
  corrective_action: "#2EBD85",
};

const SAMPLE_KG_QUERIES = [
  "missions with propulsion anomalies and their corrective actions",
  "power and cryogenic oxygen anomalies and root causes",
  "landing systems anomalies and software verification corrective actions",
];

export function KnowledgeGraphPage() {
  const [missionFilter, setMissionFilter] = useState("");
  const [kgQuery, setKgQuery] = useState(SAMPLE_KG_QUERIES[0]);
  const [queryResult, setQueryResult] = useState<KGQueryResponse | null>(null);
  const [selectedNode, setSelectedNode] = useState<KGNodeOut | null>(null);
  const [activePdfCit, setActivePdfCit] = useState<CitationOut | null>(null);

  const graphQuery = useQuery({
    queryKey: ["kg-graph", missionFilter],
    queryFn: () => api.getKnowledgeGraph(missionFilter || undefined),
  });

  const indexMutation = useMutation({
    mutationFn: () => api.indexKnowledgeGraph(null, true),
    onSuccess: () => graphQuery.refetch(),
  });

  const multihopMutation = useMutation({
    mutationFn: (q: string) =>
      api.queryKnowledgeGraph(q, missionFilter || null),
    onSuccess: (res) => setQueryResult(res),
  });

  const { nodes, edges } = useMemo(() => {
    const rawNodes = graphQuery.data?.nodes || [];
    const rawEdges = graphQuery.data?.edges || [];

    const rowCounts: Record<string, number> = {};
    const rfNodes: Node[] = rawNodes.map((n) => {
      const col = n.entity_type;
      const rowIdx = rowCounts[col] || 0;
      rowCounts[col] = rowIdx + 1;
      const accent = ENTITY_COLORS[col] || "#9AA4B2";
      return {
        id: n.id,
        position: {
          x: ENTITY_X_COLUMN[col] ?? 600,
          y: rowIdx * 96 + 40,
        },
        data: {
          label: (
            <div className="w-[215px] text-left">
              <div
                style={{ color: accent }}
                className="font-mono text-[9px] uppercase tracking-wider"
              >
                {n.entity_type.replace("_", " ")}
              </div>
              <div className="mt-0.5 line-clamp-2 text-[11.5px] font-medium text-ink-primary">
                {n.name}
              </div>
              <div className="mt-1 font-mono text-[9px] text-ink-muted">
                {n.doc_code} · p.{n.page_number}
              </div>
            </div>
          ),
          kgNode: n,
        },
        style: {
          background: "#11161F",
          border: `1px solid ${
            selectedNode?.id === n.id ? "#F2A33A" : "#2E3A4E"
          }`,
          borderLeft: `3px solid ${accent}`,
          borderRadius: 4,
          padding: 8,
          width: 235,
        },
      };
    });

    const rfEdges: Edge[] = rawEdges.map((e) => {
      const isVerified = e.verification_status === "verified";
      return {
        id: e.id,
        source: e.source_entity_id,
        target: e.target_entity_id,
        type: "smoothstep",
        label: e.relation_type.toUpperCase(),
        style: {
          stroke: isVerified ? "#2EBD85" : "#F2A33A",
          strokeWidth: 1.5,
          strokeDasharray: isVerified ? undefined : "5 4",
        },
        labelStyle: {
          fill: "#9AA4B2",
          fontSize: 9,
          fontFamily: '"IBM Plex Mono", monospace',
        },
        labelBgStyle: { fill: "#0B0E13", fillOpacity: 0.9 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: isVerified ? "#2EBD85" : "#F2A33A",
        },
      };
    });

    return { nodes: rfNodes, edges: rfEdges };
  }, [graphQuery.data, selectedNode?.id]);

  const handleMultiHopSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (kgQuery.trim().length < 3 || multihopMutation.isPending) return;
    multihopMutation.mutate(kgQuery.trim());
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-console-bg">
      {/* Top Multi-Hop Query & Index Bar */}
      <div className="border-b border-console-border bg-console-surface px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-signal-amber">
              KG-07 // MISSION &gt; SUBSYSTEM &gt; COMPONENT &gt; ANOMALY &gt; ROOT CAUSE &gt; CORRECTIVE ACTION
            </span>
            <h2 className="mt-0.5 text-base font-semibold text-ink-primary">
              Engineering Knowledge Graph Explorer
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <select
              aria-label="Filter graph by mission"
              value={missionFilter}
              onChange={(e) => setMissionFilter(e.target.value)}
              className="rounded border border-console-borderStrong bg-console-bg px-2.5 py-1.5 font-mono text-xs text-ink-primary"
            >
              <option value="">All Missions</option>
              <option value="Mars Climate Orbiter">Mars Climate Orbiter</option>
              <option value="Apollo 13">Apollo 13</option>
              <option value="Mars Polar Lander">Mars Polar Lander</option>
            </select>
            <button
              type="button"
              disabled={indexMutation.isPending}
              onClick={() => indexMutation.mutate()}
              className="inline-flex items-center gap-1.5 rounded border border-console-borderStrong bg-console-bg px-3 py-1.5 font-mono text-xs text-ink-primary hover:border-signal-amber disabled:opacity-40"
            >
              <Database className="h-3.5 w-3.5 text-signal-amber" />
              {indexMutation.isPending ? "Indexing KG..." : "Index / Refresh KG"}
            </button>
          </div>
        </div>

        <form onSubmit={handleMultiHopSubmit} className="mt-2.5 flex gap-2">
          <input
            type="text"
            value={kgQuery}
            onChange={(e) => setKgQuery(e.target.value)}
            placeholder="Multi-hop query: e.g., missions with propulsion anomalies and their corrective actions"
            className="flex-1 rounded border border-console-borderStrong bg-console-bg px-3 py-1.5 text-xs text-ink-primary placeholder:text-ink-muted focus:border-signal-amber focus:outline-none"
          />
          <button
            type="submit"
            disabled={multihopMutation.isPending || kgQuery.trim().length < 3}
            className="inline-flex items-center gap-1.5 rounded border border-signal-amber bg-signal-amber px-3.5 py-1.5 font-mono text-xs font-semibold uppercase text-console-base hover:bg-signal-amber/90 disabled:opacity-40"
          >
            <Search className="h-3.5 w-3.5" />
            {multihopMutation.isPending ? "Querying..." : "Run Multi-Hop Query"}
          </button>
        </form>
      </div>

      {/* Main Workspace: React Flow KG Canvas + Right Query/Citation/PDF Panel */}
      <div className="grid min-h-0 flex-1 grid-cols-12 overflow-hidden">
        <div
          role="region"
          aria-label="Engineering Knowledge Graph"
          className="relative col-span-12 h-full border-r border-console-border lg:col-span-7"
        >
          {nodes.length === 0 && !graphQuery.isLoading ? (
            <div className="flex h-full flex-col items-center justify-center p-8 text-center">
              <Network className="h-9 w-9 text-console-borderStrong" />
              <p className="mt-3 max-w-md font-mono text-xs text-ink-secondary">
                No Knowledge Graph entities indexed yet. Click{" "}
                <span className="text-signal-amber">Index / Refresh KG</span> above to
                extract Mission &gt; Subsystem &gt; Component &gt; Anomaly &gt; Root Cause &gt;
                Corrective Action relations from ingested reports.
              </p>
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              fitView
              onNodeClick={(_ev, node) => {
                const kgNode = (node.data as { kgNode?: KGNodeOut }).kgNode;
                if (kgNode) {
                  setSelectedNode(kgNode);
                  setActivePdfCit(null);
                }
              }}
              className="bg-console-bg"
            >
              <Background color="#222B3A" gap={22} />
              <Controls className="!border-console-border !bg-console-surface !text-ink-primary" />
            </ReactFlow>
          )}
        </div>

        {/* Right Panel: Cited Multi-Hop Answer, Selected Node Provenance, or PDF Viewer */}
        <div className="col-span-12 flex h-full flex-col overflow-hidden bg-console-surface lg:col-span-5">
          {activePdfCit ? (
            <>
              <div className="flex items-center justify-between border-b border-console-border px-3 py-2">
                <span className="font-mono text-xs text-signal-amber">
                  PDF PROVENANCE · {activePdfCit.doc_code} p.{activePdfCit.page_number}
                </span>
                <button
                  type="button"
                  onClick={() => setActivePdfCit(null)}
                  className="rounded p-1 text-ink-secondary hover:text-ink-primary"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                <CitationViewer citation={activePdfCit} />
              </div>
            </>
          ) : (
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              {queryResult && (
                <div className="rounded border border-console-border bg-console-bg p-3.5">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-signal-amber">
                    MULTI-HOP GRAPH ANSWER ({queryResult.paths.length} PATHS)
                  </span>
                  <div className="mt-2 space-y-2.5">
                    {queryResult.abstained ? (
                      <p className="font-mono text-xs text-ink-secondary">
                        {queryResult.answer}
                      </p>
                    ) : (
                      queryResult.paths.map((p, idx) => (
                        <div
                          key={idx}
                          className="rounded border border-console-border bg-console-surface p-2.5 text-xs"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono font-semibold text-signal-amber">
                              {p.mission} · {p.subsystem}
                            </span>
                            <CitationChip
                              citation={p.citation}
                              onSelect={(c) => setActivePdfCit(c)}
                            />
                          </div>
                          <p className="mt-1 font-medium text-ink-primary">
                            Anomaly: {p.anomaly}
                          </p>
                          <p className="mt-0.5 text-ink-secondary">
                            Root cause: {p.root_cause}
                          </p>
                          <p className="mt-0.5 text-status-verified">
                            Corrective action: {p.corrective_action}
                          </p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {selectedNode && (
                <div className="rounded border border-console-borderStrong bg-console-bg p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-signal-amber">
                      SELECTED ENTITY · {selectedNode.entity_type}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setActivePdfCit({
                          document_id: selectedNode.document_id,
                          doc_code: selectedNode.doc_code,
                          document_title: selectedNode.document_title,
                          source_url: selectedNode.source_url,
                          licence: selectedNode.licence,
                          section: selectedNode.section,
                          page_number: selectedNode.page_number,
                          chunk_id: selectedNode.chunk_id,
                          quote: selectedNode.evidence_text,
                          bbox_json: selectedNode.bbox_json,
                          verified: true,
                        })
                      }
                      className="inline-flex items-center gap-1 rounded border border-signal-amber bg-signal-amber px-2 py-1 font-mono text-[10px] font-semibold text-console-base"
                    >
                      <Eye className="h-3 w-3" />
                      Open PDF p.{selectedNode.page_number}
                    </button>
                  </div>
                  <h4 className="mt-1.5 text-sm font-semibold text-ink-primary">
                    {selectedNode.name}
                  </h4>
                  <p className="mt-2 font-serif text-xs italic leading-relaxed text-ink-secondary">
                    “{selectedNode.evidence_text}”
                  </p>
                </div>
              )}

              {!queryResult && !selectedNode && (
                <div className="rounded border border-console-border bg-console-bg p-4 font-mono text-xs text-ink-secondary">
                  Run a multi-hop query above or click any entity node in the graph to
                  inspect cited paths and primary report evidence.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

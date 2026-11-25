import { type FormEvent, useEffect, useMemo, useState } from "react";
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
import {
  AlertTriangle,
  Eye,
  GitBranch,
  Mic,
  Play,
  Search,
  Send,
  Square,
} from "lucide-react";
import {
  api,
  type ChatResponse,
  type CitationOut,
  type DocumentSummary,
  type FailureEventOut,
  type FailureRelationshipOut,
} from "../api/client";
import { ClaimBlock } from "../components/chat/ClaimBlock";
import {
  FailureEventNode,
  type FailureNodeData,
} from "../components/failures/FailureEventNode";
import { CitationViewer } from "../components/viewer/CitationViewer";
import { useVoiceAssistant } from "../hooks/useVoiceAssistant";
import { useWorkspaceStore } from "../stores/workspaceStore";
import { designTokens } from "../styles/design-tokens";

type EdgeFilter = "all" | "causal" | "chronology";

const NODE_TYPES = { failureEvent: FailureEventNode };

export function FailureChainPage() {
  const [missionQuery, setMissionQuery] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<DocumentSummary | null>(null);
  const [edgeFilter, setEdgeFilter] = useState<EdgeFilter>("all");
  const [selectedEvent, setSelectedEvent] = useState<FailureEventOut | null>(
    null
  );
  const [inspectorTab, setInspectorTab] = useState<"details" | "pdf">("details");
  const [pdfCitation, setPdfCitation] = useState<CitationOut | null>(null);
  const [followUpInput, setFollowUpInput] = useState("");
  const [followUpConvId, setFollowUpConvId] = useState<string | null>(null);
  const [followUpResponse, setFollowUpResponse] = useState<ChatResponse | null>(
    null
  );

  const failureChainDocId = useWorkspaceStore((s) => s.failureChainDocId);
  const setFailureChainDocId = useWorkspaceStore((s) => s.setFailureChainDocId);

  const { data: docs } = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
  });

  const filteredDocs = useMemo(() => {
    const q = missionQuery.trim().toLowerCase();
    const list = docs || [];
    if (!q) return list;
    return list.filter(
      (d) =>
        d.mission.toLowerCase().includes(q) ||
        d.doc_code.toLowerCase().includes(q) ||
        d.title.toLowerCase().includes(q)
    );
  }, [docs, missionQuery]);

  useEffect(() => {
    if (failureChainDocId && docs) {
      const target = docs.find((d) => d.id === failureChainDocId);
      if (target) {
        setSelectedDoc(target);
        setFailureChainDocId(null);
        return;
      }
    }
    if (!selectedDoc && filteredDocs.length > 0) {
      setSelectedDoc(filteredDocs[0]);
    }
  }, [docs, failureChainDocId, filteredDocs, selectedDoc, setFailureChainDocId]);

  const eventsQuery = useQuery({
    queryKey: ["failure-events", selectedDoc?.id],
    queryFn: () => api.getFailureEvents(selectedDoc!.id),
    enabled: Boolean(selectedDoc?.id),
  });

  const relsQuery = useQuery({
    queryKey: ["failure-relationships", selectedDoc?.id],
    queryFn: () => api.getFailureRelationships(selectedDoc!.id),
    enabled: Boolean(selectedDoc?.id),
  });

  const reconstructMutation = useMutation({
    mutationFn: (docId: string) => api.reconstructFailures(docId, true),
    onSuccess: (data) => {
      eventsQuery.refetch();
      relsQuery.refetch();
      if (data.events.length > 0) {
        setSelectedEvent(data.events[0]);
        setInspectorTab("details");
      }
    },
  });

  const followUpMutation = useMutation({
    mutationFn: (query: string) =>
      api.chat({
        query,
        conversation_id: followUpConvId,
        mission: selectedDoc?.mission || null,
      }),
    onSuccess: (res) => {
      setFollowUpConvId(res.conversation_id);
      setFollowUpResponse(res);
    },
  });

  const voice = useVoiceAssistant({
    conversationId: followUpConvId,
    mission: selectedDoc?.mission || "",
    selectorMode: "auto",
    onTranscript: () => undefined,
    onAnswer: (res) => {
      setFollowUpConvId(res.conversation_id);
      setFollowUpResponse(res);
    },
  });

  const events: FailureEventOut[] = eventsQuery.data || [];
  const relationships: FailureRelationshipOut[] = relsQuery.data || [];

  const { nodes, edges } = useMemo(() => {
    const ordered = [...events].sort((a, b) => a.event_order - b.event_order);
    const rfNodes: Node<FailureNodeData>[] = ordered.map((ev, idx) => {
      const isCausalRoot =
        ev.evidence_classification === "official_root_cause" ||
        ev.evidence_classification === "official_contributing_factor";
      return {
        id: ev.id,
        type: "failureEvent",
        position: {
          x: idx * 310 + 40,
          y: isCausalRoot ? 210 : 50,
        },
        data: {
          event: ev,
          isSelected: selectedEvent?.id === ev.id,
        },
      };
    });

    const filteredRels = relationships.filter((r) => {
      if (edgeFilter === "chronology") return r.relationship_type === "preceded_by";
      if (edgeFilter === "causal") return r.relationship_type !== "preceded_by";
      return true;
    });

    const rfEdges: Edge[] = filteredRels.map((r) => {
      const isChronology = r.relationship_type === "preceded_by";
      const isVerified = r.verification_status === "verified";
      const color = isChronology
        ? "#647082"
        : isVerified
          ? "#2EBD85"
          : "#F2A33A";

      return {
        id: r.id,
        source: r.source_event_id,
        target: r.target_event_id,
        type: "smoothstep",
        label: isVerified
          ? r.relationship_type.toUpperCase()
          : `${r.relationship_type.toUpperCase()} · UNVERIFIED`,
        animated: !isVerified && !isChronology,
        style: {
          stroke: color,
          strokeWidth: isVerified ? 2 : 1.75,
          strokeDasharray: isVerified && !isChronology ? undefined : "6 4",
        },
        labelStyle: {
          fill: isVerified ? "#E8E6DF" : "#F2A33A",
          fontSize: 10,
          fontFamily: '"IBM Plex Mono", monospace',
        },
        labelBgStyle: {
          fill: "#11161F",
          fillOpacity: 0.92,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
        },
      };
    });

    return { nodes: rfNodes, edges: rfEdges };
  }, [events, relationships, edgeFilter, selectedEvent?.id]);

  const openPdfForEvent = (ev: FailureEventOut) => {
    setPdfCitation({
      document_id: ev.document_id,
      doc_code: ev.doc_code,
      document_title: ev.document_title,
      source_url: ev.source_url,
      licence: ev.licence,
      section_id: ev.section_id,
      section: ev.section,
      page_number: ev.page_number,
      chunk_id: ev.chunk_id,
      quote: ev.evidence_text,
      bbox_json: ev.bbox_json,
      verified: ev.verification_status === "verified",
    });
    setInspectorTab("pdf");
  };

  const handleFollowUpSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = followUpInput.trim();
    if (!q || followUpMutation.isPending) return;
    const contextualQuery = selectedEvent
      ? `Regarding failure event "${selectedEvent.title}" in ${selectedEvent.mission} (p.${selectedEvent.page_number}): ${q}`
      : q;
    setFollowUpInput("");
    followUpMutation.mutate(contextualQuery);
  };

  const selectedBadge = selectedEvent
    ? designTokens.evidenceClassificationLabels[
        selectedEvent.evidence_classification
      ] || designTokens.evidenceClassificationLabels.explicitly_stated
    : null;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-console-bg">
      {/* Top Control Strip: Search Mission -> Select Report -> Reconstruct */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-console-border bg-console-surface px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-ink-muted" />
            <input
              type="text"
              value={missionQuery}
              onChange={(e) => setMissionQuery(e.target.value)}
              placeholder="Search mission or doc code..."
              aria-label="Search mission"
              className="w-52 rounded border border-console-borderStrong bg-console-bg py-1.5 pl-8 pr-2.5 font-mono text-xs text-ink-primary placeholder:text-ink-muted focus:border-signal-amber focus:outline-none"
            />
          </div>

          <select
            aria-label="Select mission report"
            value={selectedDoc?.id || ""}
            onChange={(e) => {
              const found = (docs || []).find((d) => d.id === e.target.value) || null;
              setSelectedDoc(found);
              setSelectedEvent(null);
              setFollowUpResponse(null);
              setFollowUpConvId(null);
            }}
            className="max-w-xs rounded border border-console-borderStrong bg-console-bg px-2.5 py-1.5 font-mono text-xs text-ink-primary focus:border-signal-amber focus:outline-none"
          >
            {filteredDocs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.doc_code} — {d.mission}
              </option>
            ))}
          </select>

          <button
            type="button"
            disabled={!selectedDoc || reconstructMutation.isPending}
            onClick={() => selectedDoc && reconstructMutation.mutate(selectedDoc.id)}
            className="inline-flex items-center gap-1.5 rounded border border-signal-amber bg-signal-amber px-3 py-1.5 font-mono text-xs font-semibold uppercase tracking-wide text-console-base hover:bg-signal-amber/90 disabled:opacity-40"
          >
            <Play className="h-3.5 w-3.5" />
            {reconstructMutation.isPending
              ? "Reconstructing..."
              : "Reconstruct Failure Chain"}
          </button>
        </div>

        {/* Edge Separation Controls */}
        <div className="flex items-center gap-1.5 font-mono text-[11px]">
          <span className="mr-1 text-ink-muted">EDGES:</span>
          {(["all", "causal", "chronology"] as EdgeFilter[]).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setEdgeFilter(f)}
              className={`rounded border px-2 py-1 uppercase ${
                edgeFilter === f
                  ? "border-signal-amber bg-signal-amberDim text-signal-amber"
                  : "border-console-border text-ink-secondary hover:text-ink-primary"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {reconstructMutation.isError && (
        <div className="border-b border-status-conflict/40 bg-status-conflict/10 px-4 py-2 font-mono text-xs text-status-conflict">
          Reconstruction failed: {(reconstructMutation.error as Error).message}
        </div>
      )}

      {/* Main Split: React Flow Canvas (Left) + Event Inspector / PDF Viewer (Right) */}
      <div className="grid min-h-0 flex-1 grid-cols-12 overflow-hidden">
        <div
          role="region"
          aria-label="Failure Chain Reconstruction Graph"
          className="relative col-span-12 h-full border-r border-console-border lg:col-span-7"
        >
          {/* Legend Bar */}
          <div className="pointer-events-none absolute left-3 top-3 z-10 flex flex-wrap gap-2 rounded border border-console-border bg-console-surface/95 px-2.5 py-1.5 font-mono text-[10px] text-ink-secondary">
            <span>TOP LANE: Chronological Timeline</span>
            <span>·</span>
            <span>LOWER LANE: Root / Contributing Causes</span>
            <span>·</span>
            <span className="text-status-verified">SOLID = Verified</span>
            <span>·</span>
            <span className="text-signal-amber">DASHED = Unverified / Chronology</span>
          </div>

          {events.length === 0 && !eventsQuery.isLoading ? (
            <div className="flex h-full flex-col items-center justify-center p-8 text-center">
              <GitBranch className="h-9 w-9 text-console-borderStrong" />
              <h3 className="mt-3 text-sm font-semibold text-ink-primary">
                No Failure Chain Reconstructed Yet
              </h3>
              <p className="mt-1.5 max-w-md text-xs leading-relaxed text-ink-secondary">
                Select a mission report above and click{" "}
                <span className="font-mono text-signal-amber">
                  Reconstruct Failure Chain
                </span>{" "}
                to extract events and causal/chronological relationships directly
                from indexed report chunks. Nothing is hardcoded or pre-seeded.
              </p>
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              fitView
              onNodeClick={(_ev, node) => {
                const payload = (node.data as FailureNodeData).event;
                setSelectedEvent(payload);
                setInspectorTab("details");
              }}
              className="bg-console-bg"
            >
              <Background color="#222B3A" gap={20} />
              <Controls className="!border-console-border !bg-console-surface !text-ink-primary" />
            </ReactFlow>
          )}
        </div>

        {/* Right Panel: Node Inspector OR Live PDF Citation Viewer */}
        <div className="col-span-12 flex h-full flex-col overflow-hidden bg-console-surface lg:col-span-5">
          <div className="flex items-center justify-between border-b border-console-border px-4 py-2">
            <div className="flex gap-2 font-mono text-[11px]">
              <button
                type="button"
                onClick={() => setInspectorTab("details")}
                className={`rounded border px-2.5 py-1 uppercase ${
                  inspectorTab === "details"
                    ? "border-signal-amber bg-signal-amberDim text-signal-amber"
                    : "border-console-border text-ink-secondary"
                }`}
              >
                Event Inspector
              </button>
              <button
                type="button"
                onClick={() => setInspectorTab("pdf")}
                className={`rounded border px-2.5 py-1 uppercase ${
                  inspectorTab === "pdf"
                    ? "border-signal-amber bg-signal-amberDim text-signal-amber"
                    : "border-console-border text-ink-secondary"
                }`}
              >
                PDF Evidence
              </button>
            </div>
            {selectedEvent && (
              <span className="font-mono text-[10px] text-ink-muted">
                {selectedEvent.doc_code} · p.{selectedEvent.page_number}
              </span>
            )}
          </div>

          {inspectorTab === "pdf" ? (
            <div className="min-h-0 flex-1 overflow-hidden">
              <CitationViewer citation={pdfCitation} />
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
              {!selectedEvent ? (
                <div className="flex flex-1 flex-col items-center justify-center text-center text-ink-muted">
                  <AlertTriangle className="h-6 w-6 text-console-borderStrong" />
                  <p className="mt-2 font-mono text-xs">
                    Click any node in the failure chain graph to inspect its
                    explanation, evidence quote, and PDF source.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      {selectedBadge && (
                        <span
                          className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase ${selectedBadge.tone}`}
                        >
                          {selectedBadge.label}
                        </span>
                      )}
                      <span
                        className={`rounded border px-2 py-0.5 font-mono text-[10px] uppercase ${
                          selectedEvent.verification_status === "verified"
                            ? "border-status-verified/40 bg-status-verified/10 text-status-verified"
                            : "border-dashed border-signal-amber/60 text-signal-amber"
                        }`}
                      >
                        {selectedEvent.verification_status === "verified"
                          ? "Evidence Verified"
                          : "Unverified / Pending"}
                      </span>
                    </div>

                    <h3 className="mt-2 text-base font-semibold text-ink-primary">
                      {selectedEvent.title}
                    </h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-ink-secondary">
                      {selectedEvent.description}
                    </p>
                  </div>

                  {/* Evidence Quote & Open PDF Button */}
                  <div className="rounded border border-console-border bg-console-bg p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-signal-amber">
                        PRIMARY EVIDENCE QUOTE · {selectedEvent.section}
                      </span>
                      <button
                        type="button"
                        onClick={() => openPdfForEvent(selectedEvent)}
                        className="inline-flex items-center gap-1.5 rounded border border-signal-amber bg-signal-amber px-2.5 py-1 font-mono text-[11px] font-semibold text-console-base hover:bg-signal-amber/90"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        Open PDF at page {selectedEvent.page_number}
                      </button>
                    </div>
                    <p className="mt-2 font-serif text-[13.5px] italic leading-relaxed text-ink-primary">
                      “{selectedEvent.evidence_text}”
                    </p>
                  </div>

                  {/* Ask Follow-Up by Voice or Text */}
                  <div className="rounded border border-console-border bg-console-bg p-3">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                      ASK FOLLOW-UP ON THIS EVENT (TEXT OR VOICE)
                    </span>
                    <form
                      onSubmit={handleFollowUpSubmit}
                      className="mt-2 flex items-center gap-2"
                    >
                      <input
                        type="text"
                        value={followUpInput}
                        onChange={(e) => setFollowUpInput(e.target.value)}
                        placeholder="Ask about this event or corrective action..."
                        className="flex-1 rounded border border-console-borderStrong bg-console-surface px-2.5 py-1.5 text-xs text-ink-primary placeholder:text-ink-muted focus:border-signal-amber focus:outline-none"
                      />
                      <button
                        type="button"
                        onMouseDown={voice.startPushToTalk}
                        onMouseUp={voice.stopPushToTalk}
                        title="Hold to ask by voice"
                        className={`rounded border px-2 py-1.5 font-mono text-xs ${
                          voice.voiceState === "listening"
                            ? "border-signal-amber bg-signal-amber text-console-base"
                            : "border-console-borderStrong bg-console-surface text-ink-primary"
                        }`}
                      >
                        <Mic className="h-3.5 w-3.5" />
                      </button>
                      {voice.voiceState === "speaking" && (
                        <button
                          type="button"
                          onClick={voice.interrupt}
                          title="Interrupt voice"
                          className="rounded border border-status-conflict/60 px-2 py-1.5 text-status-conflict"
                        >
                          <Square className="h-3.5 w-3.5" />
                        </button>
                      )}
                      <button
                        type="submit"
                        disabled={
                          followUpMutation.isPending ||
                          followUpInput.trim().length < 2
                        }
                        className="inline-flex items-center gap-1 rounded border border-signal-amber bg-signal-amber px-2.5 py-1.5 font-mono text-xs font-semibold text-console-base disabled:opacity-40"
                      >
                        <Send className="h-3 w-3" />
                      </button>
                    </form>

                    {followUpResponse && (
                      <div className="mt-3 space-y-2">
                        {followUpResponse.abstained ? (
                          <p className="font-mono text-xs text-ink-secondary">
                            {followUpResponse.answer}
                          </p>
                        ) : (
                          followUpResponse.claims.map((cl, i) => (
                            <ClaimBlock
                              key={i}
                              claim={cl}
                              onSelectCitation={(cit) => {
                                setPdfCitation(cit);
                                setInspectorTab("pdf");
                              }}
                            />
                          ))
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

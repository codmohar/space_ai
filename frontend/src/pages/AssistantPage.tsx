import { type FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, RotateCcw, Send } from "lucide-react";
import { api, type CitationOut } from "../api/client";
import { ClaimBlock } from "../components/chat/ClaimBlock";
import { ConfidenceMeter } from "../components/chat/ConfidenceMeter";
import { SplitPane } from "../components/layout/SplitPane";
import { CitationViewer } from "../components/viewer/CitationViewer";
import { useWorkspaceStore } from "../stores/workspaceStore";

const SUGGESTED_QUERIES = [
  "What was the root cause of the Mars Climate Orbiter loss?",
  "What triggered the Apollo 13 oxygen tank No. 2 failure?",
  "What was the most probable cause of the Mars Polar Lander failure?",
  "What caused the James Webb Space Telescope mirror test failure?", // Unanswerable test query
];

export function AssistantPage() {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const {
    selectedMission,
    setSelectedMission,
    conversationId,
    setConversationId,
    turns,
    addTurn,
    clearTurns,
    activeCitation,
    setActiveCitation,
    splitRatio,
    setSplitRatio,
  } = useWorkspaceStore();

  const { data: docs } = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
  });

  const missions = Array.from(new Set((docs || []).map((d) => d.mission))).sort();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        e.key === "/" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
      ) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const chatMutation = useMutation({
    mutationFn: (query: string) =>
      api.chat({
        query,
        conversation_id: conversationId,
        mission: selectedMission || null,
      }),
    onSuccess: (data) => {
      setConversationId(data.conversation_id);
      addTurn({
        id: data.message_id,
        role: "assistant",
        response: data,
      });
      if (data.citations.length > 0) {
        setActiveCitation(data.citations[0]);
      }
    },
    onError: (err: Error) => {
      addTurn({
        id: crypto.randomUUID(),
        role: "assistant",
        error: err.message,
      });
    },
  });

  const submitQuery = (q: string) => {
    const trimmed = q.trim();
    if (!trimmed || chatMutation.isPending) return;
    addTurn({
      id: crypto.randomUUID(),
      role: "user",
      query: trimmed,
    });
    setInput("");
    chatMutation.mutate(trimmed);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submitQuery(input);
  };

  const handleSelectCitation = (cit: CitationOut) => {
    setActiveCitation(cit);
  };

  const assistantPane = (
    <div className="flex h-full flex-col bg-console-bg">
      {/* Scope & Reset Toolbar */}
      <div className="flex items-center justify-between border-b border-console-border bg-console-surface px-4 py-2">
        <div className="flex items-center gap-2">
          <label
            htmlFor="mission-scope"
            className="font-mono text-[10px] uppercase tracking-wider text-ink-muted"
          >
            MISSION SCOPE
          </label>
          <select
            id="mission-scope"
            value={selectedMission}
            onChange={(e) => setSelectedMission(e.target.value)}
            className="rounded border border-console-borderStrong bg-console-bg px-2 py-1 font-mono text-xs text-ink-primary focus:border-signal-amber focus:outline-none"
          >
            <option value="">All Seeded Reports</option>
            {missions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          onClick={clearTurns}
          className="inline-flex items-center gap-1 rounded border border-console-border px-2 py-1 font-mono text-[11px] text-ink-secondary hover:border-console-borderStrong hover:text-ink-primary"
        >
          <RotateCcw className="h-3 w-3" />
          New Session
        </button>
      </div>

      {/* Scrollable Inquiry & Evidence Thread */}
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {turns.length === 0 && (
          <div className="rounded border border-console-border bg-console-surface p-4">
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal-amber">
              GROUNDED EVIDENCE WORKBENCH
            </span>
            <h3 className="mt-1 text-sm font-semibold text-ink-primary">
              Ask an engineering question across ingested mission reports
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-ink-secondary">
              Every claim is validated against stored chunks and page bounding boxes.
              Out-of-corpus queries automatically trigger abstention.
            </p>
            <div className="mt-3 grid grid-cols-1 gap-2">
              {SUGGESTED_QUERIES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => submitQuery(q)}
                  className="rounded border border-console-border bg-console-bg px-3 py-2 text-left font-mono text-xs text-ink-secondary transition-colors hover:border-signal-amber/60 hover:text-ink-primary"
                >
                  &gt; {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn) => {
          if (turn.role === "user") {
            return (
              <div
                key={turn.id}
                className="rounded border border-console-borderStrong bg-console-elevated px-3.5 py-2.5"
              >
                <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                  ENGINEER QUERY
                </span>
                <p className="mt-1 text-sm font-medium text-ink-primary">
                  {turn.query}
                </p>
              </div>
            );
          }

          if (turn.error) {
            return (
              <div
                key={turn.id}
                className="rounded border border-status-conflict/50 bg-status-conflict/10 px-3.5 py-3 font-mono text-xs text-status-conflict"
              >
                {turn.error}
              </div>
            );
          }

          const res = turn.response!;
          return (
            <div key={turn.id} className="space-y-3">
              <ConfidenceMeter
                category={res.confidence}
                score={res.confidence_score}
                stairLevel={res.stair_level}
              />

              {res.abstained ? (
                <div className="rounded border border-status-insufficient/40 bg-console-surface p-3.5">
                  <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-ink-secondary">
                    <AlertTriangle className="h-4 w-4 text-signal-amber" />
                    ABSTENTION — INSUFFICIENT REPORT EVIDENCE
                  </div>
                  <p className="mt-2 font-mono text-xs text-ink-primary">
                    {res.answer}
                  </p>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {res.claims.map((claim, idx) => (
                    <ClaimBlock
                      key={`${turn.id}-claim-${idx}`}
                      claim={claim}
                      activeChunkId={activeCitation?.chunk_id}
                      onSelectCitation={handleSelectCitation}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {chatMutation.isPending && (
          <div className="space-y-2 rounded border border-console-border bg-console-surface p-4">
            <div className="h-3 w-40 animate-pulse rounded bg-console-elevated" />
            <div className="h-14 w-full animate-pulse rounded bg-console-elevated" />
            <span className="block font-mono text-[11px] text-ink-muted">
              Running hybrid retrieval (dense + BM25 + RRF + reranker) & citation validation...
            </span>
          </div>
        )}
      </div>

      {/* Query Input Bar */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-console-border bg-console-surface p-3"
      >
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Query root causes, subsystems, corrective actions... (press / to focus)"
            className="flex-1 rounded border border-console-borderStrong bg-console-bg px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:border-signal-amber focus:outline-none"
          />
          <button
            type="submit"
            disabled={chatMutation.isPending || input.trim().length < 2}
            className="inline-flex items-center gap-1.5 rounded border border-signal-amber bg-signal-amber px-4 py-2 text-xs font-semibold uppercase tracking-wide text-console-base hover:bg-signal-amber/90 disabled:opacity-40"
          >
            <Send className="h-3.5 w-3.5" />
            Query
          </button>
        </div>
      </form>
    </div>
  );

  return (
    <SplitPane
      ratio={splitRatio}
      onRatioChange={setSplitRatio}
      left={assistantPane}
      right={<CitationViewer citation={activeCitation} />}
    />
  );
}

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Download,
  Mic,
  RotateCcw,
  Send,
} from "lucide-react";
import { api, type ChatResponse, type CitationOut } from "../api/client";
import { CitationChip } from "../components/chat/CitationChip";
import { ClaimBlock } from "../components/chat/ClaimBlock";
import { ConfidenceMeter } from "../components/chat/ConfidenceMeter";
import { SplitPane } from "../components/layout/SplitPane";
import { CitationViewer } from "../components/viewer/CitationViewer";
import { VoiceConsoleBar } from "../components/voice/VoiceConsoleBar";
import { useVoiceAssistant } from "../hooks/useVoiceAssistant";
import { useWorkspaceStore } from "../stores/workspaceStore";

const SUGGESTED_QUERIES = [
  "What was the root cause of the Mars Climate Orbiter loss?",
  "What triggered the Apollo 13 oxygen tank No. 2 failure?",
  "What was the most probable cause of the Mars Polar Lander failure?",
  "What caused the James Webb Space Telescope mirror test failure?",
];

export function AssistantPage() {
  const [input, setInput] = useState("");
  const [openDiagnosticsTurnId, setOpenDiagnosticsTurnId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const {
    selectedMission,
    setSelectedMission,
    selectorMode,
    setSelectorMode,
    conversationId,
    setConversationId,
    turns,
    addTurn,
    clearTurns,
    activeCitation,
    setActiveCitation,
    setHighlightedSections,
    setActiveRoute,
    splitRatio,
    setSplitRatio,
  } = useWorkspaceStore();

  const { data: docs } = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
  });

  const missions = Array.from(new Set((docs || []).map((d) => d.mission))).sort();

  const applyChatResponse = useCallback(
    (data: ChatResponse) => {
      setConversationId(data.conversation_id);
      addTurn({
        id: data.message_id,
        role: "assistant",
        response: data,
      });
      if (data.citations.length > 0) {
        setActiveCitation(data.citations[0]);
      }
      const allSecIds = Array.from(
        new Set([
          ...(data.used_section_ids || []),
          ...(data.selected_sections || []).map((s) => s.section_id),
        ])
      );
      const docId =
        data.citations[0]?.document_id ||
        data.selected_sections[0]?.document_id ||
        null;
      setHighlightedSections(allSecIds, docId);
    },
    [addTurn, setActiveCitation, setConversationId, setHighlightedSections]
  );

  const voice = useVoiceAssistant({
    conversationId,
    mission: selectedMission,
    selectorMode,
    onTranscript: (text) => {
      const clean = text.trim();
      if (!clean) return;
      setInput(clean);
      addTurn({
        id: crypto.randomUUID(),
        role: "user",
        query: clean,
      });
    },
    onAnswer: (res) => {
      setInput("");
      applyChatResponse(res);
    },
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        e.key === "/" &&
        document.activeElement?.tagName !== "INPUT" &&
        document.activeElement?.tagName !== "TEXTAREA"
      ) {
        e.preventDefault();
        inputRef.current?.focus();
      } else if (e.key === "Escape") {
        voice.interrupt();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [voice]);

  const chatMutation = useMutation({
    mutationFn: (query: string) =>
      api.chat({
        query,
        conversation_id: conversationId,
        mission: selectedMission || null,
        selector_mode: selectorMode,
      }),
    onSuccess: applyChatResponse,
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
    if (cit.section_id) {
      setHighlightedSections([cit.section_id], cit.document_id);
    }
  };

  const inspectSectionInToc = (sectionIds: string[], documentId: string) => {
    setHighlightedSections(sectionIds, documentId);
    setActiveRoute("documents");
  };

  const handleDownloadSummaryPdf = () => {
    if (turns.length === 0) return;
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      window.print();
      return;
    }

    const sessionDate = new Date().toLocaleString();
    const missionScopeLabel = selectedMission || "All Mission Reports (Global Corpus)";

    const turnsHtml = turns
      .map((t, idx) => {
        const resp = t.response;
        const confidence = resp?.confidence || "STRONG";
        const roleBadge =
          t.role === "user"
            ? `<div style="font-size: 11px; font-weight: bold; color: #4a5568; margin-bottom: 4px;">[INQUIRY ${idx + 1}] ENGINEER QUERY</div>`
            : `<div style="font-size: 11px; font-weight: bold; color: #b45309; margin-bottom: 4px;">[RESPONSE ${idx + 1}] MISSIONWISE AI // CONFIDENCE: ${confidence.toUpperCase()}</div>`;

        const content =
          t.role === "user"
            ? `<div style="font-size: 14px; font-weight: 600; color: #1a202c; margin-bottom: 12px; background: #f7fafc; padding: 10px; border-left: 3px solid #718096;">${t.query || ""}</div>`
            : `
              <div style="font-size: 13px; line-height: 1.6; color: #2d3748; margin-bottom: 12px;">${resp?.answer || t.error || ""}</div>
              ${
                resp?.claims && resp.claims.length > 0
                  ? `
                    <div style="margin-top: 10px;">
                      <div style="font-size: 11px; font-weight: bold; text-transform: uppercase; color: #718096; margin-bottom: 6px;">Ground Truth Verified Claims:</div>
                      <ul style="margin: 0; padding-left: 18px; font-size: 12px; color: #4a5568;">
                        ${resp.claims
                          .map(
                            (c) => `
                              <li style="margin-bottom: 6px;">
                                <span>${c.claim_text}</span>
                                <span style="font-size: 10px; font-family: monospace; background: #edf2f7; padding: 2px 5px; border-radius: 3px; margin-left: 6px;">
                                  [${c.evidence_classification}]
                                </span>
                              </li>`
                          )
                          .join("")}
                      </ul>
                    </div>
                  `
                  : ""
              }
              ${
                resp?.citations && resp.citations.length > 0
                  ? `
                    <div style="margin-top: 10px; font-size: 11px; font-family: monospace; color: #4a5568; background: #f7fafc; padding: 8px; border: 1px solid #e2e8f0; border-radius: 4px;">
                      <div style="font-weight: bold; margin-bottom: 4px; color: #2b6cb0;">CITED ARCHIVAL SOURCES:</div>
                      ${resp.citations
                        .map(
                          (cit) => `
                            <div style="margin-bottom: 3px;">
                              • <strong>${cit.doc_code}</strong> · Page ${cit.page_number} · Section: ${cit.section}
                              <br/><span style="color: #718096; font-style: italic;">"${cit.quote ? cit.quote.substring(0, 140) + '...' : ''}"</span>
                            </div>`
                        )
                        .join("")}
                    </div>
                  `
                  : ""
              }
            `;

        return `
          <div style="margin-bottom: 24px; padding-bottom: 18px; border-bottom: 1px solid #e2e8f0;">
            ${roleBadge}
            ${content}
          </div>
        `;
      })
      .join("");

    const reportHtml = `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8" />
          <title>MISSIONWISE AI - Research Brief (${sessionDate})</title>
          <style>
            @page { size: A4; margin: 20mm; }
            body {
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
              color: #1a202c;
              line-height: 1.5;
              padding: 20px;
            }
            .header-table { width: 100%; border-bottom: 2px solid #b45309; padding-bottom: 12px; margin-bottom: 20px; }
            .header-title { font-size: 20px; font-weight: 800; letter-spacing: 0.05em; color: #1a202c; }
            .header-sub { font-size: 12px; font-family: monospace; color: #718096; margin-top: 4px; }
            .meta-box { font-size: 11px; font-family: monospace; background: #edf2f7; padding: 8px 12px; border-radius: 4px; margin-bottom: 24px; }
            .disclaimer { margin-top: 30px; padding-top: 12px; border-top: 1px solid #cbd5e0; font-size: 10px; color: #718096; text-align: center; font-style: italic; }
            @media print {
              body { padding: 0; }
              button { display: none; }
            }
          </style>
        </head>
        <body>
          <div style="display: flex; justify-content: flex-end; margin-bottom: 12px;">
            <button onclick="window.print()" style="cursor: pointer; background: #b45309; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; font-size: 12px; font-weight: 600;">Print / Save as PDF</button>
          </div>
          <table class="header-table">
            <tr>
              <td>
                <div class="header-title">MISSIONWISE AI // FLIGHT-OPS ENGINEERING BRIEF</div>
                <div class="header-sub">SPACE MISSION LESSONS-LEARNED INTELLIGENCE PLATFORM (AVISHKAR 2K26)</div>
              </td>
            </tr>
          </table>

          <div class="meta-box">
            <strong>CORPUS SCOPE:</strong> ${missionScopeLabel} &nbsp;|&nbsp;
            <strong>SESSION DATE:</strong> ${sessionDate} &nbsp;|&nbsp;
            <strong>SESSION ID:</strong> ${conversationId || "ad-hoc-research"} &nbsp;|&nbsp;
            <strong>TOTAL INQUIRIES:</strong> ${turns.filter((t) => t.role === "user").length}
          </div>

          <div class="content">
            ${turnsHtml}
          </div>

          <div class="disclaimer">
            CONFIDENTIALITY & DISCLAIMER: MISSIONWISE AI is an engineering knowledge-support tool, not a certifier of spacecraft safety.
            All factual claims are grounded with citations in public space agency technical reports (NASA/ISRO/ESA).
          </div>
        </body>
      </html>
    `;

    printWindow.document.open();
    printWindow.document.write(reportHtml);
    printWindow.document.close();
    setTimeout(() => {
      printWindow.focus();
    }, 250);
  };

  const assistantPane = (
    <div className="flex h-full flex-col bg-console-bg">
      {/* Scope, STAIR Selector Mode & Reset Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-console-border bg-console-surface px-4 py-2">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label
              htmlFor="mission-scope"
              className="font-mono text-[10px] uppercase tracking-wider text-ink-muted"
            >
              MISSION
            </label>
            <select
              id="mission-scope"
              value={selectedMission}
              onChange={(e) => {
                setSelectedMission(e.target.value);
                setConversationId(null);
              }}
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

          <div className="flex items-center gap-2">
            <label
              htmlFor="stair-selector"
              className="font-mono text-[10px] uppercase tracking-wider text-ink-muted"
            >
              TOC SELECTOR
            </label>
            <select
              id="stair-selector"
              value={selectorMode}
              onChange={(e) => setSelectorMode(e.target.value)}
              className="rounded border border-console-borderStrong bg-console-bg px-2 py-1 font-mono text-xs text-ink-primary focus:border-signal-amber focus:outline-none"
            >
              <option value="auto">Auto (L2 STAIR / BM25-ToC)</option>
              <option value="stair_l2">L2 STAIR-Inspired (ToC-&gt;Leaf)</option>
              <option value="bm25_toc">L1 BM25-over-ToC</option>
              <option value="l1_passthrough">L1 Full-Doc Hybrid</option>
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {turns.length > 0 && (
            <button
              type="button"
              onClick={handleDownloadSummaryPdf}
              className="inline-flex items-center gap-1.5 rounded border border-signal-amber/60 bg-signal-amberDim/20 px-2.5 py-1 font-mono text-[11px] font-semibold text-signal-amber hover:bg-signal-amberDim/40"
              title="Download/Print formatted research session summary as PDF"
            >
              <Download className="h-3.5 w-3.5" />
              Download Summary (PDF)
            </button>
          )}

          <button
            type="button"
            onClick={() => {
              voice.interrupt();
              setConversationId(null);
              clearTurns();
            }}
            className="inline-flex items-center gap-1 rounded border border-console-border px-2 py-1 font-mono text-[11px] text-ink-secondary hover:border-console-borderStrong hover:text-ink-primary"
          >
            <RotateCcw className="h-3 w-3" />
            New Session
          </button>
        </div>
      </div>

      {/* Flight-Ops Voice Console Bar (PTT + Hands-Free + Captions + Interrupt) */}
      <VoiceConsoleBar
        mode={voice.mode}
        voiceState={voice.voiceState}
        liveTranscript={voice.liveTranscript}
        spokenCaption={voice.spokenCaption}
        engineBadge={voice.engineBadge}
        waveformLevels={voice.waveformLevels}
        errorMsg={voice.errorMsg}
        onPttStart={voice.startPushToTalk}
        onPttEnd={voice.stopPushToTalk}
        onToggleHandsFree={voice.toggleHandsFree}
        onInterrupt={voice.interrupt}
      />

      {/* Scrollable Inquiry & Evidence Thread */}
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {turns.length === 0 && (
          <div className="rounded border border-console-border bg-console-surface p-4">
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal-amber">
              GROUNDED EVIDENCE WORKBENCH (TEXT + VOICE)
            </span>
            <h3 className="mt-1 text-sm font-semibold text-ink-primary">
              Ask an engineering question by typing or using the Voice Console
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-ink-secondary">
              Voice and text share the exact same retrieval, follow-up query rewriter,
              and pre-response citation validator. Spoken answers use concise radio style
              with identical grounded claims.
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
          const uniqueUsedSections = new Map<
            string,
            { sectionId: string; documentId: string; label: string }
          >();
          for (const sec of res.selected_sections || []) {
            uniqueUsedSections.set(sec.section_id, {
              sectionId: sec.section_id,
              documentId: sec.document_id,
              label: `${sec.doc_code} · §${sec.section_path} ${sec.title} (p.${sec.page_start})`,
            });
          }
          for (const cit of res.citations || []) {
            if (cit.section_id && !uniqueUsedSections.has(cit.section_id)) {
              uniqueUsedSections.set(cit.section_id, {
                sectionId: cit.section_id,
                documentId: cit.document_id,
                label: `${cit.doc_code} · ${cit.section} (p.${cit.page_number})`,
              });
            }
          }

          const isDiagOpen = openDiagnosticsTurnId === turn.id;
          const diag = res.diagnostics;

          return (
            <div key={turn.id} className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <ConfidenceMeter
                  category={res.confidence}
                  score={res.confidence_score}
                  stairLevel={`${res.stair_level} (${res.selector_name})`}
                />
                <button
                  type="button"
                  onClick={() => setOpenDiagnosticsTurnId(isDiagOpen ? null : turn.id)}
                  className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 font-mono text-[11px] transition-colors ${
                    isDiagOpen
                      ? "border-signal-amber bg-signal-amber text-console-base font-semibold"
                      : "border-console-borderStrong bg-console-surface text-ink-secondary hover:border-signal-amber hover:text-ink-primary"
                  }`}
                >
                  <Activity className="h-3 w-3" />
                  Why this answer? (Diagnostics)
                  {isDiagOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                </button>
              </div>

              {/* Retrieval Diagnostics Drawer */}
              {isDiagOpen && (
                <div className="rounded border border-signal-amber/40 bg-console-elevated p-3.5 space-y-3 font-mono text-xs">
                  <div className="flex items-center justify-between border-b border-console-border pb-2 text-[11px] uppercase tracking-wider text-signal-amber">
                    <span>RETRIEVAL & STAIR PIPELINE TELEMETRY</span>
                    <span>STAGE LATENCIES (TOTAL: {diag?.total_ms?.toFixed(1) ?? "--"} ms)</span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
                    <div className="rounded border border-console-border bg-console-surface p-2">
                      <div className="text-ink-muted">DOCS CONSIDERED</div>
                      <div className="text-sm font-semibold text-ink-primary">{diag?.documents_considered ?? 1}</div>
                    </div>
                    <div className="rounded border border-console-border bg-console-surface p-2">
                      <div className="text-ink-muted">TOCS SCANNED</div>
                      <div className="text-sm font-semibold text-ink-primary">{diag?.tocs_scanned ?? 1}</div>
                    </div>
                    <div className="rounded border border-console-border bg-console-surface p-2">
                      <div className="text-ink-muted">SELECTOR MODE</div>
                      <div className="truncate text-xs font-semibold text-signal-amber">{res.selector_name}</div>
                    </div>
                    <div className="rounded border border-console-border bg-console-surface p-2">
                      <div className="text-ink-muted">LEAF SECTIONS</div>
                      <div className="text-sm font-semibold text-ink-primary">{diag?.selected_sections_count ?? res.selected_sections.length}</div>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-[10px] sm:grid-cols-6">
                    <div className="rounded border border-console-border bg-console-surface p-1.5">
                      <span className="text-ink-muted">DENSE POOL</span>
                      <div className="text-ink-primary font-semibold">{diag?.dense_count ?? "--"}</div>
                    </div>
                    <div className="rounded border border-console-border bg-console-surface p-1.5">
                      <span className="text-ink-muted">BM25 POOL</span>
                      <div className="text-ink-primary font-semibold">{diag?.bm25_count ?? "--"}</div>
                    </div>
                    <div className="rounded border border-console-border bg-console-surface p-1.5">
                      <span className="text-ink-muted">RRF MERGED</span>
                      <div className="text-ink-primary font-semibold">{diag?.rrf_pool_count ?? "--"}</div>
                    </div>
                    <div className="rounded border border-console-border bg-console-surface p-1.5">
                      <span className="text-ink-muted">DENSE LATENCY</span>
                      <div className="text-ink-primary">{diag?.dense_ms?.toFixed(1) ?? "--"} ms</div>
                    </div>
                    <div className="rounded border border-console-border bg-console-surface p-1.5">
                      <span className="text-ink-muted">BM25 LATENCY</span>
                      <div className="text-ink-primary">{diag?.bm25_ms?.toFixed(1) ?? "--"} ms</div>
                    </div>
                    <div className="rounded border border-console-border bg-console-surface p-1.5">
                      <span className="text-ink-muted">RERANK LATENCY</span>
                      <div className="text-ink-primary">{diag?.rerank_ms?.toFixed(1) ?? "--"} ms</div>
                    </div>
                  </div>

                  {diag?.chunks && diag.chunks.length > 0 && (
                    <div className="overflow-x-auto">
                      <div className="mb-1 text-[10px] text-ink-muted uppercase">TOP RETRIEVED CHUNKS & CROSS-ENCODER RANKINGS:</div>
                      <table className="w-full text-left text-[10px] border border-console-border">
                        <thead className="bg-console-surface text-ink-muted">
                          <tr>
                            <th className="p-1">Doc Code</th>
                            <th className="p-1">Page</th>
                            <th className="p-1">Dense</th>
                            <th className="p-1">BM25</th>
                            <th className="p-1">RRF</th>
                            <th className="p-1">Rerank</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-console-border">
                          {diag.chunks.map((chk, cIdx) => (
                            <tr key={chk.chunk_id || cIdx} className="hover:bg-console-surface/50">
                              <td className="p-1 font-semibold text-signal-amber">{chk.doc_code}</td>
                              <td className="p-1">p.{chk.page}</td>
                              <td className="p-1">{chk.dense.toFixed(3)}</td>
                              <td className="p-1">{chk.bm25.toFixed(2)}</td>
                              <td className="p-1">{chk.rrf.toFixed(4)}</td>
                              <td className="p-1 font-semibold text-status-verified">{chk.rerank.toFixed(3)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {res.standalone_query && (
                <div className="rounded border border-console-border bg-console-surface px-3 py-1.5 font-mono text-[11px] text-ink-secondary">
                  <span className="mr-2 text-ink-muted">RESOLVED QUERY:</span>
                  {res.standalone_query}
                </div>
              )}

              {uniqueUsedSections.size > 0 && (
                <div className="rounded border border-signal-amber/35 bg-signal-amberDim/50 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-signal-amber">
                      <BookOpen className="h-3.5 w-3.5" />
                      SECTIONS USED FOR THIS ANSWER ({uniqueUsedSections.size})
                    </span>
                    <span className="font-mono text-[10px] text-ink-secondary">
                      Click to highlight in Document Explorer ToC Tree
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {Array.from(uniqueUsedSections.values()).map((sec) => {
                      const isCited = (res.used_section_ids || []).includes(sec.sectionId);
                      return (
                        <button
                          key={sec.sectionId}
                          type="button"
                          onClick={() =>
                            inspectSectionInToc([sec.sectionId], sec.documentId)
                          }
                          className={`rounded border px-2 py-0.5 font-mono text-[11px] transition-colors ${
                            isCited
                              ? "border-signal-amber bg-console-surface text-signal-amber hover:bg-signal-amber hover:text-console-base"
                              : "border-console-borderStrong bg-console-surface text-ink-secondary hover:border-signal-amber"
                          }`}
                        >
                          {sec.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

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
                <div className="space-y-3">
                  {/* Compact Direct Answer Card */}
                  <div className="rounded border border-console-borderStrong bg-console-surface p-4 shadow-sm">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="font-mono text-[10px] uppercase tracking-wider text-signal-amber font-semibold">
                        EXECUTIVE SUMMARY & DIRECT ANSWER
                      </span>
                      <span className="font-mono text-[10px] text-ink-muted">
                        GROUNDED ACROSS {res.citations.length} VERIFIED CITATIONS
                      </span>
                    </div>
                    <p className="text-[13.5px] leading-relaxed text-ink-primary font-medium">
                      {res.claims.length > 0 ? res.claims[0].claim_text : res.answer}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-1.5 border-t border-console-border/60 pt-2.5">
                      {res.citations.slice(0, 4).map((cit, idx) => (
                        <CitationChip
                          key={`exec-cit-${cit.chunk_id}-${idx}`}
                          citation={cit}
                          isActive={activeCitation?.chunk_id === cit.chunk_id}
                          onSelect={handleSelectCitation}
                        />
                      ))}
                    </div>
                  </div>

                  {/* Key Verified Evidence Claims */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between font-mono text-[10px] text-ink-muted uppercase tracking-wider px-1">
                      <span>KEY VERIFIED EVIDENCE CLAIMS ({res.claims.length})</span>
                      <span>CLICK CHIP TO INSPECT IN VIEWER</span>
                    </div>
                    {res.claims.map((claim, idx) => (
                      <ClaimBlock
                        key={`${turn.id}-claim-${idx}`}
                        claim={claim}
                        activeChunkId={activeCitation?.chunk_id}
                        onSelectCitation={handleSelectCitation}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {(chatMutation.isPending ||
          voice.voiceState === "thinking" ||
          voice.voiceState === "transcribing") && (
          <div className="space-y-2 rounded border border-console-border bg-console-surface p-4">
            <div className="h-3 w-40 animate-pulse rounded bg-console-elevated" />
            <div className="h-14 w-full animate-pulse rounded bg-console-elevated" />
            <span className="block font-mono text-[11px] text-ink-muted">
              {voice.voiceState === "transcribing"
                ? "Transcribing voice input via Sarvam AI STT..."
                : "Selecting ToC leaf sections, running hybrid retrieval & citation validation..."}
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
            placeholder="Query root causes, subsystems, follow-ups ('explain simpler')... (press / to focus)"
            className="flex-1 rounded border border-console-borderStrong bg-console-bg px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:border-signal-amber focus:outline-none"
          />
          <button
            type="button"
            onMouseDown={voice.startPushToTalk}
            onMouseUp={voice.stopPushToTalk}
            onTouchStart={voice.startPushToTalk}
            onTouchEnd={voice.stopPushToTalk}
            title="Hold to speak voice query (Sarvam AI)"
            className={`inline-flex items-center gap-1.5 rounded border px-3 py-2 text-xs font-semibold uppercase tracking-wide transition-colors ${
              voice.voiceState === "listening" && voice.mode === "ptt"
                ? "border-signal-amber bg-signal-amber text-console-base animate-pulse"
                : "border-console-borderStrong bg-console-bg text-ink-secondary hover:text-signal-amber hover:border-signal-amber"
            }`}
          >
            <Mic className="h-4 w-4" />
            <span className="hidden sm:inline">
              {voice.voiceState === "listening" ? "Listening..." : "Voice"}
            </span>
          </button>
          <button
            type="submit"
            disabled={
              chatMutation.isPending ||
              voice.voiceState === "thinking" ||
              voice.voiceState === "transcribing" ||
              input.trim().length < 2
            }
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

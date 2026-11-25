import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, ExternalLink, Eye } from "lucide-react";
import { api, type DocumentSummary } from "../api/client";
import { useWorkspaceStore } from "../stores/workspaceStore";

export function DocumentsPage() {
  const [selectedDoc, setSelectedDoc] = useState<DocumentSummary | null>(null);
  const setActiveCitation = useWorkspaceStore((s) => s.setActiveCitation);
  const setActiveRoute = useWorkspaceStore((s) => s.setActiveRoute);

  const { data: docs, isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
  });

  const { data: toc, isLoading: tocLoading } = useQuery({
    queryKey: ["document-toc", selectedDoc?.id],
    queryFn: () => api.getDocumentToc(selectedDoc!.id),
    enabled: Boolean(selectedDoc?.id),
  });

  const openDocumentInViewer = (doc: DocumentSummary, page = 1, section = "Document Start") => {
    setActiveCitation({
      document_id: doc.id,
      doc_code: doc.doc_code,
      document_title: doc.title,
      source_url: doc.source_url,
      licence: doc.licence,
      section,
      page_number: page,
      chunk_id: "",
      quote: "",
      bbox_json: [],
      verified: true,
    });
    setActiveRoute("assistant");
  };

  return (
    <div className="grid h-full grid-cols-12 overflow-hidden bg-console-bg">
      {/* Left: Document Corpus Table */}
      <div className="col-span-12 flex flex-col overflow-hidden border-r border-console-border lg:col-span-7">
        <div className="border-b border-console-border bg-console-surface px-5 py-3">
          <span className="font-mono text-[10px] uppercase tracking-widest text-signal-amber">
            PUBLIC MISSION ARCHIVE
          </span>
          <h2 className="mt-0.5 text-base font-semibold text-ink-primary">
            Mission Document Explorer & Provenance Registry
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="font-mono text-xs text-ink-muted">Loading ingested reports...</div>
          ) : (
            <div className="space-y-2.5">
              {(docs || []).map((doc) => {
                const isSelected = selectedDoc?.id === doc.id;
                return (
                  <div
                    key={doc.id}
                    onClick={() => setSelectedDoc(doc)}
                    className={`cursor-pointer rounded border p-3.5 transition-colors ${
                      isSelected
                        ? "border-signal-amber bg-console-elevated"
                        : "border-console-border bg-console-surface hover:border-console-borderStrong"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="rounded border border-signal-amber/40 bg-signal-amberDim px-1.5 py-0.5 font-mono text-[11px] text-signal-amber">
                            {doc.doc_code}
                          </span>
                          <span className="font-mono text-[11px] text-ink-muted">
                            {doc.org} · {doc.mission}
                          </span>
                        </div>
                        <h3 className="mt-1.5 text-sm font-semibold text-ink-primary">
                          {doc.title}
                        </h3>
                      </div>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          openDocumentInViewer(doc, 1);
                        }}
                        className="inline-flex shrink-0 items-center gap-1 rounded border border-console-borderStrong bg-console-bg px-2.5 py-1 font-mono text-[11px] text-ink-primary hover:border-signal-amber hover:text-signal-amber"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        Open PDF
                      </button>
                    </div>

                    <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-ink-secondary tabular-nums">
                      <span>{doc.page_count} pages</span>
                      <span>{doc.section_count} sections</span>
                      <span>{doc.chunk_count} chunks</span>
                      <span>Licence: {doc.licence}</span>
                      <a
                        href={doc.source_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-signal-amber hover:underline"
                      >
                        Source <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Right: Hierarchical L1 ToC Browser */}
      <div className="col-span-12 flex flex-col overflow-hidden bg-console-surface lg:col-span-5">
        <div className="border-b border-console-border px-4 py-3">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
            STAIR L1 HIERARCHICAL INDEX
          </span>
          <h3 className="mt-0.5 text-sm font-semibold text-ink-primary">
            {selectedDoc ? `${selectedDoc.doc_code} — Table of Contents` : "Select a report"}
          </h3>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {!selectedDoc && (
            <div className="flex h-full flex-col items-center justify-center text-center text-ink-muted">
              <BookOpen className="h-7 w-7 text-console-borderStrong" />
              <p className="mt-2 font-mono text-xs">
                Click any report on the left to inspect its indexed section hierarchy.
              </p>
            </div>
          )}
          {selectedDoc && tocLoading && (
            <p className="font-mono text-xs text-ink-muted">Loading section tree...</p>
          )}
          {selectedDoc && toc && (
            <div className="space-y-1">
              {toc.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => openDocumentInViewer(selectedDoc, node.page_start, node.title)}
                  style={{ paddingLeft: `${(node.level - 1) * 14 + 8}px` }}
                  className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs hover:bg-console-elevated"
                >
                  <span className="truncate text-ink-primary">
                    <span className="mr-2 font-mono text-[11px] text-signal-amber">
                      §{node.section_path}
                    </span>
                    {node.title}
                  </span>
                  <span className="ml-2 shrink-0 font-mono text-[11px] tabular-nums text-ink-muted">
                    p.{node.page_start}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Eye,
  Sparkles,
} from "lucide-react";
import {
  api,
  type DocumentSectionNode,
  type DocumentSummary,
} from "../api/client";
import { useWorkspaceStore } from "../stores/workspaceStore";

interface TreeNode extends DocumentSectionNode {
  children: TreeNode[];
  hasHighlightedDescendant: boolean;
}

function buildSectionTree(
  nodes: DocumentSectionNode[],
  highlightedSet: Set<string>
): TreeNode[] {
  const map = new Map<string, TreeNode>();
  for (const n of nodes) {
    map.set(n.id, {
      ...n,
      children: [],
      hasHighlightedDescendant: highlightedSet.has(n.id),
    });
  }

  const roots: TreeNode[] = [];
  for (const n of nodes) {
    const tn = map.get(n.id)!;
    if (n.parent_id && map.has(n.parent_id)) {
      map.get(n.parent_id)!.children.push(tn);
    } else {
      roots.push(tn);
    }
  }

  const markDescendants = (node: TreeNode): boolean => {
    let hit = highlightedSet.has(node.id);
    for (const child of node.children) {
      if (markDescendants(child)) {
        hit = true;
      }
    }
    node.hasHighlightedDescendant = hit;
    return hit;
  };
  for (const r of roots) {
    markDescendants(r);
  }

  return roots;
}

export function DocumentsPage() {
  const [selectedDoc, setSelectedDoc] = useState<DocumentSummary | null>(null);
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({});
  const {
    highlightedSectionIds,
    highlightedDocumentId,
    setHighlightedSections,
    setActiveCitation,
    setActiveRoute,
  } = useWorkspaceStore();

  const highlightedSet = useMemo(
    () => new Set(highlightedSectionIds),
    [highlightedSectionIds]
  );

  const { data: docs, isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
  });

  // Auto-select the document referenced by the last Research Assistant answer
  useEffect(() => {
    if (!docs || docs.length === 0) return;
    if (highlightedDocumentId) {
      const match = docs.find((d) => d.id === highlightedDocumentId);
      if (match) {
        setSelectedDoc(match);
        return;
      }
    }
    if (!selectedDoc) {
      setSelectedDoc(docs[0]);
    }
  }, [docs, highlightedDocumentId, selectedDoc]);

  const { data: toc, isLoading: tocLoading } = useQuery({
    queryKey: ["document-toc", selectedDoc?.id],
    queryFn: () => api.getDocumentToc(selectedDoc!.id),
    enabled: Boolean(selectedDoc?.id),
  });

  const treeRoots = useMemo(
    () => buildSectionTree(toc || [], highlightedSet),
    [toc, highlightedSet]
  );

  // Auto-expand ancestors of highlighted sections
  useEffect(() => {
    if (!toc || highlightedSectionIds.length === 0) return;
    const nextExpanded: Record<string, boolean> = {};
    const expandTree = (node: TreeNode) => {
      if (node.hasHighlightedDescendant || node.level === 1) {
        nextExpanded[node.id] = true;
      }
      node.children.forEach(expandTree);
    };
    treeRoots.forEach(expandTree);
    setExpandedIds((prev) => ({ ...prev, ...nextExpanded }));
  }, [toc, treeRoots, highlightedSectionIds]);

  const toggleNode = (id: string) => {
    setExpandedIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const openDocumentInViewer = (
    doc: DocumentSummary,
    page = 1,
    section = "Document Start"
  ) => {
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

  const renderTreeNode = (node: TreeNode, depth = 0) => {
    const hasChildren = node.children.length > 0;
    const isExpanded = expandedIds[node.id] ?? depth === 0;
    const isHighlighted = highlightedSet.has(node.id);

    return (
      <div key={node.id}>
        <div
          style={{ paddingLeft: `${depth * 14 + 6}px` }}
          className={`flex items-center justify-between gap-2 rounded border px-2 py-1.5 text-xs transition-colors ${
            isHighlighted
              ? "border-signal-amber bg-signal-amberDim text-ink-primary"
              : "border-transparent hover:bg-console-elevated"
          }`}
        >
          <div className="flex min-w-0 flex-1 items-center gap-1.5">
            {hasChildren ? (
              <button
                type="button"
                onClick={() => toggleNode(node.id)}
                aria-label={isExpanded ? "Collapse section" : "Expand section"}
                className="rounded p-0.5 text-ink-muted hover:text-ink-primary"
              >
                {isExpanded ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
              </button>
            ) : (
              <span className="inline-block w-4 shrink-0 text-center font-mono text-[10px] text-ink-muted">
                ·
              </span>
            )}

            <button
              type="button"
              onClick={() =>
                selectedDoc &&
                openDocumentInViewer(selectedDoc, node.page_start, node.title)
              }
              className="flex min-w-0 flex-1 items-center gap-2 text-left"
            >
              <span className="shrink-0 font-mono text-[11px] text-signal-amber">
                §{node.section_path}
              </span>
              <span className="truncate text-ink-primary">{node.title}</span>
              {node.is_leaf && (
                <span className="shrink-0 rounded border border-console-borderStrong px-1 py-0.2 font-mono text-[9px] uppercase text-ink-muted">
                  LEAF
                </span>
              )}
              {isHighlighted && (
                <span className="shrink-0 rounded border border-signal-amber bg-signal-amber px-1.5 py-0.2 font-mono text-[9px] font-semibold uppercase text-console-base">
                  USED FOR ANSWER
                </span>
              )}
            </button>
          </div>

          <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-muted">
            p.{node.page_start}
            {node.page_end > node.page_start ? `–${node.page_end}` : ""}
          </span>
        </div>

        {hasChildren && isExpanded && (
          <div className="space-y-0.5">
            {node.children.map((child) => renderTreeNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  const extractionMethod = toc?.[0]?.extraction_method || "pdf_outline";

  return (
    <div className="grid h-full grid-cols-12 overflow-hidden bg-console-bg">
      {/* Left: Document Corpus Table */}
      <div className="col-span-12 flex flex-col overflow-hidden border-r border-console-border lg:col-span-6">
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
            <div className="font-mono text-xs text-ink-muted">
              Loading ingested reports...
            </div>
          ) : (
            <div className="space-y-2.5">
              {(docs || []).map((doc) => {
                const isSelected = selectedDoc?.id === doc.id;
                const hasUsedSec = highlightedDocumentId === doc.id && highlightedSectionIds.length > 0;
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
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded border border-signal-amber/40 bg-signal-amberDim px-1.5 py-0.5 font-mono text-[11px] text-signal-amber">
                            {doc.doc_code}
                          </span>
                          <span className="font-mono text-[11px] text-ink-muted">
                            {doc.org} · {doc.mission}
                          </span>
                          {hasUsedSec && (
                            <span className="inline-flex items-center gap-1 rounded border border-signal-amber/60 bg-signal-amber/15 px-1.5 py-0.5 font-mono text-[10px] text-signal-amber">
                              <Sparkles className="h-3 w-3" />
                              ACTIVE IN CHAT
                            </span>
                          )}
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

                    <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] tabular-nums text-ink-secondary">
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

      {/* Right: Hierarchical Collapsible ToC Tree */}
      <div className="col-span-12 flex flex-col overflow-hidden bg-console-surface lg:col-span-6">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-console-border px-4 py-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                HIERARCHICAL TOC TREE
              </span>
              {toc && toc.length > 0 && (
                <span className="rounded border border-console-borderStrong px-1.5 py-0.5 font-mono text-[10px] text-ink-secondary">
                  {extractionMethod}
                </span>
              )}
            </div>
            <h3 className="mt-0.5 text-sm font-semibold text-ink-primary">
              {selectedDoc
                ? `${selectedDoc.doc_code} — Table of Contents`
                : "Select a report"}
            </h3>
          </div>

          {highlightedSectionIds.length > 0 && (
            <button
              type="button"
              onClick={() => setHighlightedSections([], null)}
              className="rounded border border-console-border px-2 py-1 font-mono text-[10px] text-ink-secondary hover:text-ink-primary"
            >
              Clear Highlight ({highlightedSectionIds.length})
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {!selectedDoc && (
            <div className="flex h-full flex-col items-center justify-center text-center text-ink-muted">
              <BookOpen className="h-7 w-7 text-console-borderStrong" />
              <p className="mt-2 font-mono text-xs">
                Click any report on the left to inspect its hierarchical ToC tree.
              </p>
            </div>
          )}
          {selectedDoc && tocLoading && (
            <p className="font-mono text-xs text-ink-muted">
              Loading section tree...
            </p>
          )}
          {selectedDoc && toc && (
            <div className="space-y-0.5">
              {treeRoots.map((root) => renderTreeNode(root, 0))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

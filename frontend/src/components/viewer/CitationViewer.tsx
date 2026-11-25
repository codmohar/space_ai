import { useEffect, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileSearch,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { api, type BBoxItem, type CitationOut } from "../../api/client";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

interface CitationViewerProps {
  citation: CitationOut | null;
}

export function CitationViewer({ citation }: CitationViewerProps) {
  const [numPages, setNumPages] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.05);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (citation) {
      setCurrentPage(citation.page_number);
      setLoadError(null);
    }
  }, [citation]);

  if (!citation) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-doc-paper p-8 text-center text-doc-ink">
        <div className="max-w-sm rounded border border-doc-rule bg-doc-sheet p-6">
          <FileSearch className="mx-auto h-8 w-8 text-signal-amber" />
          <h3 className="mt-3 text-sm font-semibold uppercase tracking-wide text-doc-ink">
            Primary Document Citation Viewer
          </h3>
          <p className="mt-2 font-serif text-[13.5px] leading-relaxed text-[#5A6270]">
            Select any monospace citation chip in the Research Assistant or open
            a report from the Document Explorer to inspect the exact PDF page,
            bounding-box highlight, and archival provenance.
          </p>
        </div>
      </div>
    );
  }

  const pdfUrl = api.documentPdfUrl(citation.document_id);
  const pageBBoxes: BBoxItem[] = (citation.bbox_json || []).filter(
    (b) => b.page === currentPage
  );

  return (
    <div className="flex h-full flex-col bg-doc-paper text-doc-ink">
      {/* Light Archival Document Header & Provenance Bar */}
      <div className="border-b border-doc-rule bg-doc-sheet px-4 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="rounded bg-console-base px-1.5 py-0.5 font-mono text-[11px] font-medium text-signal-amber">
                {citation.doc_code}
              </span>
              <h2 className="truncate text-sm font-semibold text-doc-ink">
                {citation.document_title}
              </h2>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-[#5A6270]">
              <span>SECTION: {citation.section}</span>
              <span>·</span>
              <span>LICENCE: {citation.licence}</span>
              <span>·</span>
              <a
                href={citation.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[#A45D06] underline decoration-[#A45D06]/40 hover:text-doc-ink"
              >
                Source URL <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>

          {/* Page Navigation & Zoom Controls */}
          <div className="flex items-center gap-1.5 font-mono text-xs tabular-nums">
            <button
              type="button"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
              aria-label="Previous page"
              className="rounded border border-doc-rule bg-doc-paper p-1 hover:bg-doc-rule/50 disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-2">
              p.{currentPage} / {numPages || "?"}
            </span>
            <button
              type="button"
              onClick={() =>
                setCurrentPage((p) =>
                  numPages ? Math.min(numPages, p + 1) : p + 1
                )
              }
              disabled={numPages > 0 && currentPage >= numPages}
              aria-label="Next page"
              className="rounded border border-doc-rule bg-doc-paper p-1 hover:bg-doc-rule/50 disabled:opacity-40"
            >
              <ChevronRight className="h-4 w-4" />
            </button>

            <span className="mx-1 text-doc-rule">|</span>

            <button
              type="button"
              onClick={() => setScale((s) => Math.max(0.6, Number((s - 0.15).toFixed(2))))}
              aria-label="Zoom out"
              className="rounded border border-doc-rule bg-doc-paper p-1 hover:bg-doc-rule/50"
            >
              <ZoomOut className="h-4 w-4" />
            </button>
            <span className="w-11 text-center">{Math.round(scale * 100)}%</span>
            <button
              type="button"
              onClick={() => setScale((s) => Math.min(2.2, Number((s + 0.15).toFixed(2))))}
              aria-label="Zoom in"
              className="rounded border border-doc-rule bg-doc-paper p-1 hover:bg-doc-rule/50"
            >
              <ZoomIn className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Cited Excerpt Callout */}
        {citation.quote && (
          <div className="mt-2 rounded border border-signal-amber/50 bg-[#FFF8EE] px-3 py-1.5">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[#9E5B08]">
                CITED CHUNK EXCERPT · p.{citation.page_number}
              </span>
              {currentPage !== citation.page_number && (
                <button
                  type="button"
                  onClick={() => setCurrentPage(citation.page_number)}
                  className="font-mono text-[10px] font-semibold text-[#9E5B08] underline"
                >
                  Jump back to cited page {citation.page_number}
                </button>
              )}
            </div>
            <p className="mt-0.5 font-serif text-[13px] italic leading-snug text-doc-ink">
              “{citation.quote}”
            </p>
          </div>
        )}
      </div>

      {/* PDF Canvas with Normalized BBox Highlight Overlay */}
      <div className="flex-1 overflow-auto p-5">
        {loadError ? (
          <div className="mx-auto max-w-md rounded border border-status-conflict/40 bg-doc-sheet p-4 text-sm text-status-conflict">
            Failed to load PDF document: {loadError}
          </div>
        ) : (
          <div className="mx-auto flex w-fit flex-col items-center">
            <Document
              file={pdfUrl}
              onLoadSuccess={({ numPages: total }) => setNumPages(total)}
              onLoadError={(err) => setLoadError(err.message)}
              loading={
                <div className="rounded border border-doc-rule bg-doc-sheet px-6 py-10 font-mono text-xs text-[#5A6270]">
                  Loading archival PDF {citation.doc_code}...
                </div>
              }
            >
              <div className="relative border border-doc-rule bg-white shadow-sm">
                <Page
                  pageNumber={currentPage}
                  scale={scale}
                  renderTextLayer={true}
                  renderAnnotationLayer={true}
                />

                {/* Translucent Amber Bounding-Box Highlight Layer */}
                {pageBBoxes.length > 0 && (
                  <div
                    aria-label="Cited chunk highlight overlay"
                    className="pointer-events-none absolute inset-0 z-10"
                  >
                    {pageBBoxes.map((box, idx) => {
                      const pw = box.page_width || 612;
                      const ph = box.page_height || 792;
                      const leftPct = (box.x0 / pw) * 100;
                      const topPct = (box.y0 / ph) * 100;
                      const widthPct = ((box.x1 - box.x0) / pw) * 100;
                      const heightPct = ((box.y1 - box.y0) / ph) * 100;
                      return (
                        <div
                          key={idx}
                          style={{
                            left: `${leftPct}%`,
                            top: `${topPct}%`,
                            width: `${widthPct}%`,
                            height: `${heightPct}%`,
                          }}
                          className="absolute rounded-[2px] border border-[#D98218] bg-[#F2A33A]/25"
                        />
                      );
                    })}
                  </div>
                )}
              </div>
            </Document>
          </div>
        )}
      </div>
    </div>
  );
}

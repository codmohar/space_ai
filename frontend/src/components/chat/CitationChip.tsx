import { FileText } from "lucide-react";
import type { CitationOut } from "../../api/client";

interface CitationChipProps {
  citation: CitationOut;
  isActive?: boolean;
  onSelect: (citation: CitationOut) => void;
}

export function CitationChip({
  citation,
  isActive = false,
  onSelect,
}: CitationChipProps) {
  const shortSection =
    citation.section.length > 26
      ? `${citation.section.slice(0, 24)}…`
      : citation.section;

  return (
    <button
      type="button"
      onClick={() => onSelect(citation)}
      title={`${citation.document_title} · Page ${citation.page_number} · ${citation.section}`}
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[11px] tabular-nums transition-colors ${
        isActive
          ? "border-signal-amber bg-signal-amber text-console-base font-semibold"
          : "border-console-borderStrong bg-console-elevated text-signal-amber hover:border-signal-amber hover:bg-signal-amberDim"
      }`}
    >
      <FileText className="h-3 w-3 shrink-0" />
      <span>
        [{citation.doc_code} · p.{citation.page_number} · {shortSection}]
      </span>
    </button>
  );
}

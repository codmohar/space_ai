import type { CitationOut, ClaimOut } from "../../api/client";
import { designTokens } from "../../styles/design-tokens";
import { CitationChip } from "./CitationChip";

interface ClaimBlockProps {
  claim: ClaimOut;
  activeChunkId?: string;
  onSelectCitation: (citation: CitationOut) => void;
}

export function ClaimBlock({
  claim,
  activeChunkId,
  onSelectCitation,
}: ClaimBlockProps) {
  const badge =
    designTokens.evidenceClassificationLabels[claim.evidence_classification] ||
    designTokens.evidenceClassificationLabels.explicitly_stated;

  return (
    <div className="rounded border border-console-border bg-console-surface p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span
          className={`inline-block rounded border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${badge.tone}`}
        >
          {badge.label}
        </span>
        <span className="font-mono text-[10px] text-status-verified">
          VERIFIED CITATION
        </span>
      </div>

      <p className="text-[13.5px] leading-relaxed text-ink-primary">
        {claim.claim_text}
      </p>

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {claim.citations.map((cit, idx) => (
          <CitationChip
            key={`${cit.chunk_id}-${idx}`}
            citation={cit}
            isActive={activeChunkId === cit.chunk_id}
            onSelect={onSelectCitation}
          />
        ))}
      </div>
    </div>
  );
}

import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { FailureEventOut } from "../../api/client";
import { designTokens } from "../../styles/design-tokens";

export interface FailureNodeData extends Record<string, unknown> {
  event: FailureEventOut;
  isSelected: boolean;
}

export function FailureEventNode({ data }: NodeProps) {
  const { event, isSelected } = data as FailureNodeData;
  const classBadge =
    designTokens.evidenceClassificationLabels[event.evidence_classification] ||
    designTokens.evidenceClassificationLabels.explicitly_stated;
  const isVerified = event.verification_status === "verified";
  const isInference = event.evidence_classification === "system_inference";

  return (
    <div
      className={`w-[260px] rounded bg-console-surface p-3 text-left transition-colors ${
        isInference ? "border-2 border-dashed" : "border"
      } ${
        isSelected
          ? "border-signal-amber ring-1 ring-signal-amber/60"
          : isVerified
            ? "border-console-borderStrong hover:border-signal-amber/70"
            : "border-signal-amber/50 hover:border-signal-amber"
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2.5 !w-2.5 !border-console-bg !bg-signal-amber"
      />

      <div className="flex items-center justify-between gap-1.5">
        <span className="font-mono text-[10px] font-semibold tabular-nums text-signal-amber">
          T{event.event_order}
          {event.timestamp_label ? ` · ${event.timestamp_label}` : ""}
        </span>
        <span
          className={`rounded border px-1.5 py-0.2 font-mono text-[9px] uppercase ${
            isVerified
              ? "border-status-verified/40 bg-status-verified/10 text-status-verified"
              : "border-dashed border-signal-amber/60 text-signal-amber"
          }`}
        >
          {isVerified ? "VERIFIED" : "UNVERIFIED"}
        </span>
      </div>

      <h4 className="mt-1.5 line-clamp-2 text-[12.5px] font-semibold leading-snug text-ink-primary">
        {event.title}
      </h4>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span
          className={`rounded border px-1.5 py-0.5 font-mono text-[9px] uppercase ${classBadge.tone}`}
        >
          {classBadge.label}
        </span>
        <span className="rounded border border-console-border px-1.5 py-0.5 font-mono text-[9px] uppercase text-ink-muted">
          {event.event_type.replace("_", " ")}
        </span>
      </div>

      <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-ink-muted">
        <span className="truncate">{event.subsystem || "General"}</span>
        <span>p.{event.page_number}</span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!h-2.5 !w-2.5 !border-console-bg !bg-signal-amber"
      />
    </div>
  );
}

import { useEffect } from "react";
import { AlertCircle, CheckCircle2, ChevronRight, FileText, Loader2, X } from "lucide-react";
import { useWorkspaceStore } from "../../stores/workspaceStore";

export function IngestionNotificationBanner() {
  const activeIngestions = useWorkspaceStore((s) => s.activeIngestions);
  const removeIngestionNotification = useWorkspaceStore((s) => s.removeIngestionNotification);
  const setActiveRoute = useWorkspaceStore((s) => s.setActiveRoute);

  // Auto-dismiss completed notifications after 10 seconds
  useEffect(() => {
    const completed = activeIngestions.filter((n) => n.status === "indexed" || n.status === "failed");
    if (completed.length === 0) return;

    const timers = completed.map((n) =>
      setTimeout(() => {
        removeIngestionNotification(n.jobId);
      }, 10000)
    );

    return () => {
      timers.forEach((t) => clearTimeout(t));
    };
  }, [activeIngestions, removeIngestionNotification]);

  if (activeIngestions.length === 0) {
    return null;
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="space-y-2 border-b border-console-border bg-console-elevated px-4 py-2 text-xs shadow-md"
    >
      {activeIngestions.map((n) => {
        const isProcessing = n.status === "queued" || n.status === "processing";
        const isIndexed = n.status === "indexed";
        const isFailed = n.status === "failed";

        return (
          <div
            key={n.jobId}
            className={`flex flex-wrap items-center justify-between gap-3 rounded border px-3 py-2.5 transition-all ${
              isIndexed
                ? "border-status-verified/60 bg-status-verified/10 text-ink-primary"
                : isFailed
                  ? "border-status-conflict/60 bg-status-conflict/10 text-status-conflict"
                  : "border-signal-amber/60 bg-signal-amber/10 text-ink-primary"
            }`}
          >
            <div className="flex items-center gap-2.5 font-mono">
              {isProcessing && (
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-signal-amber" />
              )}
              {isIndexed && (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-status-verified" />
              )}
              {isFailed && (
                <AlertCircle className="h-4 w-4 shrink-0 text-status-conflict" />
              )}

              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                      isIndexed
                        ? "bg-status-verified text-console-base"
                        : isFailed
                          ? "bg-status-conflict text-white"
                          : "bg-signal-amber text-console-base"
                    }`}
                  >
                    {isIndexed
                      ? "DATABASE SEEDED"
                      : isFailed
                        ? "INGESTION FAILED"
                        : "PROCESSING & SEEDING"}
                  </span>
                  <span className="font-semibold text-ink-primary">
                    {n.title || n.filename}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-ink-secondary">
                  {n.message ||
                    (isIndexed
                      ? "Document seeded successfully in database! Ready for RAG and STAIR queries."
                      : isFailed
                        ? "Ingestion encountered an error during parsing or seeding."
                        : `Reading and processing document (${n.progressPct}%)... extracting ToC, chunks, embeddings & incident relationships`)}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 font-mono">
              {isProcessing && (
                <div className="flex items-center gap-2">
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-console-borderStrong sm:w-32">
                    <div
                      style={{ width: `${Math.max(10, n.progressPct)}%` }}
                      className="h-full bg-signal-amber transition-all duration-300"
                    />
                  </div>
                  <span className="text-[10px] text-signal-amber">{n.progressPct}%</span>
                </div>
              )}

              {isIndexed && (
                <button
                  type="button"
                  onClick={() => setActiveRoute("assistant")}
                  className="inline-flex items-center gap-1 rounded border border-status-verified bg-status-verified/20 px-2.5 py-1 text-[11px] font-medium text-status-verified hover:bg-status-verified/30"
                >
                  <FileText className="h-3 w-3" />
                  Query Assistant
                  <ChevronRight className="h-3 w-3" />
                </button>
              )}

              <button
                type="button"
                onClick={() => removeIngestionNotification(n.jobId)}
                aria-label="Dismiss notification"
                className="rounded p-1 text-ink-muted hover:bg-console-base hover:text-ink-primary"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

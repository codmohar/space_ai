import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Database, Play, X } from "lucide-react";
import { api, type DemoStepOut } from "../../api/client";
import { type NavRoute, useWorkspaceStore } from "../../stores/workspaceStore";

function routeForTargetPage(target: string): NavRoute {
  switch (target) {
    case "chat":
    case "citation":
      return "assistant";
    case "similar":
      return "similar";
    case "failures":
      return "failures";
    case "kg":
      return "kg";
    case "eval":
      return "evaluation";
    default:
      return "assistant";
  }
}

export function DemoWalkthroughBar() {
  const queryClient = useQueryClient();
  const {
    demoMode,
    setDemoMode,
    demoStepIndex,
    setDemoStepIndex,
    setActiveRoute,
    setSelectedMission,
    setConversationId,
    addTurn,
    setActiveCitation,
    setHighlightedSections,
    setFailureChainDocId,
    setPrefillSimilarQuery,
    setPrefillKgQuery,
  } = useWorkspaceStore();

  const walkthroughQuery = useQuery({
    queryKey: ["demo-walkthrough"],
    queryFn: api.demoWalkthrough,
    enabled: demoMode,
  });

  const docsQuery = useQuery({
    queryKey: ["documents"],
    queryFn: api.listDocuments,
    enabled: demoMode,
  });

  const prewarmMutation = useMutation({
    mutationFn: api.demoPrewarm,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["demo-walkthrough"] });
    },
  });

  const executeMutation = useMutation({
    mutationFn: async (step: DemoStepOut) => {
      const targetRoute = routeForTargetPage(step.target_page);
      setActiveRoute(targetRoute);

      if (step.target_page === "chat" && step.suggested_query) {
        if (step.suggested_mission) {
          setSelectedMission(step.suggested_mission);
        }
        addTurn({
          id: `demo-u-${Date.now()}`,
          role: "user",
          query: step.suggested_query,
        });
        const res = await api.demoAsk({
          query: step.suggested_query,
          mission: step.suggested_mission || null,
          use_cache: true,
        });
        const data = res.response;
        setConversationId(data.conversation_id);
        addTurn({
          id: data.message_id,
          role: "assistant",
          response: data,
        });
        if (data.citations.length > 0) {
          setActiveCitation(data.citations[0]);
        }
        const secIds = Array.from(
          new Set([
            ...(data.used_section_ids || []),
            ...(data.selected_sections || []).map((s) => s.section_id),
          ])
        );
        if (secIds.length > 0) {
          setHighlightedSections(secIds, data.citations[0]?.document_id || null);
        }
      } else if (step.target_page === "similar" && step.suggested_query) {
        setPrefillSimilarQuery(step.suggested_query);
      } else if (step.target_page === "failures") {
        const docs = docsQuery.data || [];
        const match = docs.find(
          (d) =>
            (step.suggested_doc_code && d.doc_code === step.suggested_doc_code) ||
            (step.suggested_mission && d.mission === step.suggested_mission)
        );
        if (match) {
          setFailureChainDocId(match.id);
        }
      } else if (step.target_page === "kg" && step.suggested_query) {
        setPrefillKgQuery(step.suggested_query);
      }
    },
  });

  if (!demoMode) return null;

  const steps = walkthroughQuery.data?.steps || [];
  const currentStep = steps[demoStepIndex] || steps[0];

  return (
    <div
      data-testid="demo-walkthrough-bar"
      className="border-b border-signal-amber/40 bg-signal-amberDim/40 px-5 py-2.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="rounded border border-signal-amber bg-console-bg px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-widest text-signal-amber">
            DEMO WALKTHROUGH
          </span>
          <div className="flex items-center gap-1">
            {steps.map((s, idx) => (
              <button
                key={s.step_id}
                type="button"
                onClick={() => setDemoStepIndex(idx)}
                className={`rounded px-2 py-0.5 font-mono text-[11px] tabular-nums transition-colors ${
                  idx === demoStepIndex
                    ? "bg-signal-amber text-console-bg font-semibold"
                    : "border border-console-border bg-console-surface text-ink-secondary hover:text-ink-primary"
                }`}
              >
                0{s.step_number}
              </button>
            ))}
          </div>
          {walkthroughQuery.data && (
            <span className="font-mono text-[10px] text-ink-secondary">
              {walkthroughQuery.data.cache_warmed
                ? `CACHE WARM (${walkthroughQuery.data.cached_query_count} VERIFIED QUERIES)`
                : "CACHE COLD"}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => prewarmMutation.mutate()}
            disabled={prewarmMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded border border-console-borderStrong bg-console-surface px-2.5 py-1 font-mono text-[11px] text-ink-primary hover:border-signal-amber disabled:opacity-50"
          >
            <Database className="h-3 w-3 text-signal-amber" />
            {prewarmMutation.isPending ? "Warming..." : "Pre-Warm Cache"}
          </button>
          <button
            type="button"
            onClick={() => setDemoStepIndex(Math.max(0, demoStepIndex - 1))}
            disabled={demoStepIndex <= 0}
            aria-label="Previous walkthrough step"
            className="rounded border border-console-border bg-console-surface p-1 text-ink-secondary hover:text-ink-primary disabled:opacity-40"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() =>
              setDemoStepIndex(Math.min(Math.max(0, steps.length - 1), demoStepIndex + 1))
            }
            disabled={demoStepIndex >= steps.length - 1}
            aria-label="Next walkthrough step"
            className="rounded border border-console-border bg-console-surface p-1 text-ink-secondary hover:text-ink-primary disabled:opacity-40"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setDemoMode(false)}
            aria-label="Close Demo Walkthrough"
            className="rounded border border-console-border bg-console-surface p-1 text-ink-muted hover:text-ink-primary"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {currentStep && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3 border-t border-console-border/60 pt-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-[11px] font-semibold text-signal-amber">
                STEP 0{currentStep.step_number}:
              </span>
              <span className="text-xs font-semibold text-ink-primary">
                {currentStep.title}
              </span>
            </div>
            <p className="text-[11px] text-ink-secondary">{currentStep.subtitle}</p>
          </div>

          <button
            type="button"
            data-testid="demo-execute-step"
            onClick={() => executeMutation.mutate(currentStep)}
            disabled={executeMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded bg-signal-amber px-3 py-1.5 font-mono text-[11px] font-semibold text-console-bg hover:bg-signal-amber/90 disabled:opacity-50"
          >
            <Play className="h-3 w-3" />
            {executeMutation.isPending ? "Executing..." : currentStep.action_label}
          </button>
        </div>
      )}
    </div>
  );
}

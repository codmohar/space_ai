import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BookOpen,
  FileSearch,
  GitBranch,
  Layers,
  LayoutDashboard,
  Network,
  ShieldAlert,
} from "lucide-react";
import { api } from "../../api/client";
import { type NavRoute, useWorkspaceStore } from "../../stores/workspaceStore";

interface NavItem {
  id: NavRoute;
  label: string;
  code: string;
  icon: typeof LayoutDashboard;
  phaseTag?: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Mission Control", code: "SYS-01", icon: LayoutDashboard },
  { id: "assistant", label: "Research Assistant", code: "RAG-02", icon: FileSearch },
  { id: "documents", label: "Document Explorer", code: "DOC-03", icon: BookOpen },
  { id: "failures", label: "Failure Chains", code: "FCR-04", icon: GitBranch },
  { id: "similar", label: "Similar Incidents", code: "SIM-05", icon: Layers },
  { id: "kg", label: "Knowledge Graph", code: "KG-07", icon: Network },
  { id: "evaluation", label: "Evaluation", code: "EVL-06", icon: Activity },
];

export function AppShell({ children }: { children: ReactNode }) {
  const activeRoute = useWorkspaceStore((s) => s.activeRoute);
  const setActiveRoute = useWorkspaceStore((s) => s.setActiveRoute);

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30000,
    retry: 1,
  });

  const isHealthy = health?.status === "ok";

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-console-bg text-ink-primary">
      {/* Left Navigation Rail */}
      <aside
        aria-label="Primary navigation"
        className="flex w-60 shrink-0 flex-col border-r border-console-border bg-console-surface"
      >
        <div className="border-b border-console-border px-4 py-3.5">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-signal-amber">
              AVISHKAR // 2K26
            </span>
            <span className="rounded border border-console-borderStrong px-1.5 py-0.5 font-mono text-[10px] text-ink-secondary">
              v0.1
            </span>
          </div>
          <h1 className="mt-1 text-base font-semibold tracking-tight text-ink-primary">
            MISSIONWISE AI
          </h1>
          <p className="text-[11px] text-ink-muted">
            Flight-Ops Lessons Intelligence
          </p>
        </div>

        <nav className="flex-1 space-y-0.5 px-2.5 py-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = activeRoute === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveRoute(item.id)}
                className={`group flex w-full items-center justify-between rounded px-2.5 py-2 text-left text-[13px] transition-colors ${
                  active
                    ? "border border-signal-amber/40 bg-signal-amberDim text-ink-primary"
                    : "border border-transparent text-ink-secondary hover:border-console-border hover:bg-console-elevated hover:text-ink-primary"
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <Icon
                    className={`h-4 w-4 ${
                      active ? "text-signal-amber" : "text-ink-muted group-hover:text-ink-secondary"
                    }`}
                  />
                  <span className="font-medium">{item.label}</span>
                </span>
                <span className="font-mono text-[10px] text-ink-muted">
                  {item.phaseTag ? item.phaseTag : item.code}
                </span>
              </button>
            );
          })}
        </nav>

        {/* System Telemetry Strip */}
        <div className="border-t border-console-border px-4 py-3 text-[11px]">
          <div className="flex items-center justify-between">
            <span className="font-mono uppercase tracking-wider text-ink-muted">
              Telemetry
            </span>
            <span
              className={`inline-flex items-center gap-1.5 font-mono text-[11px] ${
                isHealthy ? "text-status-verified" : "text-signal-amber"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isHealthy ? "bg-status-verified" : "bg-signal-amber"
                }`}
              />
              {isHealthy ? "ONLINE" : "DEGRADED"}
            </span>
          </div>
          <div className="mt-2 space-y-1 font-mono text-[11px] text-ink-secondary tabular-nums">
            <div className="flex justify-between">
              <span className="text-ink-muted">STAIR</span>
              <span>L1 / L2 Ready</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-muted">PGVECTOR</span>
              <span>{health?.pgvector || "checking"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-ink-muted">LLM</span>
              <span>
                {health ? (health.llm_configured ? health.llm_provider : "NO KEY") : "..."}
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area + Mandatory Safety Footer */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-11 shrink-0 items-center justify-between border-b border-console-border bg-console-surface px-5">
          <div className="flex items-center gap-3">
            <span className="font-mono text-[11px] uppercase tracking-widest text-ink-muted">
              WORKSPACE
            </span>
            <span className="text-console-borderStrong">/</span>
            <span className="text-xs font-semibold uppercase tracking-wide text-ink-primary">
              {NAV_ITEMS.find((n) => n.id === activeRoute)?.label}
            </span>
          </div>
          <div className="flex items-center gap-4 font-mono text-[11px] text-ink-secondary">
            <span>PROTOGUYS</span>
            <span className="text-console-borderStrong">|</span>
            <span>SHORTCUT: [/] FOCUS QUERY</span>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>

        <footer className="flex h-8 shrink-0 items-center justify-between border-t border-console-border bg-console-surface px-5 text-[11px] text-ink-muted">
          <span className="flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5 text-signal-amber" />
            MISSIONWISE is a knowledge-support tool, not a certifier of spacecraft safety.
          </span>
          <span className="font-mono text-[10px]">
            PUBLIC ARCHIVAL REPORTS ONLY · CITATION-VALIDATED RAG
          </span>
        </footer>
      </div>
    </div>
  );
}

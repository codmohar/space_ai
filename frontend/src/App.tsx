import { AppShell } from "./components/layout/AppShell";
import { AssistantPage } from "./pages/AssistantPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { PhasePlaceholderPage } from "./pages/PhasePlaceholderPage";
import { useWorkspaceStore } from "./stores/workspaceStore";

export default function App() {
  const activeRoute = useWorkspaceStore((s) => s.activeRoute);

  return (
    <AppShell>
      {activeRoute === "dashboard" && <DashboardPage />}
      {activeRoute === "assistant" && <AssistantPage />}
      {activeRoute === "documents" && <DocumentsPage />}
      {activeRoute === "failures" && (
        <PhasePlaceholderPage
          code="FCR-04"
          title="Failure Chain Reconstruction"
          description="Interactive React Flow causal/chronological timeline separating verified causality from pending system extractions, backed by failure_events and failure_relationships."
        />
      )}
      {activeRoute === "similar" && (
        <PhasePlaceholderPage
          code="SIM-05"
          title="Similar Past Failures"
          description="Engineering relevance matching across subsystems, anomalies, root causes, and corrective actions using the shared retrieval pipeline."
        />
      )}
      {activeRoute === "evaluation" && (
        <PhasePlaceholderPage
          code="EVL-06"
          title="Evaluation Dashboard"
          description="Displays measured metrics strictly produced by scripts in /scripts (BM25 vs Dense vs Hybrid vs STAIR L2/L3, RAG faithfulness, abstention accuracy). Currently: Not yet evaluated."
        />
      )}
    </AppShell>
  );
}

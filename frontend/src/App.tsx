import { AppShell } from "./components/layout/AppShell";
import { AssistantPage } from "./pages/AssistantPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { FailureChainPage } from "./pages/FailureChainPage";
import { PhasePlaceholderPage } from "./pages/PhasePlaceholderPage";
import { useWorkspaceStore } from "./stores/workspaceStore";

export default function App() {
  const activeRoute = useWorkspaceStore((s) => s.activeRoute);

  return (
    <AppShell>
      {activeRoute === "dashboard" && <DashboardPage />}
      {activeRoute === "assistant" && <AssistantPage />}
      {activeRoute === "documents" && <DocumentsPage />}
      {activeRoute === "failures" && <FailureChainPage />}
      {activeRoute === "similar" && (
        <PhasePlaceholderPage
          code="SIM-05"
          title="Similar Past Failures"
          description="Engineering relevance matching across subsystems, anomalies, root causes, and corrective actions using the shared retrieval pipeline."
        />
      )}
      {activeRoute === "evaluation" && <EvaluationPage />}
    </AppShell>
  );
}

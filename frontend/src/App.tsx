import { AdminPage } from "./pages/AdminPage";
import { AppShell } from "./components/layout/AppShell";
import { AssistantPage } from "./pages/AssistantPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { FailureChainPage } from "./pages/FailureChainPage";
import { KnowledgeGraphPage } from "./pages/KnowledgeGraphPage";
import { SimilarFailuresPage } from "./pages/SimilarFailuresPage";
import { useWorkspaceStore } from "./stores/workspaceStore";

export default function App() {
  const activeRoute = useWorkspaceStore((s) => s.activeRoute);

  return (
    <AppShell>
      {activeRoute === "dashboard" && <DashboardPage />}
      {activeRoute === "assistant" && <AssistantPage />}
      {activeRoute === "documents" && <DocumentsPage />}
      {activeRoute === "failures" && <FailureChainPage />}
      {activeRoute === "similar" && <SimilarFailuresPage />}
      {activeRoute === "kg" && <KnowledgeGraphPage />}
      {activeRoute === "evaluation" && <EvaluationPage />}
      {activeRoute === "admin" && <AdminPage />}
    </AppShell>
  );
}

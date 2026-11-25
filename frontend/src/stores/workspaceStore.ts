import { create } from "zustand";
import type { ChatResponse, CitationOut } from "../api/client";

export type NavRoute =
  | "dashboard"
  | "assistant"
  | "documents"
  | "failures"
  | "similar"
  | "evaluation";

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  query?: string;
  response?: ChatResponse;
  error?: string;
}

interface WorkspaceState {
  activeRoute: NavRoute;
  setActiveRoute: (route: NavRoute) => void;

  selectedMission: string;
  setSelectedMission: (mission: string) => void;

  conversationId: string | null;
  setConversationId: (id: string | null) => void;

  turns: ChatTurn[];
  addTurn: (turn: ChatTurn) => void;
  clearTurns: () => void;

  activeCitation: CitationOut | null;
  setActiveCitation: (cit: CitationOut | null) => void;

  splitRatio: number;
  setSplitRatio: (ratio: number) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeRoute: "assistant",
  setActiveRoute: (activeRoute) => set({ activeRoute }),

  selectedMission: "",
  setSelectedMission: (selectedMission) => set({ selectedMission }),

  conversationId: null,
  setConversationId: (conversationId) => set({ conversationId }),

  turns: [],
  addTurn: (turn) => set((state) => ({ turns: [...state.turns, turn] })),
  clearTurns: () => set({ turns: [], conversationId: null, activeCitation: null }),

  activeCitation: null,
  setActiveCitation: (activeCitation) => set({ activeCitation }),

  splitRatio: 52,
  setSplitRatio: (splitRatio) =>
    set({ splitRatio: Math.min(72, Math.max(30, splitRatio)) }),
}));

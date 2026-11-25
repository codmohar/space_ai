import type {
  ConfidenceCategory,
  EvidenceClassification,
} from "../styles/design-tokens";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export interface BBoxItem {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  page_width: number;
  page_height: number;
}

export interface CitationOut {
  id?: string | null;
  document_id: string;
  doc_code: string;
  document_title: string;
  source_url: string;
  licence: string;
  section_id?: string | null;
  section: string;
  page_number: number;
  chunk_id: string;
  quote: string;
  bbox_json: BBoxItem[];
  verified: boolean;
}

export interface ClaimOut {
  claim_text: string;
  evidence_classification: EvidenceClassification;
  citations: CitationOut[];
}

export interface SelectedSectionOut {
  section_id: string;
  document_id: string;
  doc_code: string;
  section_path: string;
  title: string;
  page_start: number;
  page_end: number;
  reason: string;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  retrieval_log_id: string;
  answer: string;
  spoken_text?: string;
  standalone_query?: string;
  response_style?: "standard" | "simpler";
  claims: ClaimOut[];
  citations: CitationOut[];
  confidence: ConfidenceCategory;
  confidence_score: number;
  evidence_classification: EvidenceClassification;
  abstained: boolean;
  stair_level: string;
  selector_name: string;
  selected_sections: SelectedSectionOut[];
  used_section_ids: string[];
}

export interface VoiceCapabilities {
  server_stt_available: boolean;
  server_stt_engine: string;
  server_tts_available: boolean;
  server_tts_engine: string;
}

export interface FailureEventOut {
  id: string;
  mission: string;
  event_type: string;
  title: string;
  description: string;
  event_order: number;
  timestamp_label?: string | null;
  subsystem?: string | null;
  evidence_classification: EvidenceClassification;
  verification_status: "pending" | "verified" | "rejected";
  document_id: string;
  doc_code: string;
  document_title: string;
  source_url: string;
  licence: string;
  section_id?: string | null;
  section: string;
  page_number: number;
  chunk_id: string;
  evidence_text: string;
  bbox_json: BBoxItem[];
}

export type FailureRelationshipType =
  | "caused_by"
  | "contributed_to"
  | "preceded_by"
  | "associated_with"
  | "reported_as";

export interface FailureRelationshipOut {
  id: string;
  source_event_id: string;
  target_event_id: string;
  relationship_type: FailureRelationshipType;
  verification_status: "pending" | "verified" | "rejected";
  document_id: string;
  section_id?: string | null;
  page_number: number;
  evidence_chunk_id: string;
  evidence_text: string;
}

export interface FailureChainResponse {
  document_id: string;
  doc_code: string;
  document_title: string;
  mission: string;
  events: FailureEventOut[];
  relationships: FailureRelationshipOut[];
  verified_events: number;
  verified_relationships: number;
}

export interface DocumentSummary {
  id: string;
  doc_code: string;
  title: string;
  source_url: string;
  licence: string;
  org: string;
  mission: string;
  page_count: number;
  version: string;
  ingestion_status: string;
  chunk_count: number;
  section_count: number;
  created_at: string;
}

export interface DocumentSectionNode {
  id: string;
  parent_id: string | null;
  title: string;
  level: number;
  is_leaf: boolean;
  section_path: string;
  page_start: number;
  page_end: number;
  order_index: number;
  extraction_method: string;
}

export interface EvalMethodMetrics {
  method: string;
  stair_level: string;
  evaluated_questions: number;
  recall_at_1: number;
  recall_at_3: number;
  recall_at_5: number;
  mrr: number;
  ndcg_at_5: number;
  invalid_section_rate: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
}

export interface EvalResultsResponse {
  status: string;
  generated_at?: string | null;
  dataset_path?: string | null;
  total_questions: number;
  answerable_questions: number;
  unanswerable_questions: number;
  methods: EvalMethodMetrics[];
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  database: string;
  pgvector: string;
  embedding_model: string;
  reranker_model: string;
  llm_provider: string;
  llm_configured: boolean;
}

export interface CorpusStatsResponse {
  document_count: number;
  section_count: number;
  chunk_count: number;
  ocr_chunk_count: number;
  retrieval_log_count: number;
  evaluation_status: string;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let message = `API request failed (${res.status})`;
    try {
      const errBody = await res.json();
      if (errBody?.message) {
        message = `[${errBody.code || res.status}] ${errBody.message}`;
      }
    } catch {
      // ignore json parse failure
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => apiFetch<HealthResponse>("/api/health"),
  stats: () => apiFetch<CorpusStatsResponse>("/api/stats"),
  listDocuments: () => apiFetch<DocumentSummary[]>("/api/documents"),
  getDocumentToc: (docId: string) =>
    apiFetch<DocumentSectionNode[]>(`/api/documents/${docId}/toc`),
  evalResults: () => apiFetch<EvalResultsResponse>("/api/eval/results"),
  voiceCapabilities: () => apiFetch<VoiceCapabilities>("/api/voice/capabilities"),
  reconstructFailures: (documentId: string, forceRebuild = true) =>
    apiFetch<FailureChainResponse>("/api/failures/reconstruct", {
      method: "POST",
      body: JSON.stringify({
        document_id: documentId,
        force_rebuild: forceRebuild,
      }),
    }),
  getFailureEvents: (documentId: string) =>
    apiFetch<FailureEventOut[]>(`/api/failures/${documentId}/events`),
  getFailureRelationships: (documentId: string) =>
    apiFetch<FailureRelationshipOut[]>(
      `/api/failures/${documentId}/relationships`
    ),
  voiceWsUrl: () => {
    const u = new URL(API_BASE_URL);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.pathname = "/api/voice/stream";
    return u.toString();
  },
  chat: (payload: {
    query: string;
    conversation_id?: string | null;
    mission?: string | null;
    selector_mode?: string | null;
  }) =>
    apiFetch<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  documentPdfUrl: (docId: string) =>
    `${API_BASE_URL}/api/documents/${docId}/file`,
};

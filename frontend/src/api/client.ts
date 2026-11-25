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

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  retrieval_log_id: string;
  answer: string;
  claims: ClaimOut[];
  citations: CitationOut[];
  confidence: ConfidenceCategory;
  confidence_score: number;
  evidence_classification: EvidenceClassification;
  abstained: boolean;
  stair_level: string;
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
  chat: (payload: {
    query: string;
    conversation_id?: string | null;
    mission?: string | null;
  }) =>
    apiFetch<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  documentPdfUrl: (docId: string) =>
    `${API_BASE_URL}/api/documents/${docId}/file`,
};

import type {
  ConfidenceCategory,
  EvidenceClassification,
} from "../styles/design-tokens";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : "";

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

export interface RelevanceBreakdown {
  semantic_score: number;
  keyword_score: number;
  rerank_score: number;
  subsystem_match_score: number;
  matched_terms: string[];
  total_relevance: number;
}

export interface SimilarIncidentOut {
  incident_id: string;
  mission: string;
  subsystem: string;
  component?: string | null;
  anomaly_title: string;
  anomaly_description: string;
  root_cause: string;
  consequence: string;
  corrective_action: string;
  failure_mechanism?: string | null;
  evidence_classification: EvidenceClassification;
  verification_status: "pending" | "verified" | "rejected";
  document_id: string;
  doc_code: string;
  document_title: string;
  source_url: string;
  licence: string;
  section: string;
  page_number: number;
  chunk_id: string;
  evidence_text: string;
  bbox_json: BBoxItem[];
  relevance: RelevanceBreakdown;
}

export interface SimilarFailuresSearchResponse {
  extracted_subsystems: string[];
  extracted_mechanisms: string[];
  extracted_keywords: string[];
  results: SimilarIncidentOut[];
}

export interface KGNodeOut {
  id: string;
  entity_type: string;
  name: string;
  mission: string;
  document_id: string;
  doc_code: string;
  document_title: string;
  source_url: string;
  licence: string;
  section: string;
  page_number: number;
  chunk_id: string;
  evidence_text: string;
  bbox_json: BBoxItem[];
}

export interface KGEdgeOut {
  id: string;
  source_entity_id: string;
  target_entity_id: string;
  relation_type: string;
  verification_status: string;
  page_number: number;
  evidence_text: string;
}

export interface KGGraphResponse {
  nodes: KGNodeOut[];
  edges: KGEdgeOut[];
}

export interface KGPathOut {
  mission: string;
  subsystem: string;
  component?: string | null;
  anomaly: string;
  root_cause: string;
  corrective_action: string;
  verification_status: string;
  citation: CitationOut;
}

export interface KGQueryResponse {
  answer: string;
  abstained: boolean;
  matched_subsystems: string[];
  paths: KGPathOut[];
  citations: CitationOut[];
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
  llm_model?: string;
  llm_configured: boolean;
  prompt_version?: string;
  auth_required?: boolean;
  models_warmed?: { embedding: boolean; reranker: boolean };
  eval_status?: string;
  incident_count?: number;
  kg_entity_count?: number;
}

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "engineer" | string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface AdminUserOut {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface AuditLogOut {
  id: string;
  user_id?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  request_id?: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface RetrievalLogOut {
  id: string;
  request_id: string;
  query_text: string;
  mission_scope?: string | null;
  stair_level: string;
  top_rerank_score?: number | null;
  confidence_category: string;
  abstained: boolean;
  latency_ms: number;
  embedding_model: string;
  reranker_model: string;
  llm_model: string;
  prompt_version: string;
  created_at: string;
}

export interface RuntimeSettingsOut {
  llm_provider: string;
  gemini_model: string;
  embedding_model: string;
  reranker_model: string;
  prompt_version: string;
  section_selector_mode: string;
  min_rerank_score_threshold: number;
  min_rrf_score_threshold: number;
  rate_limit_per_minute: number;
  chat_rate_limit_per_minute: number;
  max_upload_mb: number;
  max_upload_pages: number;
}

export interface DemoStepOut {
  step_id: string;
  step_number: number;
  title: string;
  subtitle: string;
  target_page: string;
  suggested_query?: string | null;
  suggested_mission?: string | null;
  suggested_doc_code?: string | null;
  action_label: string;
  notes: string;
}

export interface DemoWalkthroughResponse {
  enabled: boolean;
  cache_warmed: boolean;
  cached_query_count: number;
  generated_at?: string | null;
  steps: DemoStepOut[];
}

export interface DemoAskResponse {
  cache_hit: boolean;
  response: ChatResponse;
}

export interface DemoPrewarmResponse {
  status: string;
  cached_queries: number;
  generated_at: string;
}

const AUTH_TOKEN_KEY = "mw_auth_token";

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAuthToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(AUTH_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  } catch {
    // ignore storage errors
  }
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
  const token = getAuthToken();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
  searchSimilarFailures: (payload: {
    problem_description: string;
    mission?: string | null;
    top_k?: number;
  }) =>
    apiFetch<SimilarFailuresSearchResponse>("/api/similar-failures/search", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  indexKnowledgeGraph: (documentId?: string | null, forceRebuild = true) =>
    apiFetch("/api/kg/index", {
      method: "POST",
      body: JSON.stringify({
        document_id: documentId || null,
        force_rebuild: forceRebuild,
      }),
    }),
  getKnowledgeGraph: (mission?: string, entityType?: string) => {
    const params = new URLSearchParams();
    if (mission) params.set("mission", mission);
    if (entityType) params.set("entity_type", entityType);
    const qs = params.toString();
    return apiFetch<KGGraphResponse>(`/api/kg/graph${qs ? `?${qs}` : ""}`);
  },
  queryKnowledgeGraph: (query: string, mission?: string | null) =>
    apiFetch<KGQueryResponse>("/api/kg/query", {
      method: "POST",
      body: JSON.stringify({ query, mission: mission || null }),
    }),
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
  login: (email: string, password: string) =>
    apiFetch<TokenResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => apiFetch<AuthUser>("/api/auth/me"),
  listAdminUsers: () => apiFetch<AdminUserOut[]>("/api/admin/users"),
  updateUserRole: (userId: string, role: "admin" | "engineer", isActive?: boolean) =>
    apiFetch<AdminUserOut>(`/api/admin/users/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role, is_active: isActive }),
    }),
  listAuditLogs: (limit = 100) =>
    apiFetch<AuditLogOut[]>(`/api/admin/audit-logs?limit=${limit}`),
  listRetrievalLogs: (limit = 100) =>
    apiFetch<RetrievalLogOut[]>(`/api/admin/retrieval-logs?limit=${limit}`),
  getAdminSettings: () => apiFetch<RuntimeSettingsOut>("/api/admin/settings"),
  updateAdminSettings: (payload: Partial<RuntimeSettingsOut>) =>
    apiFetch<RuntimeSettingsOut>("/api/admin/settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  demoWalkthrough: () => apiFetch<DemoWalkthroughResponse>("/api/demo/walkthrough"),
  demoPrewarm: () =>
    apiFetch<DemoPrewarmResponse>("/api/demo/prewarm", { method: "POST" }),
  demoAsk: (payload: {
    query: string;
    mission?: string | null;
    selector_mode?: string | null;
    use_cache?: boolean;
  }) =>
    apiFetch<DemoAskResponse>("/api/demo/ask", {
      method: "POST",
      body: JSON.stringify({ ...payload, use_cache: payload.use_cache ?? true }),
    }),
  documentPdfUrl: (docId: string) =>
    `${API_BASE_URL}/api/documents/${docId}/file`,
};

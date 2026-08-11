export type User = {
  id: string;
  email: string;
  status: string;
  platform_role: string;
  created_at: string;
};

export type WorkspaceSummary = {
  id: string;
  name: string;
  slug: string;
  status: string;
  role: string;
};

export type Membership = {
  id: string;
  workspace_id: string;
  user_id: string;
  role: string;
  created_at: string;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
};

export type MeResponse = {
  user: User;
  workspaces: WorkspaceSummary[];
  current_workspace: WorkspaceSummary | null;
  membership: Membership | null;
};

export type Workspace = {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_by: string | null;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  role: string | null;
};

export type Member = {
  id: string;
  user_id: string;
  email: string | null;
  role: string;
  created_at: string;
};

export type WorkspaceRole = 'owner' | 'admin' | 'member';

export type DocumentSummary = {
  id: string;
  title: string;
  original_filename: string;
  status: string;
  page_count: number;
  byte_size: number | null;
  mime_type: string | null;
  processed_pages: number;
  failed_pages: number;
  current_stage: string | null;
  progress: number;
  failure_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
};

export type DocumentDetail = DocumentSummary & {
  sha256: string;
  mime_type: string;
  job_id: string | null;
};

export type Citation = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  page: number;
  snippet: string;
};

export type QueryResponse = {
  answer: string;
  insufficient_context: boolean;
  citations: Citation[];
  model: string;
  general_answer: string | null;
  used_general_knowledge: boolean;
  general_model: string | null;
};

/** Phase 3A/3C Expert types. */
export type ExpertType = 'workspace' | 'platform';
export type ExpertOwnership = 'workspace' | 'platform';

export type ExpertRagConfig = {
  top_k?: number;
  rerank_top_n?: number;
  similarity_threshold?: number;
};

export type Expert = {
  id: string;
  type: ExpertType;
  ownership: ExpertOwnership;
  workspace_id: string | null;
  name: string;
  description: string | null;
  icon_url: string | null;
  /** Null for platform experts. */
  system_instructions: string | null;
  /** Null for platform experts. */
  rag_config: ExpertRagConfig | null;
  status: string;
  visibility: string;
  availability_mode: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  knowledge_document_count: number;
};

export type ExpertDocumentLink = {
  id: string;
  expert_id: string;
  document_id: string;
  source_id: string | null;
  created_at: string;
};

/** Enriched knowledge item returned by GET /api/experts/{id}/documents (Phase 3C). */
export type ExpertKnowledgeItem = {
  id: string;
  expert_id: string;
  document_id: string;
  source_id: string | null;
  created_at: string;
  title: string;
  original_filename: string;
  status: string;
  mime_type: string | null;
  byte_size: number | null;
  page_count: number | null;
  failure_reason: string | null;
  source_type: string | null;
  processed_pages?: number;
  failed_pages?: number;
  current_stage?: string | null;
  /** 0–1 ingestion progress from latest job. */
  progress?: number;
};

export type ExpertUploadResponse = {
  expert_id: string;
  source_id: string;
  document_id: string;
  status: string;
  mime_type: string | null;
  page_count: number | null;
  reused: boolean;
};

export type ExpertSource = {
  id: string;
  expert_id: string;
  type: string;
  name: string | null;
  status: string;
  config: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

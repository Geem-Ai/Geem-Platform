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

export type DocumentExpertRef = {
  id: string;
  name: string;
};

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
  experts?: DocumentExpertRef[];
};

export type DocumentListPage = {
  items: DocumentSummary[];
  total: number;
  limit: number;
  offset: number;
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
  /** ``rag`` (default) or ``general`` (Geem General LLM-only). */
  knowledge_mode?: 'rag' | 'general' | string;
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
  /** Null while a connector source is queued and no Document exists yet. */
  document_id: string | null;
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

/** Phase 4 — Conversation persistence + Chat UX. */
export type ConversationExpertSummary = {
  id: string;
  type: string;
  ownership: string;
  name: string;
  description: string | null;
  icon_url: string | null;
  status: string;
  visibility: string;
  knowledge_mode?: 'rag' | 'general' | string;
};

export type MessageRole = 'user' | 'assistant' | 'system';
export type MessageStatus =
  | 'pending'
  | 'streaming'
  | 'completed'
  | 'cancelled'
  | 'failed';

export type MessagePreview = {
  id: string;
  role: MessageRole | string;
  content: string;
  created_at: string;
};

export type Conversation = {
  id: string;
  workspace_id: string;
  expert_id: string;
  user_id: string;
  title: string | null;
  is_pinned: boolean;
  pinned_at: string | null;
  is_favorite?: boolean;
  favorited_at?: string | null;
  created_at: string;
  updated_at: string;
  expert: ConversationExpertSummary | null;
  last_message: MessagePreview | null;
};

export type ConversationMessage = {
  id: string;
  conversation_id: string;
  role: MessageRole | string;
  content: string;
  citations: Citation[];
  status: MessageStatus | string;
  usage_event_id: string | null;
  created_at: string;
  updated_at: string;
};

/** SSE payloads from ChatOrchestrator (Phase 4B). */
export type ChatMessageStartEvent = {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  /** @deprecated Prefer the post-turn ``title`` SSE event (LLM-generated). */
  title?: string;
};

export type ChatTitleEvent = {
  conversation_id: string;
  title: string;
};

export type ChatMessageCompleteEvent = {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  status: MessageStatus | string;
  citations: Citation[];
};

export type ChatFinalEvent = {
  answer?: string;
  citations?: Citation[];
  insufficient_context?: boolean;
  conversation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  status?: MessageStatus | string;
};

export type ChatStreamErrorEvent = {
  error?: string;
  message?: string;
  conversation_id?: string;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  status?: MessageStatus | string;
};

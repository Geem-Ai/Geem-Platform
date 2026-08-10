const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export type DocumentSummary = {
  id: string;
  title: string;
  original_filename: string;
  status: string;
  page_count: number;
  processed_pages: number;
  failed_pages: number;
  current_stage: string | null;
  progress: number;
  failure_reason: string | null;
  created_at?: string | null;
  completed_at?: string | null;
};

export type DocumentDetail = DocumentSummary & {
  sha256: string;
  mime_type: string;
  job_id: string | null;
  failed_page_details: Array<{
    page_number: number;
    last_error: string | null;
    attempt_count: number;
  }>;
  debug_pages?: Array<{
    page_number: number;
    status: string;
    text_length: number | null;
    arabic_ratio: number | null;
    canonical_text: string | null;
    last_error: string | null;
  }> | null;
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
};

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.message || body.error || message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export async function listDocuments(): Promise<DocumentSummary[]> {
  const res = await fetch(`${API_URL}/api/documents`);
  return handle(res);
}

export async function getDocument(id: string, debug = false): Promise<DocumentDetail> {
  const res = await fetch(`${API_URL}/api/documents/${id}?debug=${debug ? "true" : "false"}`);
  return handle(res);
}

export async function uploadDocument(file: File, title?: string): Promise<{ id: string; status: string; page_count: number }> {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  const res = await fetch(`${API_URL}/api/documents`, { method: "POST", body: form });
  return handle(res);
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/documents/${id}`, { method: "DELETE" });
  await handle(res);
}

export async function reprocessDocument(id: string, mode: "failed_pages" | "full"): Promise<void> {
  const res = await fetch(`${API_URL}/api/documents/${id}/reprocess`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  await handle(res);
}

export async function queryDocuments(
  question: string,
  documentIds?: string[],
): Promise<QueryResponse> {
  const res = await fetch(`${API_URL}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      document_ids: documentIds?.length ? documentIds : undefined,
    }),
  });
  return handle(res);
}

export type QueryStreamHandlers = {
  onStatus?: (stage: string) => void;
  onToken?: (text: string) => void;
  onReplace?: (text: string) => void;
  onFinal?: (res: QueryResponse) => void;
  onError?: (message: string) => void;
};

function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of block.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) return null;
  return { event, data: dataLines.join("\n") };
}

export async function queryDocumentsStream(
  question: string,
  documentIds: string[] | undefined,
  handlers: QueryStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      question,
      document_ids: documentIds?.length ? documentIds : undefined,
    }),
    signal,
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.message || body.error || message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }

  if (!res.body) {
    throw new Error("Streaming is not supported in this browser");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawFinal = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const parsed = parseSseBlock(block);
      if (!parsed) continue;

      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(parsed.data) as Record<string, unknown>;
      } catch {
        continue;
      }

      if (parsed.event === "status") {
        handlers.onStatus?.(String(payload.stage || ""));
      } else if (parsed.event === "token") {
        handlers.onToken?.(String(payload.text || ""));
      } else if (parsed.event === "replace") {
        handlers.onReplace?.(String(payload.text || ""));
      } else if (parsed.event === "final") {
        sawFinal = true;
        handlers.onFinal?.(payload as unknown as QueryResponse);
      } else if (parsed.event === "error") {
        throw new Error(String(payload.message || payload.error || "Query failed"));
      }
    }
  }

  if (!sawFinal) {
    handlers.onError?.("Stream ended before a final answer");
    throw new Error("Stream ended before a final answer");
  }
}

export function documentFileUrl(id: string, page?: number): string {
  const base = `${API_URL}/api/documents/${id}/file`;
  return page ? `${base}#page=${page}` : base;
}

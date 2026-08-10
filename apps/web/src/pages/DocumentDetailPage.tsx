import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  DocumentDetail,
  deleteDocument,
  documentFileUrl,
  getDocument,
  reprocessDocument,
} from "../api";

export default function DocumentDetailPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const page = params.get("page");
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [debug, setDebug] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getDocument(id, debug);
        if (!cancelled) {
          setDoc(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [id, debug]);

  useEffect(() => {
    if (id && page) {
      window.open(documentFileUrl(id, Number(page)), "_blank");
    }
  }, [id, page]);

  if (!id) return <div className="error">Missing document id</div>;
  if (error) return <div className="error">{error}</div>;
  if (!doc) return <p className="muted">Loading…</p>;

  return (
    <div className="stack">
      <Link to="/">← Documents</Link>
      <h1 dir="auto">{doc.title}</h1>
      <div className="panel stack">
        <div className="row">
          <span className={`badge ${doc.status}`}>{doc.status}</span>
          <span className="muted">
            {doc.processed_pages}/{doc.page_count} pages
          </span>
          {doc.current_stage && <span className="muted">{doc.current_stage}</span>}
        </div>
        <div className="progress">
          <span style={{ width: `${Math.round(doc.progress * 100)}%` }} />
        </div>
        {doc.failure_reason && <div className="error">{doc.failure_reason}</div>}
        <div className="row">
          <a className="button" href={documentFileUrl(doc.id)} target="_blank" rel="noreferrer">
            Open original PDF
          </a>
          <button type="button" className="secondary" onClick={() => void reprocessDocument(doc.id, "failed_pages")}>
            Reprocess failed pages
          </button>
          <button type="button" className="secondary" onClick={() => void reprocessDocument(doc.id, "full")}>
            Full reprocess
          </button>
          <button
            type="button"
            className="danger"
            onClick={() => {
              if (confirm("Delete document?")) void deleteDocument(doc.id).then(() => (window.location.href = "/"));
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {doc.failed_page_details.length > 0 && (
        <div className="panel">
          <h2>Failed pages</h2>
          <ul>
            {doc.failed_page_details.map((p) => (
              <li key={p.page_number}>
                Page {p.page_number} (attempts {p.attempt_count}): {p.last_error}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel stack">
        <label className="row">
          <input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} />
          Show extracted page text (debug)
        </label>
        {debug &&
          doc.debug_pages?.map((p) => (
            <div key={p.page_number}>
              <h3>
                Page {p.page_number} — {p.status}
              </h3>
              {p.last_error && <div className="error">{p.last_error}</div>}
              <pre dir="auto" style={{ whiteSpace: "pre-wrap" }}>
                {p.canonical_text || "(empty)"}
              </pre>
            </div>
          ))}
      </div>
    </div>
  );
}

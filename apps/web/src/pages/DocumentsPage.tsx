import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  DocumentSummary,
  deleteDocument,
  documentFileUrl,
  listDocuments,
  reprocessDocument,
  uploadDocument,
} from "../api";

function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${status}`}>{status}</span>;
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listDocuments();
      setDocs(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(id);
  }, [refresh]);

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadDocument(file);
      setFile(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="stack">
      <h1>Documents</h1>
      <p className="muted">Upload Arabic or mixed PDFs. Processing runs asynchronously.</p>

      <form className="panel stack" onSubmit={onUpload}>
        <label>
          PDF file
          <input
            type="file"
            accept="application/pdf,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <div className="row">
          <button type="submit" disabled={!file || uploading}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
      </form>

      {error && <div className="error">{error}</div>}

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Pages</th>
              <th>Progress</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>
                  <Link to={`/document/${d.id}`}>{d.title}</Link>
                </td>
                <td>
                  <StatusBadge status={d.status} />
                  {d.current_stage && <div className="muted">{d.current_stage}</div>}
                </td>
                <td>
                  {d.processed_pages}/{d.page_count}
                  {d.failed_pages > 0 && (
                    <div className="muted">{d.failed_pages} failed</div>
                  )}
                </td>
                <td>
                  <div className="progress" title={`${Math.round(d.progress * 100)}%`}>
                    <span style={{ width: `${Math.round(d.progress * 100)}%` }} />
                  </div>
                </td>
                <td>
                  <div className="row">
                    <a className="button secondary" href={documentFileUrl(d.id)} target="_blank" rel="noreferrer">
                      Open PDF
                    </a>
                    {d.status === "failed" && (
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void reprocessDocument(d.id, "failed_pages").then(refresh)}
                      >
                        Reprocess
                      </button>
                    )}
                    <button
                      type="button"
                      className="danger"
                      onClick={() => {
                        if (confirm("Delete this document and all derived data?")) {
                          void deleteDocument(d.id).then(refresh);
                        }
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {docs.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  No documents yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

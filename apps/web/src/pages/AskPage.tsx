import { FormEvent, useEffect, useState } from "react";
import {
  Citation,
  DocumentSummary,
  documentFileUrl,
  listDocuments,
  queryDocuments,
} from "../api";

export default function AskPage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [insufficient, setInsufficient] = useState(false);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [model, setModel] = useState<string | null>(null);

  useEffect(() => {
    void listDocuments().then((d) => setDocs(d.filter((x) => x.status === "ready")));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setAnswer(null);
    setCitations([]);
    try {
      const res = await queryDocuments(question, selected);
      setAnswer(res.answer);
      setInsufficient(res.insufficient_context);
      setCitations(res.citations);
      setModel(res.model);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <h1>Ask</h1>
      <p className="muted">Ask in Arabic or English. Answers cite exact document pages.</p>

      <form className="panel stack" onSubmit={onSubmit}>
        <label>
          Documents
          <select
            multiple
            value={selected}
            onChange={(e) =>
              setSelected(Array.from(e.target.selectedOptions).map((o) => o.value))
            }
            style={{ minHeight: 100 }}
          >
            {docs.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </select>
          <span className="muted">Leave empty to search all ready documents.</span>
        </label>
        <label>
          Question
          <textarea
            dir="auto"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="ما هي شروط إنهاء العقد؟"
          />
        </label>
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "Searching…" : "Ask"}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {answer !== null && (
        <div className="panel stack">
          <h2>Answer</h2>
          {insufficient && (
            <p className="muted">Insufficient context in the available documents.</p>
          )}
          <div className="answer" dir="auto">
            {answer}
          </div>
          {model && <p className="muted">Model: {model}</p>}
          <h2>Citations</h2>
          <div className="citations">
            {citations.length === 0 && <p className="muted">No citations.</p>}
            {citations.map((c) => (
              <div className="citation" key={c.chunk_id}>
                <a href={documentFileUrl(c.document_id, c.page)} target="_blank" rel="noreferrer">
                  {c.document_title} — page {c.page}
                </a>
                <div dir="auto" className="muted">
                  {c.snippet}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, ErrorBox, Expandable, Loading, Notice, PageHeader, Pill, fmtDate } from "../ui.jsx";

const AI_UNAVAILABLE_MESSAGE = "AI-generated explanations are temporarily unavailable. Your rule-based assessment and findings are still available.";

const EV = {
  present: { label: "Evidence found", color: "#15803d", bg: "#dcfce7" },
  not_provided: { label: "Not provided", color: "#4b5563", bg: "#e5e7eb" },
  explicit_negative: { label: "States absent / invalid", color: "#b91c1c", bg: "#fee2e2" },
  mentioned: { label: "Mentioned only", color: "#b45309", bg: "#fef3c7" },
};

function DocumentDetail({ id }) {
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { api.document(id).then(setDoc).catch(setError); }, [id]);
  if (error) return <ErrorBox error={error} />;
  if (!doc) return <Loading />;
  const a = doc.analysis;
  const f = a ? a.facts : null;
  const topics = f ? Object.entries(f.topics).filter(([, v]) => v.status !== "none") : [];
  return (
    <div className="stack">
      {f && (
        <div>
          <h3>Extracted information <span className="tag">rule-based, traceable to the document</span></h3>
          <dl className="kv" style={{ marginTop: ".5rem" }}>
            <dt>Business name</dt><dd>{f.business_name || "Not found"}</dd>
            <dt>Location</dt><dd>{f.location || "Not found"}</dd>
            <dt>Industry</dt><dd>{f.industry || "Not found"}</dd>
            <dt>Reporting period</dt><dd>{f.reporting_period || "Not found"}</dd>
            {Object.entries(f.quantities || {}).map(([k, v]) => (<React.Fragment key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{v}</dd></React.Fragment>))}
            {f.air_sources.length > 0 && (<><dt>Emission sources</dt><dd>{f.air_sources.map((s) => s.line).join("; ")}</dd></>)}
          </dl>
        </div>
      )}
      {topics.length > 0 && (
        <div>
          <h3>Environmental records and evidence</h3>
          {topics.map(([key, v]) => (
            <div key={key} style={{ margin: ".6rem 0" }}>
              <div className="row gap"><b>{key.replace(/_/g, " ")}</b><Pill {...EV[v.status]}>{EV[v.status].label}</Pill>
                {v.details && v.details.valid_until && <span className="small muted">valid until {v.details.valid_until}{v.details.expired ? " (expired)" : ""}</span>}</div>
              {v.evidence.map((e, i) => <div className="evidence" key={i}>p.{e.page}: {e.line}</div>)}
            </div>
          ))}
        </div>
      )}
      <div>
        <h3>AI analysis</h3>
        {a && a.ai_analysis ? (
          <div className="ai-box"><div className="ai-label">AI-generated interpretation - not verified</div>{a.ai_analysis}</div>
        ) : (
          <p className="muted small">
            {a && a.ai_status === "unavailable" ? AI_UNAVAILABLE_MESSAGE : "AI analysis was not requested for this document."}
          </p>
        )}
      </div>
      <Expandable header={<b>Extracted PDF text ({doc.chars.toLocaleString()} characters)</b>}>
        <textarea readOnly rows={12} value={doc.text || ""} style={{ fontFamily: "Consolas, monospace", fontSize: ".8rem" }} />
      </Expandable>
    </div>
  );
}

export default function Documents({ active, go }) {
  const [docs, setDocs] = useState(null);
  const [error, setError] = useState(null);
  const [useAi, setUseAi] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState([]);
  const [over, setOver] = useState(false);
  const input = useRef(null);

  const load = useCallback(async () => {
    if (!active) return;
    try { setDocs(await api.documents(active.id)); setError(null); } catch (e) { setError(e); }
  }, [active]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.status().then((s) => setAiAvailable(s.llm.available)).catch(() => {}); }, []);

  if (!active) {
    return (<><PageHeader title="Documents" subtitle="Step 2 - upload and analyse environmental PDFs" />
      <Empty title="Select a business first" action={<button className="btn" onClick={() => go("profile")}>Go to Business Profile</button>}>Documents are linked to a business.</Empty></>);
  }

  const upload = async (files) => {
    const list = Array.from(files || []);
    if (!list.length) return;
    setBusy(true);
    const out = [];
    for (const file of list) {
      try {
        const d = await api.uploadDocument(file, active.id, useAi);
        out.push({ name: file.name, ok: true, doc: d });
      } catch (e) {
        out.push({ name: file.name, ok: false, message: e.message });
      }
    }
    setResults(out);
    setBusy(false);
    if (input.current) input.current.value = "";
    load();
  };

  const remove = async (d) => {
    if (!window.confirm(`Delete ${d.filename}?`)) return;
    try { await api.deleteDocument(d.id); load(); } catch (e) { setError(e); }
  };

  return (
    <>
      <PageHeader title="Documents" subtitle={`Step 2 - environmental documents for ${active.company}`}>
        <button className="btn" onClick={() => go("regulations")} disabled={!docs || docs.length === 0}>Next: regulations</button>
      </PageHeader>

      <Card title="Upload PDF documents">
        <div className={`dropzone ${over ? "over" : ""}`} onClick={() => input.current && input.current.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files); }}>
          <b>Drop PDFs here or click to browse</b>
          <p className="muted small" style={{ margin: ".3rem 0 0" }}>Permits, consent orders, monitoring reports, waste records. Text-based PDFs only (scanned images need OCR).</p>
          <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => upload(e.target.files)} />
        </div>
        <label className="check-row">
          <input type="checkbox" checked={useAi} disabled={!aiAvailable} onChange={(e) => setUseAi(e.target.checked)} />
          <span>Also run AI analysis {!aiAvailable && <span className="muted small">(unavailable: add OPENROUTER_API_KEY to .env and restart the backend)</span>}</span>
        </label>
        {busy && <Loading text="Reading and analysing documents..." />}
        {results.map((r, i) => (
          <Notice key={i} tone={r.ok ? "ok" : "warn"}>
            <b>{r.name}</b>: {r.ok ? `analysed (${r.doc.pages} page${r.doc.pages === 1 ? "" : "s"}).` : `rejected - ${r.message}`}
          </Notice>
        ))}
      </Card>

      <ErrorBox error={error} onRetry={load} />
      <h2 style={{ margin: "1.4rem 0 .6rem" }}>Uploaded documents</h2>
      {!docs ? <Loading /> : docs.length === 0 ? (
        <Empty title="No documents yet">Upload a PDF above. Try the sample record in <code>data/sample_documents</code>.</Empty>
      ) : docs.map((d) => (
        <Expandable key={d.id} header={
          <span className="row gap wrap"><b>{d.filename}</b><span className="muted small">{d.pages} pages · {fmtDate(d.uploaded_at)}</span>
            {d.analysis && Object.entries(d.analysis.topics_found).slice(0, 4).map(([k, v]) => <Pill key={k} {...EV[v]}>{k}</Pill>)}</span>}>
          <DocumentDetail id={d.id} />
          <div style={{ marginTop: ".8rem" }}><button className="btn btn-danger btn-small" onClick={() => remove(d)}>Delete document</button></div>
        </Expandable>
      ))}
    </>
  );
}

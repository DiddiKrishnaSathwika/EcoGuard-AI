import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, ErrorBox, Expandable, Loading, Notice, PageHeader, Pill, Sources, Tabs, fmtDate } from "../ui.jsx";

const APP_TONE = {
  APPLICABLE: { label: "Applicable", color: "#15803d", bg: "#dcfce7" },
  CONDITIONALLY_APPLICABLE: { label: "Conditionally applicable", color: "#b45309", bg: "#fef3c7" },
  NEEDS_INFORMATION: { label: "Needs information", color: "#b45309", bg: "#fef3c7" },
  NOT_APPLICABLE: { label: "Not applicable", color: "#4b5563", bg: "#e5e7eb" },
};

function Verification({ v }) {
  return (
    <div className="verified-box">
      <b>Verification:</b> section and subject confirmed on {v.verified_on}; <b>not</b> a full-text legal review. {v.method}
    </div>
  );
}

function Requirement({ e, extra }) {
  return (
    <Expandable header={
      <span className="row gap wrap"><b>{e.instrument}</b><span className="tag">{e.citation}</span><span className="grow">{e.title}</span>{extra}</span>}>
      <div className="stack">
        <div><div className="ai-label" style={{ color: "#166534" }}>Curated reference summary (paraphrase, not legal text)</div><p style={{ margin: 0 }}>{e.summary}</p></div>
        <div><b>Evidence expected:</b> {e.evidence_description}</div>
        {e.conditions_to_confirm.length > 0 && <div><b>Confirm:</b><ul className="plain">{e.conditions_to_confirm.map((c) => <li key={c}>{c}</li>)}</ul></div>}
        <div><b>Sources</b><Sources sources={e.sources} /></div>
        <Verification v={e.verification} />
      </div>
    </Expandable>
  );
}

export default function Regulations({ active, go, isAdmin }) {
  const [tab, setTab] = useState("relevant");
  const [kb, setKb] = useState(null);
  const [error, setError] = useState(null);
  const [docs, setDocs] = useState([]);
  const [retrieved, setRetrieved] = useState(null);
  const [busy, setBusy] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState({});

  const load = useCallback(async () => {
    try { setKb(await api.regulations()); setError(null); } catch (e) { setError(e); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (active) api.documents(active.id).then(setDocs).catch(() => setDocs([])); }, [active]);

  const retrieve = async () => {
    setBusy(true); setError(null);
    try { setRetrieved(await api.retrieve(active.id, docs.map((d) => d.id))); } catch (e) { setError(e); }
    setBusy(false);
  };
  const refresh = async (id) => {
    setRefreshMsg({ ...refreshMsg, [id]: "Retrieving..." });
    try { const r = await api.refreshSource(id); setRefreshMsg((m) => ({ ...m, [id]: `Cached (${r.paragraphs} paragraphs). Treated as unverified website content.` })); load(); }
    catch (e) { setRefreshMsg((m) => ({ ...m, [id]: `Failed: ${e.message}` })); }
  };

  if (!kb) return <><PageHeader title="Regulations" />{error ? <ErrorBox error={error} onRetry={load} /> : <Loading />}</>;

  return (
    <>
      <PageHeader title="Regulations" subtitle="Step 3 - regulatory retrieval from the curated knowledge base and registered official sources">
        <button className="btn" onClick={() => go("assessment")}>Next: assessment</button>
      </PageHeader>
      <Notice tone="warn">
        <b>Verified references.</b> Provisions below are curated references with official source links; summaries are paraphrases, not legal text, and amendments were not checked.
      </Notice>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "relevant", label: "Relevant to this business" }, { id: "kb", label: `Knowledge base (${kb.entries.length})` }, { id: "sources", label: "Registered sources" }, { id: "coverage", label: "Coverage limits" }]} />
      <ErrorBox error={error} />

      {tab === "relevant" && (!active ? <Empty title="Select a business first" action={<button className="btn" onClick={() => go("profile")}>Business Profile</button>}>Retrieval uses the business industry, state and declared activities.</Empty> : (
        <>
          <Card title={`Retrieval for ${active.company}`} action={<button className="btn" onClick={retrieve} disabled={busy}>{busy ? "Retrieving..." : "Retrieve regulations"}</button>}>
            <p className="muted" style={{ margin: 0 }}>Uses {active.industry}, {active.state}, declared activities and the content of {docs.length} uploaded document(s).</p>
          </Card>
          {busy && <Loading />}
          {retrieved && (
            <div style={{ marginTop: "1rem" }}>
              <p className="small muted">Method: {retrieved.method === "local_bm25" ? "local BM25 keyword ranking" : "ChromaDB vector search"} {retrieved.note && `· ${retrieved.note}`}</p>
              {retrieved.results.map((r) => (
                <Requirement key={r.requirement_id} e={r.entry} extra={<>
                  <Pill {...APP_TONE[r.applicability.status]}>{APP_TONE[r.applicability.status].label}</Pill>
                  <span className="small muted">relevance {r.score}</span></>} />
              ))}
              <p className="small muted">Applicability reasons are shown in the assessment results.</p>
            </div>
          )}
        </>
      ))}

      {tab === "kb" && kb.entries.map((e) => <Requirement key={e.id} e={e} extra={<Pill color="#166534" bg="#dcfce7">Curated</Pill>} />)}

      {tab === "sources" && (
        <Card title="Registered official sources">
          <p className="muted small">These are the portals in <code>data/source_registry.json</code>. Retrieved website pages are stored as <b>unverified website content</b> and are never used as law or to produce findings. Retrieval needs internet access.</p>
          <div className="table-wrap"><table>
            <thead><tr><th>Source</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {kb.sources.sources.map((s) => (
                <tr key={s.source_id}>
                  <td><b>{s.authority}</b><div className="small"><a href={s.url} target="_blank" rel="noreferrer">{s.url}</a></div><div className="small muted">{s.category}</div></td>
                  <td className="small">{s.cached ? <>Cached {fmtDate(s.retrieved_at)}<br />{s.validation_status}</> : "Not retrieved"}<br /><span className="muted">{s.note}</span>{refreshMsg[s.source_id] && <div><b>{refreshMsg[s.source_id]}</b></div>}</td>
                  <td>{isAdmin
                    ? <button className="btn btn-ghost btn-small" onClick={() => refresh(s.source_id)}>Retrieve now</button>
                    : <span className="small muted">Administrator only</span>}</td>
                </tr>
              ))}
            </tbody></table></div>
          <p className="small muted">Registry validation: {kb.sources.registry_validation.valid ? "valid" : kb.sources.registry_validation.errors.join("; ")}</p>
        </Card>
      )}

      {tab === "coverage" && (
        <Card title="What this knowledge base does NOT cover">
          <p>{kb.disclaimer}</p>
          <ul className="plain">{kb.coverage_limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          <p className="small muted">Curated on {kb.curated_on} · Jurisdiction: {kb.jurisdiction}</p>
        </Card>
      )}
    </>
  );
}

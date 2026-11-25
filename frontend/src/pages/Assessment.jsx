import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Card, Donut, Empty, ErrorBox, Expandable, Loading, Notice, OVERALL_TONE, PageHeader, Pill, RiskBadge, Sources, StatusBadge, STATUS, Tabs, fmtDate } from "../ui.jsx";

const APP_LABEL = { APPLICABLE: "Applicable", CONDITIONALLY_APPLICABLE: "Conditionally applicable", NEEDS_INFORMATION: "Needs information", NOT_APPLICABLE: "Not applicable" };
const PRIORITY_TONE = { 1: ["#b91c1c", "#fee2e2"], 2: ["#b45309", "#fef3c7"], 3: ["#15803d", "#dcfce7"] };
const AI_UNAVAILABLE_MESSAGE = "AI-generated explanations are temporarily unavailable. Your rule-based assessment and findings are still available.";

function Summary({ a }) {
  const r = a.result;
  const o = r.overall;
  const segments = Object.keys(STATUS).map((k) => ({ label: STATUS[k].label, value: o.counts[k], color: STATUS[k].color }));
  return (
    <div className="stack">
      <div className="card overall" style={{ borderLeftColor: OVERALL_TONE[o.status] }}>
        <div className="row gap wrap"><h2 style={{ margin: 0 }}>{o.label}</h2><RiskBadge level={o.risk_level} /></div>
        <p style={{ margin: ".4rem 0 0" }}>{o.summary}</p>
        <p className="small muted" style={{ margin: ".4rem 0 0" }}>Assessment date {r.assessment_date} · {r.documents_analysed} document(s) analysed · {o.not_applicable} requirement(s) not applicable</p>
      </div>
      <div className="grid grid-2">
        <Card title="Status distribution"><Donut segments={segments} centerLabel="requirements" /></Card>
        <Card title="Integrity review">
          <div className="row gap"><Pill color={r.ethics_review.passed ? "#15803d" : "#b91c1c"} bg={r.ethics_review.passed ? "#dcfce7" : "#fee2e2"}>{r.ethics_review.passed ? "Passed" : "Issues found"}</Pill></div>
          <ul className="plain small">{r.ethics_review.checks.map((c) => <li key={c}>{c}</li>)}</ul>
          {r.ethics_review.issues.map((i) => <Notice key={i} tone="warn">{i}</Notice>)}
          {r.ethics_review.notes.map((i) => <Notice key={i} tone="warn">{i}</Notice>)}
        </Card>
      </div>
      <AiBlock ai={r.ai} />
      <Card title="Limitations">
        <ul className="plain small">{r.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        <Expandable header={<b>Regulatory coverage limits</b>}><ul className="plain small">{r.regulatory_coverage.limitations.map((l) => <li key={l}>{l}</li>)}</ul></Expandable>
      </Card>
    </div>
  );
}

function AiBlock({ ai }) {
  if (!ai?.requested) return <Notice tone="info">AI explanations were not requested. All statuses come from the deterministic evidence rule engine.</Notice>;
  return (
    <Card title="AI-generated explanations">
      {ai.narrative && <div className="ai-box"><div className="ai-label">AI-generated narrative - not verified legal advice</div>{ai.narrative}</div>}
      {ai.interpretations.map((item) => <div key={item.instrument} className="ai-box" style={{ marginTop: ".6rem" }}><div className="ai-label">AI-generated regulatory explanation: {item.instrument}</div>{item.text}</div>)}
      {ai.suppressed_reason && <Notice tone="warn">{ai.suppressed_reason}</Notice>}
      {(ai.unavailable || ai.errors?.length > 0) && <Notice tone="warn">{AI_UNAVAILABLE_MESSAGE}</Notice>}
      <p className="small muted">{ai.label}</p>
    </Card>
  );
}

function Findings({ r }) {
  if (r.findings.length === 0) return <Empty title="No applicable requirements">None of the knowledge-base requirements apply to the declared activities.</Empty>;
  return r.findings.map((f) => (
    <Expandable key={f.requirement_id} defaultOpen={f.status === "NON_COMPLIANT"} header={
      <span className="row gap wrap"><b>{f.title}</b><span className="tag">{f.instrument.split(",")[0]} · {f.citation}</span><span className="grow" /><StatusBadge status={f.status} /><RiskBadge level={f.risk_level} /></span>}>
      <div className="stack">
        <p style={{ margin: 0 }}><b>Why this status:</b> {f.explanation}</p>
        <div>
          <b>Evidence from documents</b>
          {f.evidence.length === 0 ? <p className="muted small" style={{ margin: ".2rem 0" }}>No evidence found in the submitted documents.</p> : f.evidence.map((e, i) => <div className="evidence" key={i}>{e.document ? `${e.document} · ` : ""}p.{e.page}: {e.line}</div>)}
        </div>
        {f.missing_information.length > 0 && <div><b>Missing:</b><ul className="plain">{f.missing_information.map((m) => <li key={m}>{m}</li>)}</ul></div>}
        {f.notes.map((n) => <Notice key={n} tone="warn">{n}</Notice>)}
        <div className="verified-box">
          <b>Regulatory reference (curated summary, not legal text):</b> {f.summary}
          <div style={{ marginTop: ".4rem" }}><Sources sources={f.references} /></div>
          <p className="small muted" style={{ margin: ".4rem 0 0" }}>{f.amendment_check.message}</p>
        </div>
      </div>
    </Expandable>
  ));
}

function Recommendations({ r }) {
  if (r.recommendations.length === 0) return <Empty title="No corrective actions needed">All assessed requirements are supported by evidence.</Empty>;
  return r.recommendations.map((rec) => (
    <div className="card" key={rec.id} style={{ marginBottom: ".8rem" }}>
      <div className="row gap wrap">
        <Pill color={PRIORITY_TONE[rec.priority][0]} bg={PRIORITY_TONE[rec.priority][1]}>{rec.priority_label}</Pill>
        <b className="grow">{rec.title}</b><RiskBadge level={rec.risk_level} />
      </div>
      <p style={{ margin: ".6rem 0 .3rem" }}><b>Why:</b> {rec.why}</p>
      <div><b>Actions:</b><ul className="plain">{rec.actions.map((x) => <li key={x}>{x}</li>)}</ul></div>
      <p className="small muted" style={{ margin: 0 }}>Suggested timeframe: {rec.suggested_timeframe}{rec.references.length ? ` · Basis: ${rec.references.join("; ")}` : ""}</p>
    </div>
  ));
}

function RegulationsTab({ r }) {
  const app = Object.fromEntries(r.applicability.map((x) => [x.requirement_id, x]));
  return (
    <>
      <p className="small muted">Retrieval method: {r.retrieval.method}{r.retrieval.note ? ` · ${r.retrieval.note}` : ""}. Curated {r.regulatory_coverage.curated_on}.</p>
      {r.regulations.map((g) => (
        <Expandable key={g.id} header={<span className="row gap wrap"><b>{g.instrument.split(",")[0]}</b><span className="tag">{g.citation}</span><span className="grow">{g.title}</span><Pill color="#374151" bg="#e5e7eb">{APP_LABEL[app[g.id].status]}</Pill></span>}>
          <p><b>Applicability:</b> {app[g.id].reason}</p>
          {app[g.id].discrepancy && <Notice tone="warn">{app[g.id].discrepancy}</Notice>}
          {app[g.id].conditions_to_confirm.length > 0 && <ul className="plain">{app[g.id].conditions_to_confirm.map((c) => <li key={c}>{c}</li>)}</ul>}
          <div className="verified-box"><b>Summary (paraphrase):</b> {g.summary}<Sources sources={g.sources} /></div>
        </Expandable>
      ))}
    </>
  );
}

function Results({ a, onDownload }) {
  const [tab, setTab] = useState("summary");
  const r = a.result;
  return (
    <>
      <div className="row gap wrap" style={{ justifyContent: "space-between", margin: "1.4rem 0 .6rem" }}>
        <h2 style={{ margin: 0 }}>Results for {r.profile.company} <span className="muted small">#{a.id} · {fmtDate(a.created_at)}</span></h2>
        <button className="btn" onClick={() => onDownload(a.id)}>Download PDF report</button>
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "summary", label: "Overall" }, { id: "findings", label: `Findings (${r.findings.length})` }, { id: "recs", label: `Recommendations (${r.recommendations.length})` }, { id: "regs", label: "Regulations" }, { id: "trace", label: "Process" }]} />
      {tab === "summary" && <Summary a={a} />}
      {tab === "findings" && <Findings r={r} />}
      {tab === "recs" && <Recommendations r={r} />}
      {tab === "regs" && <RegulationsTab r={r} />}
      {tab === "trace" && <Card title={`Workflow (${r.workflow_engine})`}><ol>{r.trace.map((t) => <li key={t}>{t}</li>)}</ol></Card>}
    </>
  );
}

export default function Assessment({ active, go, params }) {
  const [docs, setDocs] = useState([]);
  const [selected, setSelected] = useState([]);
  const [useAi, setUseAi] = useState(false);
  const [aiAvailable, setAiAvailable] = useState(false);
  const [history, setHistory] = useState(null);
  const [current, setCurrent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const resultsRef = useRef(null);

  const loadHistory = useCallback(async () => { try { setHistory(await api.assessments()); } catch (e) { setError(e); } }, []);
  const open = useCallback(async (id) => {
    setError(null);
    try { setCurrent(await api.assessment(id)); } catch (e) { setError(e); }
  }, []);

  useEffect(() => {
    loadHistory();
    api.status().then((status) => setAiAvailable(status.llm.available)).catch(setError);
  }, [loadHistory]);
  useEffect(() => { if (params && params.assessmentId) open(params.assessmentId); }, [params, open]);
  useEffect(() => {
    if (!active) return;
    api.documents(active.id).then((d) => { setDocs(d); setSelected(d.map((x) => x.id)); }).catch(setError);
  }, [active]);
  useEffect(() => {
    if (current) resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [current]);

  const run = async () => {
    setBusy(true); setError(null);
    try {
      const a = await api.createAssessment(active.id, selected, useAi);
      setCurrent(a);
      loadHistory();
    } catch (e) { setError(e); }
    setBusy(false);
  };
  const downloadReport = async (id) => {
    try { await api.downloadReport(id); } catch (e) { setError(e); }
  };
  const toggle = (id) => setSelected(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);

  return (
    <>
      <PageHeader title="Assessment & Results" subtitle="Step 4 - compare the business and its documents against applicable regulations" />
      <ErrorBox error={error} />
      <div className="grid grid-main">
        <Card title="Run a new assessment">
          {!active ? (
            <Empty title="Select a business first" action={<button className="btn" onClick={() => go("profile")}>Business Profile</button>}>An assessment needs a business profile.</Empty>
          ) : (
            <div className="stack">
              <div><b>{active.company}</b> <span className="muted">· {active.industry} · {active.state}</span></div>
              <div>
                <b>Documents to include</b>
                {docs.length === 0 ? (
                  <Notice tone="warn">No documents uploaded. You can still run the assessment; every requirement will then be reported as <b>insufficient evidence</b>. <button className="btn btn-small btn-ghost" onClick={() => go("documents")}>Upload documents</button></Notice>
                ) : docs.map((d) => (
                  <label className="check-row" key={d.id}><input type="checkbox" checked={selected.includes(d.id)} onChange={() => toggle(d.id)} /><span>{d.filename} <span className="muted small">({d.pages} pages)</span></span></label>
                ))}
              </div>
              <label className="check-row">
                <input type="checkbox" checked={useAi} disabled={!aiAvailable} onChange={(e) => setUseAi(e.target.checked)} />
                <span>Add AI-generated narrative and regulatory explanations {!aiAvailable && <span className="muted small">(unavailable: add OPENROUTER_API_KEY to .env and restart the backend)</span>}</span>
              </label>
              <div><button className="btn" onClick={run} disabled={busy}>{busy ? "Running assessment..." : "Run assessment"}</button></div>
              {busy && <Loading text="Analysing documents, retrieving regulations, assessing compliance..." />}
            </div>
          )}
        </Card>
        <Card title="History">
          {!history ? <Loading /> : history.length === 0 ? <p className="muted">No assessments yet.</p> : (
            <div className="history">
              {history.map((h) => (
                <button key={h.id} className={current && current.id === h.id ? "active" : ""} onClick={() => open(h.id)}>
                  <b>#{h.id} {h.company}</b><br /><span className="small muted">{fmtDate(h.created_at)}</span> <RiskBadge level={h.risk_level} />
                </button>
              ))}
            </div>
          )}
        </Card>
      </div>
      {current ? <div ref={resultsRef}><Results a={current} onDownload={downloadReport} /></div> : <div style={{ marginTop: "1rem" }}><Empty title="No results to show">Run an assessment or pick one from the history. Results are never shown unless an assessment has actually been run.</Empty></div>}
    </>
  );
}

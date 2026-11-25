import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { BarList, Card, Donut, Empty, ErrorBox, Loading, Notice, PageHeader, RiskBadge, Stat, StatusBadge, STATUS, OVERALL_TONE, fmtDate } from "../ui.jsx";

export default function Dashboard({ go }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [d, s] = await Promise.all([api.dashboard(), api.status()]);
      setData(d);
      setStatus(s);
    } catch (e) { setError(e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (error) return <><PageHeader title="Dashboard" /><ErrorBox error={error} onRetry={load} /></>;
  if (!data) return <><PageHeader title="Dashboard" /><Loading /></>;

  const latest = data.latest_summary;
  const counts = latest ? latest.overall.counts : null;
  const segments = counts ? Object.keys(STATUS).map((k) => ({ label: STATUS[k].label, value: counts[k], color: STATUS[k].color })) : [];
  const riskTally = { High: 0, Medium: 0, Low: 0 };
  if (latest) latest.top_findings.forEach((f) => { if (riskTally[f.risk_level] !== undefined) riskTally[f.risk_level] += 1; });
  const p = data.latest_profile;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Environmental compliance overview for your business">
        <button className="btn" onClick={() => go(p ? "assessment" : "profile")}>{p ? "Run assessment" : "Add business"}</button>
      </PageHeader>

      {status && !status.llm.available && (
        <Notice tone="warn">
          <b>AI features are off.</b> {status.llm.configured ? "The AI provider is not available." : "No OPENROUTER_API_KEY found in .env."} The
          rule-based assessment, regulatory retrieval, recommendations and PDF reports work without it.
        </Notice>
      )}

      <div className="grid grid-4" style={{ margin: "1rem 0" }}>
        <Stat label="Business profiles" value={data.profiles} />
        <Stat label="Documents uploaded" value={data.documents.total} hint={data.documents.failed ? `${data.documents.failed} failed` : undefined} />
        <Stat label="Pages analysed" value={data.documents.pages} />
        <Stat label="Assessments run" value={data.assessments_total} />
      </div>

      {!p && (
        <Empty title="No business added yet" action={<button className="btn" onClick={() => go("profile")}>Add business information</button>}>
          Start with your business details, then upload environmental documents and run an assessment.
        </Empty>
      )}

      {p && (
        <div className="grid grid-main">
          <Card title="Compliance assessment summary">
            {!latest ? (
              <Empty title="No assessment yet" action={<button className="btn" onClick={() => go("assessment")}>Run first assessment</button>}>
                Upload documents for {p.company} and run an assessment to see results here.
              </Empty>
            ) : (
              <div className="stack">
                <div className="overall card" style={{ borderLeftColor: OVERALL_TONE[latest.overall.status] }}>
                  <b>{latest.company}: {latest.overall.label}</b>
                  <p className="muted" style={{ margin: ".3rem 0 0" }}>{latest.overall.summary}</p>
                </div>
                <div className="grid grid-2">
                  <Donut segments={segments} centerLabel="requirements" />
                  <div>
                    <h3 style={{ marginBottom: ".6rem" }}>Risk indicators</h3>
                    <BarList items={[{ label: "High", value: riskTally.High, color: "#b91c1c" }, { label: "Medium", value: riskTally.Medium, color: "#b45309" }, { label: "Low", value: riskTally.Low, color: "#15803d" }]} />
                    <p className="small muted">Based on the top findings of the latest assessment.</p>
                  </div>
                </div>
                <div>
                  <h3 style={{ marginBottom: ".4rem" }}>Top findings</h3>
                  {latest.top_findings.map((f) => (
                    <div key={f.title} className="row gap" style={{ padding: ".3rem 0", borderBottom: "1px solid #f3f4f6" }}>
                      <span className="grow">{f.title}</span><StatusBadge status={f.status} /> <RiskBadge level={f.risk_level} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          <Card title="Business overview" action={<button className="btn btn-ghost btn-small" onClick={() => go("profile")}>Edit</button>}>
            <dl className="kv">
              <dt>Company</dt><dd><b>{p.company}</b></dd>
              <dt>Industry</dt><dd>{p.industry}</dd>
              <dt>State / UT</dt><dd>{p.state}</dd>
              <dt>Wastewater</dt><dd>{p.wastewater}</dd>
              <dt>Air emissions</dt><dd>{p.air_emissions}</dd>
              <dt>Hazardous waste</dt><dd>{p.hazardous_waste}</dd>
            </dl>
          </Card>
        </div>
      )}

      <Card title="Recent assessment history" className="" action={<button className="btn btn-ghost btn-small" onClick={() => go("reports")}>All reports</button>}>
        {data.recent.length === 0 ? <p className="muted">No assessments yet.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Company</th><th>Date</th><th>Result</th><th>Risk</th></tr></thead>
              <tbody>
                {data.recent.map((a) => (
                  <tr key={a.id} className="click" onClick={() => go("assessment", { assessmentId: a.id })}>
                    <td>{a.id}</td><td>{a.company}</td><td>{fmtDate(a.created_at)}</td>
                    <td>{a.overall_status.replace(/_/g, " ").toLowerCase()}</td><td><RiskBadge level={a.risk_level} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

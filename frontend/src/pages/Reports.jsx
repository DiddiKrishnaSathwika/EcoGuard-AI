import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, Empty, ErrorBox, Loading, PageHeader, RiskBadge, fmtDate } from "../ui.jsx";

export default function Reports({ go }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const load = useCallback(async () => {
    try { setRows(await api.assessments()); setError(null); } catch (e) { setError(e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const remove = async (a) => {
    if (!window.confirm(`Delete assessment #${a.id}?`)) return;
    try { await api.deleteAssessment(a.id); load(); } catch (e) { setError(e); }
  };

  return (
    <>
      <PageHeader title="Reports" subtitle="Step 5 - download PDF compliance reports" />
      <ErrorBox error={error} onRetry={load} />
      {!rows ? <Loading /> : rows.length === 0 ? (
        <Empty title="No reports yet" action={<button className="btn" onClick={() => go("assessment")}>Run an assessment</button>}>A report is available for every completed assessment.</Empty>
      ) : (
        <Card title={`Assessments (${rows.length})`}>
          <div className="table-wrap"><table>
            <thead><tr><th>#</th><th>Company</th><th>Created</th><th>Result</th><th>Risk</th><th></th></tr></thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <td>{a.id}</td><td><b>{a.company}</b></td><td>{fmtDate(a.created_at)}</td>
                  <td>{a.overall_status.replace(/_/g, " ").toLowerCase()}</td><td><RiskBadge level={a.risk_level} /></td>
                  <td className="row gap">
                    <button className="btn btn-small" onClick={() => api.downloadReport(a.id).catch(setError)}>Download PDF</button>
                    <button className="btn btn-ghost btn-small" onClick={() => go("assessment", { assessmentId: a.id })}>View</button>
                    <button className="btn btn-danger btn-small" onClick={() => remove(a)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody></table></div>
          <p className="small muted">Reports include company information, findings with evidence, regulatory references, gaps, prioritised recommendations and the assessment date.</p>
        </Card>
      )}
    </>
  );
}

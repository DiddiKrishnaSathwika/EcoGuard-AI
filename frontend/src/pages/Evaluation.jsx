import React, { useState } from "react";
import { api } from "../api.js";
import { Card, Empty, ErrorBox, Expandable, Loading, PageHeader, Pill, Stat, useAsync } from "../ui.jsx";

export default function Evaluation() {
  const [data, setData] = useState(null);
  const [state, run] = useAsync();
  const start = async () => { const r = await run(() => api.runEvaluation()); if (r) setData(r); };
  const m = data && data.metrics;

  return (
    <>
      <PageHeader title="AI Evaluation" subtitle="Executes the project's evaluation cases against the assessment pipeline">
        <button className="btn" onClick={start} disabled={state.loading}>{state.loading ? "Running..." : data ? "Run again" : "Run evaluation"}</button>
      </PageHeader>
      <ErrorBox error={state.error} />
      {state.loading && <Loading text="Running evaluation cases..." />}
      {!data && !state.loading && (
        <Empty title="No evaluation run yet">Press "Run evaluation" to execute the test cases in <code>evaluation/test_cases.json</code>. Nothing is shown until it has actually run.</Empty>
      )}
      {data && (
        <div className="stack">
          <div className="grid grid-4">
            <Stat label="Cases passed" value={`${m.cases_passed}/${m.cases}`} />
            <Stat label="Checks passed" value={`${m.checks_passed}/${m.checks}`} />
            <Stat label="Check pass rate" value={m.check_pass_rate === null ? "n/a" : `${(m.check_pass_rate * 100).toFixed(1)}%`} />
            <Stat label="Assessment date used" value={data.assessment_date} />
          </div>
          <Card title="Case results">
            {data.cases.map((c) => (
              <Expandable key={c.id} header={<span className="row gap wrap"><Pill color={c.passed ? "#15803d" : "#b91c1c"} bg={c.passed ? "#dcfce7" : "#fee2e2"}>{c.passed ? "PASS" : "FAIL"}</Pill><b>{c.id}</b><span className="muted small">{c.passed_checks}/{c.total_checks} checks</span></span>}>
                <p>{c.description}</p>
                {c.error && <ErrorBox error={c.error} />}
                <div className="table-wrap"><table>
                  <thead><tr><th>Check</th><th>Expected</th><th>Actual</th><th></th></tr></thead>
                  <tbody>{c.checks.map((k) => <tr key={k.check}><td>{k.check}</td><td>{k.expected}</td><td>{k.actual}</td><td>{k.passed ? "✓" : "✗"}</td></tr>)}</tbody>
                </table></div>
              </Expandable>
            ))}
          </Card>
        </div>
      )}
    </>
  );
}

import React, { useState } from "react";

export const STATUS = {
  COMPLIANT: { label: "Compliant", color: "#15803d", bg: "#dcfce7" },
  PARTIALLY_COMPLIANT: { label: "Partially compliant", color: "#b45309", bg: "#fef3c7" },
  NON_COMPLIANT: { label: "Non-compliant", color: "#b91c1c", bg: "#fee2e2" },
  INSUFFICIENT_EVIDENCE: { label: "Insufficient evidence", color: "#4b5563", bg: "#e5e7eb" },
};
export const RISK = {
  High: { color: "#b91c1c", bg: "#fee2e2" },
  Medium: { color: "#b45309", bg: "#fef3c7" },
  Low: { color: "#15803d", bg: "#dcfce7" },
  Undetermined: { color: "#4b5563", bg: "#e5e7eb" },
};
export const OVERALL_TONE = {
  NON_COMPLIANCE_INDICATED: "#b91c1c",
  EVIDENCE_INCOMPLETE: "#b45309",
  NO_GAPS_IN_SUBMITTED_EVIDENCE: "#15803d",
  NO_APPLICABLE_REQUIREMENTS: "#4b5563",
};

export const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString() : "");

export function Pill({ color, bg, children }) {
  return <span className="pill" style={{ color, background: bg }}>{children}</span>;
}
export function StatusBadge({ status }) {
  const s = STATUS[status] || { label: status, color: "#4b5563", bg: "#e5e7eb" };
  return <Pill color={s.color} bg={s.bg}>{s.label}</Pill>;
}
export function RiskBadge({ level }) {
  const r = RISK[level] || RISK.Undetermined;
  return <Pill color={r.color} bg={r.bg}>Risk: {level}</Pill>;
}
export function Card({ title, action, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <div className="card-head">
          <h3>{title}</h3>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function PageHeader({ title, subtitle, children }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      <div className="row gap">{children}</div>
    </header>
  );
}
export function Loading({ text = "Loading..." }) {
  return <div className="loading"><span className="spinner" /> {text}</div>;
}
export function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="alert alert-error" role="alert">
      <span>{typeof error === "string" ? error : error.message}</span>
      {onRetry && <button className="btn btn-small" onClick={onRetry}>Retry</button>}
    </div>
  );
}
export function Notice({ tone = "info", children }) {
  return <div className={`alert alert-${tone}`}>{children}</div>;
}
export function Empty({ title, children, action }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p className="muted">{children}</p>
      {action}
    </div>
  );
}
export function Stat({ label, value, hint }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="muted small">{hint}</div>}
    </div>
  );
}
export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className={`tab ${value === t.id ? "active" : ""}`} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
export function Field({ label, error, hint, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && !error && <span className="muted small">{hint}</span>}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}
export function Expandable({ header, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="expandable">
      <button className="expandable-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="chev">{open ? "▾" : "▸"}</span>
        <span className="grow">{header}</span>
      </button>
      {open && <div className="expandable-body">{children}</div>}
    </div>
  );
}

// Donut chart (SVG). segments: [{label, value, color}]
export function Donut({ segments, size = 150, centerLabel }) {
  const total = segments.reduce((a, s) => a + s.value, 0);
  const r = 52;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div className="donut-wrap">
      <svg width={size} height={size} viewBox="0 0 140 140" role="img" aria-label="Status distribution">
        <circle cx="70" cy="70" r={r} fill="none" stroke="#e5e7eb" strokeWidth="18" />
        {total > 0 &&
          segments.filter((s) => s.value > 0).map((s) => {
            const len = (s.value / total) * c;
            const el = (
              <circle key={s.label} cx="70" cy="70" r={r} fill="none" stroke={s.color} strokeWidth="18"
                strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-offset} transform="rotate(-90 70 70)" />
            );
            offset += len;
            return el;
          })}
        <text x="70" y="68" textAnchor="middle" className="donut-num">{total}</text>
        <text x="70" y="86" textAnchor="middle" className="donut-cap">{centerLabel || "assessed"}</text>
      </svg>
      <ul className="legend">
        {segments.map((s) => (
          <li key={s.label}><i style={{ background: s.color }} /> {s.label} <b>{s.value}</b></li>
        ))}
      </ul>
    </div>
  );
}

export function BarList({ items }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <div className="bars">
      {items.map((i) => (
        <div className="bar-row" key={i.label}>
          <span className="bar-label">{i.label}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(i.value / max) * 100}%`, background: i.color }} /></div>
          <b>{i.value}</b>
        </div>
      ))}
    </div>
  );
}

export function Sources({ sources }) {
  return (
    <ul className="sources">
      {sources.map((s) => (
        <li key={s.url}>
          <a href={s.url} target="_blank" rel="noreferrer">{s.label}</a>
          <span className="tag">{s.kind.replace(/_/g, " ")}</span>
        </li>
      ))}
    </ul>
  );
}

export function useAsync() {
  const [state, setState] = useState({ loading: false, error: null });
  const run = async (fn) => {
    setState({ loading: true, error: null });
    try {
      const out = await fn();
      setState({ loading: false, error: null });
      return out;
    } catch (e) {
      setState({ loading: false, error: e });
      return undefined;
    }
  };
  return [state, run];
}

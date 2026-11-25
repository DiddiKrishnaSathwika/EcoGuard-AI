import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Card, ErrorBox, Field, Loading, Notice, PageHeader, useAsync } from "../ui.jsx";

const EMPTY = {
  company: "", industry: "", state: "", wastewater: "Unknown", air_emissions: "Unknown", hazardous_waste: "Unknown",
  wastewater_volume_lpd: "", wastewater_treatment: "", wastewater_disposal: "",
  air_sources: "", air_control_equipment: "", hazardous_waste_types: "", hazardous_waste_qty_kg_month: "",
};

export default function Profile({ profiles, activeId, setActiveId, reloadProfiles, go }) {
  const [options, setOptions] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});
  const [saved, setSaved] = useState(null);
  const [state, run] = useAsync();

  useEffect(() => { api.options().then(setOptions).catch(() => setOptions(false)); }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const edit = (p) => {
    setEditing(p.id);
    setSaved(null);
    setFieldErrors({});
    setForm(Object.fromEntries(Object.keys(EMPTY).map((k) => [k, p[k] === null || p[k] === undefined ? "" : p[k]])));
    window.scrollTo(0, 0);
  };
  const reset = () => { setEditing(null); setForm(EMPTY); setFieldErrors({}); };

  const clientCheck = () => {
    const errs = {};
    if (!form.company.trim()) errs.company = "Company name is required.";
    if (!form.industry) errs.industry = "Choose an industry.";
    if (!form.state) errs.state = "Choose a state or union territory.";
    for (const k of ["wastewater_volume_lpd", "hazardous_waste_qty_kg_month"]) {
      if (form[k] !== "" && (isNaN(Number(form[k])) || Number(form[k]) < 0)) errs[k] = "Enter a non-negative number.";
    }
    return errs;
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaved(null);
    const errs = clientCheck();
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;
    const payload = { ...form };
    for (const k of ["wastewater_volume_lpd", "hazardous_waste_qty_kg_month"]) payload[k] = form[k] === "" ? null : Number(form[k]);
    const result = await run(async () => {
      try {
        return editing ? await api.updateProfile(editing, payload) : await api.createProfile(payload);
      } catch (err) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors);
        throw err;
      }
    });
    if (result) {
      await reloadProfiles();
      setActiveId(result.id);
      setSaved(result);
      reset();
    }
  };

  const remove = async (p) => {
    if (!window.confirm(`Delete "${p.company}"? Its assessments are kept but uploaded documents are unlinked.`)) return;
    await run(() => api.deleteProfile(p.id));
    await reloadProfiles();
  };

  if (options === null) return <><PageHeader title="Business Profile" /><Loading /></>;
  if (options === false) return <><PageHeader title="Business Profile" /><ErrorBox error="Could not load form options from the backend." /></>;

  const yn = (k) => (
    <select value={form[k]} onChange={set(k)}>{options.yes_no.map((o) => <option key={o}>{o}</option>)}</select>
  );

  return (
    <>
      <PageHeader title="Business Profile" subtitle="Step 1 - tell us about the business being assessed" />
      {saved && (
        <Notice tone="info">
          Saved <b>{saved.company}</b> and set it as the active business.{" "}
          <button className="btn btn-small" onClick={() => go("documents")}>Next: upload documents</button>
        </Notice>
      )}
      <ErrorBox error={state.error && !state.error.fieldErrors ? state.error : null} />

      <form onSubmit={submit} noValidate>
        <Card title={editing ? "Edit business" : "New business"}>
          <div className="form-grid">
            <Field label="Company name *" error={fieldErrors.company}><input type="text" value={form.company} onChange={set("company")} maxLength={150} /></Field>
            <Field label="Industry *" error={fieldErrors.industry}>
              <select value={form.industry} onChange={set("industry")}><option value="">Select...</option>{options.industries.map((o) => <option key={o}>{o}</option>)}</select>
            </Field>
            <Field label="State / Union Territory *" error={fieldErrors.state}>
              <select value={form.state} onChange={set("state")}><option value="">Select...</option>{options.states.map((o) => <option key={o}>{o}</option>)}</select>
            </Field>
          </div>
        </Card>

        <div className="grid grid-3" style={{ marginTop: "1rem" }}>
          <fieldset>
            <legend>Wastewater discharge</legend>
            <div className="stack">
              <Field label="Generates wastewater?" error={fieldErrors.wastewater}>{yn("wastewater")}</Field>
              <Field label="Volume (litres/day)" error={fieldErrors.wastewater_volume_lpd}><input type="number" min="0" value={form.wastewater_volume_lpd} onChange={set("wastewater_volume_lpd")} /></Field>
              <Field label="Treatment (e.g. ETP)"><input type="text" value={form.wastewater_treatment} onChange={set("wastewater_treatment")} /></Field>
              <Field label="Disposal method"><input type="text" value={form.wastewater_disposal} onChange={set("wastewater_disposal")} /></Field>
            </div>
          </fieldset>
          <fieldset>
            <legend>Air emissions</legend>
            <div className="stack">
              <Field label="Generates air emissions?" error={fieldErrors.air_emissions}>{yn("air_emissions")}</Field>
              <Field label="Sources (e.g. DG set 25 kVA, boiler)"><input type="text" value={form.air_sources} onChange={set("air_sources")} /></Field>
              <Field label="Control equipment"><input type="text" value={form.air_control_equipment} onChange={set("air_control_equipment")} /></Field>
            </div>
          </fieldset>
          <fieldset>
            <legend>Hazardous waste</legend>
            <div className="stack">
              <Field label="Generates hazardous waste?" error={fieldErrors.hazardous_waste}>{yn("hazardous_waste")}</Field>
              <Field label="Waste types"><input type="text" value={form.hazardous_waste_types} onChange={set("hazardous_waste_types")} /></Field>
              <Field label="Quantity (kg/month)" error={fieldErrors.hazardous_waste_qty_kg_month}><input type="number" min="0" value={form.hazardous_waste_qty_kg_month} onChange={set("hazardous_waste_qty_kg_month")} /></Field>
            </div>
          </fieldset>
        </div>

        <div className="row gap">
          <button className="btn" type="submit" disabled={state.loading}>{state.loading ? "Saving..." : editing ? "Save changes" : "Save business"}</button>
          {(editing || form.company) && <button type="button" className="btn btn-ghost" onClick={reset}>Clear form</button>}
        </div>
      </form>

      <Card title={`Saved businesses (${profiles.length})`} className="" >
        {profiles.length === 0 ? <p className="muted">No businesses saved yet.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Company</th><th>Industry</th><th>State</th><th>W / A / H</th><th></th></tr></thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.id}>
                    <td><b>{p.company}</b> {p.id === activeId && <span className="tag">active</span>}</td>
                    <td>{p.industry}</td><td>{p.state}</td>
                    <td>{p.wastewater} / {p.air_emissions} / {p.hazardous_waste}</td>
                    <td className="row gap">
                      {p.id !== activeId && <button className="btn btn-ghost btn-small" onClick={() => setActiveId(p.id)}>Use</button>}
                      <button className="btn btn-ghost btn-small" onClick={() => edit(p)}>Edit</button>
                      <button className="btn btn-danger btn-small" onClick={() => remove(p)}>Delete</button>
                    </td>
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

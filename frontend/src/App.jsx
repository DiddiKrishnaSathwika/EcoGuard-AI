import React, { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Dashboard from "./pages/Dashboard.jsx";
import Profile from "./pages/Profile.jsx";
import Documents from "./pages/Documents.jsx";
import Regulations from "./pages/Regulations.jsx";
import Assessment from "./pages/Assessment.jsx";
import Reports from "./pages/Reports.jsx";
import Evaluation from "./pages/Evaluation.jsx";
import { authConfigured, initializeAuth, signIn, signOut } from "./auth.js";

const PAGES = [
  { id: "dashboard", label: "Dashboard", icon: "▦" },
  { id: "profile", label: "Business Profile", step: 1 },
  { id: "documents", label: "Documents", step: 2 },
  { id: "regulations", label: "Regulations", step: 3 },
  { id: "assessment", label: "Assessment & Results", step: 4 },
  { id: "reports", label: "Reports", step: 5 },
  { id: "evaluation", label: "AI Evaluation", icon: "✓" },
];

function readStored(key) {
  try { return window.localStorage.getItem(key); } catch (e) { return null; }
}
function writeStored(key, value) {
  try { window.localStorage.setItem(key, value); } catch (e) { /* storage unavailable */ }
}

export default function App() {
  const [auth, setAuth] = useState({ ready: false, user: null, error: null });
  const [isAdmin, setIsAdmin] = useState(false);
  const [page, setPage] = useState(() => (window.location.hash || "#dashboard").slice(1));
  const [params, setParams] = useState({});
  const [profiles, setProfiles] = useState([]);
  const [activeId, setActiveId] = useState(() => Number(readStored("ecoguard.activeProfile")) || null);
  const [menu, setMenu] = useState(false);
  const [backendError, setBackendError] = useState(null);

  const reloadProfiles = useCallback(async () => {
    try {
      const list = await api.profiles();
      setProfiles(list);
      setBackendError(null);
      return list;
    } catch (e) {
      setBackendError(e.message);
      return [];
    }
  }, []);

  useEffect(() => {
    let active = true;
    initializeAuth()
      .then((user) => {
        if (active) setAuth({ ready: true, user, error: null });
      })
      .catch(() => {
        if (active) setAuth({ ready: true, user: null, error: "Sign-in could not be completed. Try again." });
      });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (auth.user) reloadProfiles();
  }, [auth.user, reloadProfiles]);
  useEffect(() => {
    if (!auth.user) {
      setIsAdmin(false);
      return;
    }
    api.session()
      .then((session) => setIsAdmin(session.is_platform_admin))
      .catch(() => setIsAdmin(false));
  }, [auth.user]);
  useEffect(() => {
    if (!auth.user?.expires_at) return undefined;
    const remaining = auth.user.expires_at * 1000 - Date.now();
    const timer = window.setTimeout(
      () => setAuth({ ready: true, user: null, error: "Your session expired. Sign in again." }),
      Math.max(remaining, 0),
    );
    return () => window.clearTimeout(timer);
  }, [auth.user]);
  useEffect(() => {
    if (profiles.length && !profiles.some((p) => p.id === activeId)) setActiveId(profiles[0].id);
  }, [profiles, activeId]);
  useEffect(() => { if (activeId) writeStored("ecoguard.activeProfile", String(activeId)); }, [activeId]);

  const go = (id, p = {}) => {
    setPage(id);
    setParams(p);
    setMenu(false);
    window.location.hash = id;
    window.scrollTo(0, 0);
  };
  const active = profiles.find((p) => p.id === activeId) || null;
  const ctx = { profiles, active, activeId, setActiveId, reloadProfiles, go, params, isAdmin };

  const visiblePage = page === "evaluation" && !isAdmin ? "dashboard" : page;
  const View = { dashboard: Dashboard, profile: Profile, documents: Documents, regulations: Regulations,
    assessment: Assessment, reports: Reports, evaluation: Evaluation }[visiblePage] || Dashboard;

  if (!auth.ready) {
    return <main className="main" style={{ margin: "15vh auto", maxWidth: 560 }}>Loading authentication...</main>;
  }
  if (!authConfigured || !auth.user) {
    return (
      <main className="main" style={{ margin: "15vh auto", maxWidth: 560 }}>
        <div className="brand"><span className="brand-mark">E</span> EcoGuard AI</div>
        <section className="card">
          <h1>{authConfigured ? "Sign in to EcoGuard AI" : "Authentication is not configured"}</h1>
          <p className="muted">
            {authConfigured
              ? "Sign in with your organization identity provider to access business records."
              : "Set the VITE_OIDC_AUTHORITY, VITE_OIDC_CLIENT_ID, and VITE_OIDC_AUDIENCE frontend settings."}
          </p>
          {auth.error && <div className="alert alert-error" role="alert">{auth.error}</div>}
          {authConfigured && (
            <button
              className="btn"
              onClick={() => signIn().catch(() => setAuth((current) => ({
                ...current,
                error: "Sign-in could not be started. Check the identity-provider configuration.",
              })))}
            >
              Sign in
            </button>
          )}
        </section>
      </main>
    );
  }

  return (
    <div className="shell">
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <div className="brand"><span className="brand-mark">E</span> EcoGuard AI</div>
        <div className="profile-chip">
          <span className="muted" style={{ color: "#a7f3d0" }}>Active business</span>
          <b>{active ? active.company : "None selected"}</b>
          {active && <span>{active.industry} · {active.state}</span>}
        </div>
        <nav className="nav" aria-label="Main navigation">
          {PAGES.map((p) => (
            (p.id !== "evaluation" || isAdmin) &&
            <button key={p.id} className={visiblePage === p.id ? "active" : ""} onClick={() => go(p.id)}>
              <span className="step">{p.step || p.icon}</span> {p.label}
            </button>
          ))}
        </nav>
        <button className="btn btn-ghost btn-small" onClick={() => signOut().then(() => setAuth({ ready: true, user: null, error: null }))}>
          Sign out
        </button>
        <div className="sidebar-foot">Screening aid for Indian SMEs. Not legal advice.</div>
      </aside>
      <main className="main">
        <div className="topbar"><button onClick={() => setMenu(!menu)} aria-label="Toggle menu">☰</button><b>EcoGuard AI</b>
          <button className="btn btn-small" onClick={() => signOut().then(() => setAuth({ ready: true, user: null, error: null }))}>Sign out</button>
        </div>
        {backendError && (
          <div className="alert alert-error" role="alert">
            <span>{backendError}</span>
            <button className="btn btn-small" onClick={reloadProfiles}>Retry</button>
          </div>
        )}
        <View {...ctx} />
      </main>
    </div>
  );
}

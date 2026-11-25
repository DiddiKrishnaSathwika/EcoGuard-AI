// Thin REST client. In dev, Vite proxies /api to FastAPI (see vite.config.js).
import { getAccessToken } from "./auth.js";

const BASE = import.meta.env.VITE_API_URL || "";

export const apiUrl = (path) => `${BASE}${path}`;

async function request(path, options = {}, requiresAuth = true) {
  let response;
  const headers = new Headers(options.headers || {});
  if (requiresAuth) {
    const token = await getAccessToken();
    if (!token) throw new ApiError("Sign in is required or your session has expired.", 401);
    headers.set("Authorization", `Bearer ${token}`);
  }
  try {
    response = await fetch(apiUrl(path), { ...options, headers });
  } catch (e) {
    throw new ApiError("Cannot reach the EcoGuard backend. Is it running on http://127.0.0.1:8000 ?", 0);
  }
  const type = response.headers.get("content-type") || "";
  const body = type.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const detail = body && (typeof body.detail === "string" ? body.detail : "Request failed");
    throw new ApiError(detail || `Request failed (${response.status})`, response.status, body && body.errors);
  }
  return body;
}

export class ApiError extends Error {
  constructor(message, status, fieldErrors) {
    super(message);
    this.status = status;
    this.fieldErrors = fieldErrors || null;
  }
}

const json = (method, data) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  status: () => request("/api/status", {}, false),
  options: () => request("/api/meta/options", {}, false),
  session: () => request("/api/session"),
  dashboard: () => request("/api/dashboard"),
  profiles: () => request("/api/profiles"),
  createProfile: (d) => request("/api/profiles", json("POST", d)),
  updateProfile: (id, d) => request(`/api/profiles/${id}`, json("PUT", d)),
  deleteProfile: (id) => request(`/api/profiles/${id}`, { method: "DELETE" }),
  documents: (profileId) => request(`/api/documents${profileId ? `?profile_id=${profileId}` : ""}`),
  document: (id) => request(`/api/documents/${id}`),
  deleteDocument: (id) => request(`/api/documents/${id}`, { method: "DELETE" }),
  uploadDocument: (file, profileId, useAi) => {
    const form = new FormData();
    form.append("file", file);
    if (profileId) form.append("profile_id", String(profileId));
    form.append("use_ai", useAi ? "true" : "false");
    return request("/api/documents/upload", { method: "POST", body: form });
  },
  regulations: () => request("/api/regulations", {}, false),
  retrieve: (profileId, documentIds) => request("/api/regulations/retrieve", json("POST", { profile_id: profileId, document_ids: documentIds })),
  refreshSource: (id) => request(`/api/regulations/sources/${id}/refresh`, { method: "POST" }),
  assessments: () => request("/api/assessments"),
  assessment: (id) => request(`/api/assessments/${id}`),
  createAssessment: (profileId, documentIds, useAi) => request("/api/assessments", json("POST", { profile_id: profileId, document_ids: documentIds, use_ai: useAi })),
  deleteAssessment: (id) => request(`/api/assessments/${id}`, { method: "DELETE" }),
  downloadReport: async (id) => {
    const token = await getAccessToken();
    if (!token) throw new ApiError("Sign in is required or your session has expired.", 401);
    let response;
    try {
      response = await fetch(apiUrl(`/api/assessments/${id}/report.pdf`), {
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch (e) {
      throw new ApiError("Cannot reach the EcoGuard backend.", 0);
    }
    if (!response.ok) {
      const body = (response.headers.get("content-type") || "").includes("application/json")
        ? await response.json()
        : null;
      const detail = body && typeof body.detail === "string" ? body.detail : "Report download failed.";
      throw new ApiError(detail, response.status);
    }
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `EcoGuard_Report_${id}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  },
  runEvaluation: () => request("/api/evaluation/run", { method: "POST" }),
};

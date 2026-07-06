// Thin REST client. Same-origin relative URLs (Vite proxies /api to FastAPI).
const getToken = () => localStorage.getItem("rael_token");

const j = (r) => {
  if (r.status === 401 && getToken() && !r.url.includes("/api/auth/")) {
    // Session expired or revoked — drop the stale token and land on the login screen.
    localStorage.removeItem("rael_token");
    location.reload();
  }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
};

const req = (url, options = {}) => {
  const token = getToken();
  const headers = { ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...options, headers }).then(j);
};

export const api = {
  // Auth
  login: (email) => 
    req("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email })
    }),
  verify: (email, otp) =>
    req("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, otp })
    }),
  me: () => req("/api/auth/me"),
  logout: () => req("/api/auth/logout", { method: "POST" }).catch(() => ({})),
  metrics: () => req("/api/metrics"),
  hot: () => req("/api/hot"),
  leads: (status) => req(`/api/leads${status ? `?status=${status}` : ""}`),
  lead: (id) => req(`/api/leads/${id}`),
  logs: (limit = 80) => req(`/api/logs?limit=${limit}`),
  fit: () => req("/api/onboarding"),

  approve: (id, decision = "send") =>
    req(`/api/approvals/${id}?decision=${decision}`, { method: "POST" }),
  // Human-approved Apollo enrichment — the only way credits get spent.
  enrichLead: (id) => req(`/api/leads/${id}/enrich`, { method: "POST" }),
  outcome: (lead_id, outcome_type, closed_value) =>
    req("/api/outcomes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lead_id, outcome_type, closed_value }),
    }),
  brief: (id) => req(`/api/leads/${id}/brief`, { method: "POST" }),
  reply: (id, text) =>
    req(`/api/leads/${id}/reply?text=${encodeURIComponent(text)}`, { method: "POST" }),
  onboard: (payload) =>
    req("/api/onboarding", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  // Discovery / scouting
  brain: () => req("/api/discovery/brain"),
  discovered: (status) =>
    req(`/api/discovery/companies${status ? `?status=${status}` : ""}`),
  runDiscovery: () => req("/api/discovery/run", { method: "POST" }),
  rebuildBrain: () => req("/api/discovery/brain/build", { method: "POST" }),
  importUrls: (urls) => req("/api/discovery/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls })
  }),

  // Outreach / inbox
  outreach: () => req("/api/outreach"),
  updateDraft: (id, { subject, content }) =>
    req(`/api/interactions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject, content }),
    }),

  // Mode toggle (paused / copilot / autonomous)
  getMode: () => req("/api/settings/mode"),
  setMode: (mode) =>
    req("/api/settings/mode", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    }),
};

import { create } from "zustand";
import { api } from "./api";

let socket = null;
let refreshTimer = null;
let raelTimer = null;

export const useStore = create((set, get) => ({
  // ── auth state ──
  user: null,
  authStatus: "loading", // loading | unauthenticated | onboard_pending | authenticated

  // ── view state ──
  view: "hq", // hq | brain | scouting | relationships | pipeline | outreach | desk | train | results
  setView: (view) => set({ view }),

  // ── data ──
  feed: [],
  notifications: [],
  leads: [],
  metrics: {},
  hot: [],
  fit: [],
  brain: null, // Rael's distilled understanding (product_brain)
  discovered: [], // companies the discovery engine surfaced
  selected: null, // lead deep-dive object
  connected: false,
  raelState: "idle", // idle | active | alert
  busy: false,

  // ── mode (paused | copilot | autonomous) ──
  mode: "copilot",

  // ── outreach (drafts, sent, inbox) ──
  outreach: { drafts: [], sent: [], inbox: [] },

  // ── enrichment approval (Apollo credits — never spent without a human) ──
  enrichDismissed: {},   // lead_id -> true, "Not now" snoozes; new finds re-pop
  enriching: {},         // lead_id -> true while the Apollo call runs

  // ── lifecycle ──
  async init() {
    try {
      const user = await api.me();
      set({ 
        user, 
        authStatus: user.onboarding_completed ? "authenticated" : "onboard_pending" 
      });
      await get().loadAppData();
    } catch (e) {
      set({ authStatus: "unauthenticated", user: null });
    }
  },

  async login(email, otp) {
    if (otp) {
      const res = await api.verify(email, otp);
      localStorage.setItem("rael_token", res.token);
      set({ authStatus: res.onboarding_completed ? "authenticated" : "onboard_pending" });
      if (res.onboarding_completed) {
        await get().loadAppData();
      }
    } else {
      await api.login(email);
    }
  },

  logout() {
    api.logout(); // invalidate server-side; fire-and-forget
    localStorage.removeItem("rael_token");
    try { socket?.close(); } catch { /* already closed */ }
    socket = null;
    set({
      authStatus: "unauthenticated", user: null, view: "hq",
      feed: [], notifications: [], leads: [], metrics: {}, hot: [], fit: [],
      brain: null, discovered: [], selected: null, connected: false,
      outreach: { drafts: [], sent: [], inbox: [] },
    });
  },

  async completeOnboarding() {
    set({ authStatus: "authenticated" });
    await get().loadAppData();
  },

  async loadAppData() {
    await get().refresh();
    const logs = await api.logs();
    set({ feed: logs });
    get().connectWS();
    // Load mode
    const m = await api.getMode().catch(() => ({ mode: "copilot" }));
    set({ mode: m.mode });
  },

  async refresh() {
    const [metrics, hot, leads, fit, brain, discovered, outreach] = await Promise.all([
      api.metrics(),
      api.hot(),
      api.leads(),
      api.fit(),
      api.brain().catch(() => null),
      api.discovered().catch(() => []),
      api.outreach().catch(() => ({ drafts: [], sent: [], inbox: [] })),
    ]);
    set({ metrics, hot, leads, fit, brain, discovered, outreach });
  },

  async refreshOutreach() {
    const data = await api.outreach().catch(() => ({ drafts: [], sent: [], inbox: [] }));
    set({ outreach: data });
  },

  // debounced refresh so a burst of feed events triggers one reload
  scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(() => get().refresh(), 400);
  },

  pulse(state) {
    set({ raelState: state });
    clearTimeout(raelTimer);
    raelTimer = setTimeout(() => set({ raelState: "idle" }), 2500);
  },

  // ── mode toggle ──
  async setMode(mode) {
    const res = await api.setMode(mode);
    if (res.ok !== false) set({ mode });
  },

  connectWS() {
    const token = localStorage.getItem("rael_token");
    if (!token) return; // logged out — nothing to stream
    const proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${location.host}/ws/feed?token=${encodeURIComponent(token)}`);
    socket.onopen = () => set({ connected: true });
    socket.onclose = () => {
      set({ connected: false });
      if (localStorage.getItem("rael_token")) {
        setTimeout(() => get().connectWS(), 2000); // auto-reconnect
      }
    };
    socket.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.channel === "feed") {
        set((s) => ({ feed: [msg, ...s.feed].slice(0, 200) }));
        get().pulse(msg.level === "urgent" ? "alert" : "active");
        get().scheduleRefresh();
      } else if (msg.channel === "whatsapp") {
        set((s) => ({ notifications: [{ ...msg, _id: Date.now() + Math.random() }, ...s.notifications].slice(0, 8) }));
        get().pulse("alert");
      } else if (msg.channel === "enrich_request") {
        // New companies found — un-snooze so the approval prompt pops again.
        set({ enrichDismissed: {} });
        get().pulse("alert");
        get().scheduleRefresh();
      }
    };
  },

  dismissNotification: (id) =>
    set((s) => ({ notifications: s.notifications.filter((n) => n._id !== id) })),

  // ── actions ──
  // Scout the market now (the scheduler also does this continuously).
  async runDiscovery() {
    set({ busy: true });
    try {
      await api.runDiscovery();
      await get().refresh();
    } finally {
      set({ busy: false });
    }
  },
  // Re-distil the Brain from the current Fit Model.
  async rebuildBrain() {
    set({ busy: true });
    try {
      await api.rebuildBrain();
      await get().refresh();
    } finally {
      set({ busy: false });
    }
  },
  async openLead(id) {
    const detail = await api.lead(id);
    set({ selected: detail });
  },
  closeLead: () => set({ selected: null }),
  async approve(id, decision) {
    await api.approve(id, decision);
    await get().refresh();
    if (get().selected?.lead?.id === id) await get().openLead(id);
  },
  // Human edits a held draft (subject/body), then optionally sends it.
  async saveDraft(interactionId, { subject, content }) {
    await api.updateDraft(interactionId, { subject, content });
    await get().refreshOutreach();
  },
  // ── Apollo enrichment (human-approved only) ──
  async enrichLead(id) {
    set((s) => ({ enriching: { ...s.enriching, [id]: true } }));
    try {
      await api.enrichLead(id);
      await get().refresh();
      if (get().selected?.lead?.id === id) await get().openLead(id);
    } finally {
      set((s) => {
        const e = { ...s.enriching };
        delete e[id];
        return { enriching: e };
      });
    }
  },
  async enrichAll(ids) {
    for (const id of ids) {
      await get().enrichLead(id); // sequential — visible progress, gentle on credits
    }
  },
  snoozeEnrich(ids) {
    set((s) => ({
      enrichDismissed: { ...s.enrichDismissed, ...Object.fromEntries(ids.map((i) => [i, true])) },
    }));
  },
  async recordOutcome(id, type, value) {
    await api.outcome(id, type, value);
    await get().refresh();
    if (get().selected?.lead?.id === id) await get().openLead(id);
  },
  async simulateReply(id, text) {
    await api.reply(id, text);
    await get().refresh();
    if (get().selected?.lead?.id === id) await get().openLead(id);
  },
  async makeBrief(id) {
    await api.brief(id);
    if (get().selected?.lead?.id === id) await get().openLead(id);
  },
}));

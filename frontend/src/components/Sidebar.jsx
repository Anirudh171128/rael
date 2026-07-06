import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

const RAEL_IMG = import.meta.env.VITE_RAEL_AVATAR_IMG || "/rael.png";

const I = {
  hq: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 11l9-7 9 7" /><path d="M5 10v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9" /><path d="M9 20v-6h6v6" /></svg>,
  brain: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5.2A2.8 2.8 0 0 0 9 18a3 3 0 0 0 3 1 3 3 0 0 0 3-1 2.8 2.8 0 0 0 2-5.8A3 3 0 0 0 15 7a3 3 0 0 0-3-3Z" /><path d="M12 4v15" /></svg>,
  scouting: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="M11 4a7 7 0 0 1 7 7" /><path d="M11 8a3 3 0 0 1 3 3" /><path d="M16.5 16.5L21 21" /></svg>,
  relationships: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="8" r="3" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M16 5.5a3 3 0 0 1 0 5.6" /><path d="M17 14.5a5.5 5.5 0 0 1 3.5 4.5" /></svg>,
  pipeline: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 5h18" /><path d="M6 5l3 6v6l6-3v-3l3-6" /></svg>,
  outreach: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><path d="M22 6l-10 7L2 6" /></svg>,
  desk: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 3v3h6V3" /><path d="M9 11h6M9 15h4" /></svg>,
  train: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8l9-4 9 4-9 4-9-4Z" /><path d="M7 10.5V15c0 1.1 2.2 2.5 5 2.5s5-1.4 5-2.5v-4.5" /><path d="M21 8v5" /></svg>,
  results: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19V5" /><path d="M4 19h16" /><path d="M8 16v-4M13 16V8M18 16v-6" /></svg>,
};

const NAV = [
  { key: "hq", label: "HQ", icon: I.hq },
  { key: "brain", label: "Brain", icon: I.brain },
  { key: "scouting", label: "Scouting", icon: I.scouting },
  { key: "relationships", label: "Relationships", icon: I.relationships },
  { key: "pipeline", label: "Pipeline", icon: I.pipeline },
  { key: "outreach", label: "Outreach", icon: I.outreach },
  { key: "desk", label: "Desk", icon: I.desk },
  { key: "train", label: "Train Rael", icon: I.train },
  { key: "results", label: "Results", icon: I.results },
];

const MODE_CFG = {
  paused:     { label: "Paused",     dot: "var(--faint)",   desc: "Nothing is running" },
  copilot:    { label: "Co-pilot",   dot: "var(--success)", desc: "Scouts & drafts, holds for you" },
  autonomous: { label: "Autonomous", dot: "var(--signal)",  desc: "Full auto — sends without asking" },
};
const MODE_ORDER = ["paused", "copilot", "autonomous"];

export default function Sidebar() {
  const { view, setView, metrics, mode, setMode, outreach, user, logout } = useStore(
    useShallow((s) => ({
      view: s.view, setView: s.setView, metrics: s.metrics,
      mode: s.mode, setMode: s.setMode,
      outreach: s.outreach, user: s.user, logout: s.logout,
    }))
  );
  const waiting = metrics.waiting_on_you ?? 0;
  const draftCount = outreach?.drafts?.length ?? 0;
  const mcfg = MODE_CFG[mode] || MODE_CFG.copilot;

  const cycleMode = () => {
    const idx = MODE_ORDER.indexOf(mode);
    const next = MODE_ORDER[(idx + 1) % MODE_ORDER.length];
    setMode(next);
  };

  return (
    <aside className="os-sidebar">
      <div className="ws-head">
        <div className="ws-portrait">
          <img src={RAEL_IMG} alt="Rael" draggable={false} />
        </div>
        <div>
          <div className="ws-name">Rael</div>
          <div className="ws-role">
            <span className="ws-dot" style={{ background: mcfg.dot, boxShadow: `0 0 7px ${mcfg.dot}` }} />
            {mcfg.label}
          </div>
        </div>
      </div>

      <nav className="nav-group">
        {NAV.map((n) => (
          <button
            key={n.key}
            className={`nav-link ${view === n.key ? "active" : ""}`}
            onClick={() => setView(n.key)}
          >
            {n.icon}
            {n.label}
            {n.key === "desk" && waiting > 0 && <span className="nav-badge">{waiting}</span>}
            {n.key === "outreach" && draftCount > 0 && <span className="nav-badge">{draftCount}</span>}
          </button>
        ))}
      </nav>

      <div className="ws-foot">
        {/* Mode switch */}
        <button className="mode-switch" onClick={cycleMode} title={mcfg.desc}>
          <span className="mode-dot" style={{ background: mcfg.dot, boxShadow: `0 0 6px ${mcfg.dot}` }} />
          <span className="mode-label">{mcfg.label}</span>
          <span className="mode-cycle">⟳</span>
        </button>

        <button className="btn-signout" onClick={logout} title={user?.email || ""}>
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5" /><path d="M21 12H9" /></svg>
          Sign out{user?.email ? <span className="so-email">{user.email}</span> : null}
        </button>
      </div>
    </aside>
  );
}

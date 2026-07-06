import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

// Icon-only sidenav. SVGs inherit currentColor so the active/hover states just
// swap text color.
const I = {
  dashboard: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  ),
  pipeline: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="5" height="16" rx="1.5" /><rect x="10" y="4" width="5" height="11" rx="1.5" /><rect x="17" y="4" width="4" height="7" rx="1.5" />
    </svg>
  ),
  memory: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-1 5.8V15a3 3 0 0 0 4 2.8" />
      <path d="M15 3a3 3 0 0 1 3 3 3 3 0 0 1 1 5.8V15a3 3 0 0 1-4 2.8" />
      <path d="M9 3v15M15 3v15" />
    </svg>
  ),
  reports: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" rx="0.5" /><rect x="12" y="7" width="3" height="10" rx="0.5" /><rect x="17" y="13" width="3" height="4" rx="0.5" />
    </svg>
  ),
  fit: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3.5" /><circle cx="12" cy="12" r="0.5" />
    </svg>
  ),
};

const TOP = [
  { key: "home", label: "Dashboard", icon: I.dashboard },
  { key: "pipeline", label: "Pipeline", icon: I.pipeline },
  { key: "memory", label: "Memory", icon: I.memory },
  { key: "reports", label: "Reports", icon: I.reports },
];

export default function Nav() {
  const { view, setView } = useStore(useShallow((s) => ({ view: s.view, setView: s.setView })));

  const Item = ({ it }) => (
    <button
      className={`nav-item ${view === it.key ? "active" : ""}`}
      onClick={() => setView(it.key)}
      aria-label={it.label}
    >
      {it.icon}
      <span className="nav-tooltip">{it.label}</span>
    </button>
  );

  return (
    <nav className="sidenav">
      {TOP.map((it) => (
        <Item key={it.key} it={it} />
      ))}
      <div style={{ marginTop: "auto" }}>
        <Item it={{ key: "onboarding", label: "Fit Model", icon: I.fit }} />
      </div>
    </nav>
  );
}

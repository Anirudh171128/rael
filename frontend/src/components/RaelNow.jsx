import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { timeAgo } from "../util";

const RAEL_IMG = import.meta.env.VITE_RAEL_AVATAR_IMG || "/rael.png";

// What each tab cares about — the strip filters the live feed to the work
// that belongs on the screen you're looking at. null = everything.
const TAB_SCOPE = {
  hq: { match: null, label: "actions today" },
  desk: { match: null, label: "actions today" },
  brain: { match: /brain|memory|onboarding|outcome/i, label: "brain updates" },
  scouting: { match: /discovery|scout|search|verify|qualif|reject|park|import|signal/i, label: "scouting actions" },
  relationships: { match: /outreach|draft|reply|approval|brief|outcome|qualified/i, label: "relationship touches" },
  pipeline: { match: /discovery|enrich|qualif|outreach|draft|approval|reply|outcome/i, label: "pipeline moves" },
  outreach: { match: /outreach|draft|reply|approval|escalat/i, label: "messages" },
  train: { match: /brain|onboarding|memory/i, label: "training updates" },
  results: { match: /report|outcome|approval|outreach/i, label: "results logged" },
};

function inScope(e, scope) {
  if (!scope?.match) return true;
  return scope.match.test(`${e.agent_name || ""} ${e.action_type || ""}`);
}

// Friendly agent tag for a feed row.
function agentTag(e) {
  const a = `${e.agent_name || ""} ${e.action_type || ""}`.toLowerCase();
  if (/discovery|scout/.test(a)) return "Scout";
  if (/brain/.test(a)) return "Brain";
  if (/enrich/.test(a)) return "Research";
  if (/qualif/.test(a)) return "Scoring";
  if (/outreach|draft/.test(a)) return "Outreach";
  if (/reply|escalat/.test(a)) return "Replies";
  if (/brief|meeting/.test(a)) return "Briefing";
  if (/memory|outcome/.test(a)) return "Learning";
  if (/report/.test(a)) return "Reports";
  return "Rael";
}

function levelColor(e) {
  if (e.level === "urgent") return "var(--danger)";
  if (e.level === "positive") return "var(--success)";
  if (e.level === "attention") return "var(--signal)";
  return "var(--muted)";
}

const IDLE_AFTER_MS = 3 * 60 * 1000;

export default function RaelNow() {
  const { feed, connected, view, busy, mode, openLead } = useStore(
    useShallow((s) => ({
      feed: s.feed, connected: s.connected, view: s.view,
      busy: s.busy, mode: s.mode, openLead: s.openLead,
    }))
  );
  const [open, setOpen] = useState(false);
  const [, forceTick] = useState(0);
  const panelRef = useRef(null);

  // Re-evaluate "working vs idle" once a minute even with no new events.
  useEffect(() => {
    const t = setInterval(() => forceTick((n) => n + 1), 60000);
    return () => clearInterval(t);
  }, []);

  // Close the panel when clicking outside it.
  useEffect(() => {
    if (!open) return;
    const onDown = (ev) => {
      if (panelRef.current && !panelRef.current.contains(ev.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const scope = TAB_SCOPE[view] || TAB_SCOPE.hq;
  const scoped = feed.filter((e) => inScope(e, scope));
  const latest = feed[0];
  const latestTime = latest ? new Date(latest.created_at).getTime() : 0;
  const working = busy || (latest && Date.now() - latestTime < IDLE_AFTER_MS);

  let line;
  if (mode === "paused") {
    line = "Paused — I'm standing by. Flip the mode switch when you want me back on shift.";
  } else if (busy) {
    line = "Scouting the market right now — new companies will stream in below.";
  } else if (working && latest) {
    line = latest.description;
  } else if (latest) {
    line = `Watching the market — last action ${timeAgo(latest.created_at)}. Next scouting sweep is on the schedule.`;
  } else {
    line = "On shift and watching the market — activity will appear here the moment I act.";
  }

  const recent = scoped.slice(0, 14);

  return (
    <div className="rn-wrap" ref={panelRef}>
      <button className={`rael-now ${working ? "working" : ""}`} onClick={() => setOpen((v) => !v)} title="See what Rael is doing">
        <span className="rn-avatar">
          <img src={RAEL_IMG} alt="" draggable={false} />
          <span className={`rn-dot ${connected ? (working ? "live" : "idle") : "off"}`} />
        </span>
        <span className="rn-eyebrow">{working ? "Working" : "Watching"}</span>
        <span className="rn-line">{line}</span>
        <span className="rn-chip">{scoped.length ? `${scoped.length} ${scope.label}` : "no activity yet"}</span>
        <span className={`rn-caret ${open ? "open" : ""}`}>▾</span>
      </button>

      {open && (
        <div className="rn-panel">
          <div className="rn-panel-head">
            <span>What I've been doing{scope.match ? ` — ${scope.label}` : ""}</span>
            <span className={`rn-conn ${connected ? "on" : ""}`}>{connected ? "live" : "reconnecting…"}</span>
          </div>
          {recent.length === 0 ? (
            <div className="rn-empty">Nothing in this lane yet — I'll log every step here as I work.</div>
          ) : (
            recent.map((e, i) => (
              <button
                key={e.id ?? `${e.created_at}-${i}`}
                className="rn-row"
                onClick={() => { if (e.lead_id) { openLead(e.lead_id); setOpen(false); } }}
                style={{ cursor: e.lead_id ? "pointer" : "default" }}
              >
                <span className="rn-row-dot" style={{ background: levelColor(e) }} />
                <span className="rn-row-tag">{agentTag(e)}</span>
                <span className="rn-row-msg">{e.description}</span>
                <span className="rn-row-time">{timeAgo(e.created_at)}</span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

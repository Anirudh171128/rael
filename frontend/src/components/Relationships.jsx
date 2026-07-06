import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { clampScore, scoreColor, timeAgo } from "../util";

// Relationship strength, 1–5, from where the conversation stands.
function health(l) {
  const map = {
    closed: 5, meeting: 5, follow_up: 5, warm: 4,
    contacted: 3, pending_approval: 3, qualified: 3,
    enriched: 2, identified: 2, watching: 2, incomplete: 2,
    disqualified: 1, unsubscribed: 1,
  };
  let lvl = map[l.status] ?? 2;
  if ((l.fit_score ?? 0) >= 85 && lvl < 5) lvl += 0; // fit already shown separately
  const label = lvl >= 4 ? "Strong" : lvl === 3 ? "Building" : lvl === 2 ? "New" : "Cold";
  return { lvl, label };
}

function historyFor(l) {
  const base = {
    warm: "Replied warm", contacted: "Outreach sent", pending_approval: "Outreach drafted",
    qualified: "Scored a strong fit", enriched: "Contact identified", identified: "Signal detected",
    meeting: "Meeting booked", follow_up: "Following up", closed: "Deal closed",
    disqualified: "Set aside", unsubscribed: "Opted out", watching: "Watching",
  }[l.status] || "In motion";
  const trig = l.trigger_event ? ` · ${l.trigger_event.length > 46 ? l.trigger_event.slice(0, 46) + "…" : l.trigger_event}` : "";
  return base + trig;
}

function nextFor(l) {
  switch (l.status) {
    case "warm": return "Rael recommends calling this week";
    case "pending_approval": return "Approve the outreach Rael drafted";
    case "contacted": return "Rael will follow up in 2 days";
    case "qualified": return "Rael is about to reach out";
    case "meeting": return "Prep for the meeting";
    case "follow_up": return "Rael is staying close";
    case "closed": return "Nurture for expansion";
    case "enriched": case "identified": case "watching": return "Rael is still researching";
    default: return "Rael is keeping an eye on this";
  }
}

export default function Relationships() {
  const { leads, openLead } = useStore(useShallow((s) => ({ leads: s.leads, openLead: s.openLead })));

  const people = [...leads]
    .filter((l) => l.contact_name || l.company_name)
    .sort((a, b) => health(b).lvl - health(a).lvl || (b.fit_score ?? 0) - (a.fit_score ?? 0));

  return (
    <div className="screen rise">
      <div className="screen-eyebrow">Rael · Relationships</div>
      <h1 className="screen-title">Everyone I'm building a relationship with.</h1>
      <p className="screen-sub">Not a lead list — the people I'm getting to know, and where each one stands.</p>

      {people.length === 0 && (
        <div className="hq-help-empty">I haven't met anyone yet — once I work a cycle, they'll show up here.</div>
      )}

      <div className="rel-grid">
        {people.map((l) => {
          const h = health(l);
          const score = clampScore(l.fit_score);
          return (
            <div className="rel-card" key={l.id} onClick={() => openLead(l.id)}>
              <div className="rel-head">
                <div>
                  <div className="rel-name">{l.contact_name || l.company_name}</div>
                  <div className="rel-co">{l.title ? `${l.title} · ` : ""}{l.company_name}</div>
                </div>
                {score != null && <span className="rel-score" style={{ color: scoreColor(score) }}>{score}</span>}
              </div>

              <div className="rel-health">
                <span className="rel-dots">
                  {[0, 1, 2, 3, 4].map((i) => <i key={i} className={i < h.lvl ? "on" : ""} />)}
                </span>
                <span className="rel-health-label">{h.label}</span>
              </div>

              <div className="rel-row"><span className="k">Last seen</span><span>{timeAgo(l.last_touched_at) || "recently"}</span></div>
              <div className="rel-row"><span className="k">History</span><span>{historyFor(l)}</span></div>
              <div className="rel-next">→ {nextFor(l)}</div>

              <div className="rel-link">View full history →</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

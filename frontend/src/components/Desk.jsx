import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { timeAgo } from "../util";

// What Rael is literally doing on a given lead — specific, so you feel him working.
function doingLine(l) {
  const who = l.contact_name || "the team";
  switch (l.status) {
    case "identified": return <>Waiting for your OK to pull contacts for <span className="who">{l.company_name}</span> (Apollo)</>;
    case "incomplete": return <>No verified contact yet at <span className="who">{l.company_name}</span> — watching</>;
    case "enriched": return <>Got the decision-maker at <span className="who">{l.company_name}</span> — scoring next</>;
    case "qualified": return <>Writing outreach for <span className="who">{who}</span> <span className="co">· {l.company_name}</span></>;
    case "pending_approval": return <>Outreach drafted for <span className="who">{l.company_name}</span> — your call</>;
    case "contacted": return <>Following the thread with <span className="who">{who}</span> <span className="co">· {l.company_name}</span></>;
    case "warm": return <>Handling the reply from <span className="who">{who}</span> <span className="co">· {l.company_name}</span></>;
    default: return <>Working on <span className="who">{l.company_name}</span></>;
  }
}

export default function Desk() {
  const { metrics, hot, leads, openLead } = useStore(
    useShallow((s) => ({ metrics: s.metrics, hot: s.hot, leads: s.leads, openLead: s.openLead }))
  );

  const byId = Object.fromEntries(leads.map((l) => [l.id, l]));
  const waiting = hot.filter((h) => h.needs_you);
  const working = leads
    .filter((l) => ["identified", "incomplete", "enriched", "qualified", "contacted", "warm"].includes(l.status))
    .slice(0, 5);

  const wins = [
    { n: metrics.contacted ?? 0, t: "prospects contacted" },
    { n: metrics.replies ?? 0, t: "conversations started" },
    { n: metrics.meetings ?? 0, t: "meetings booked", green: true },
  ];

  return (
    <div className="screen rise">
      <div className="screen-eyebrow">Rael · Desk</div>
      <h1 className="screen-title">Here's what's on my desk.</h1>
      <p className="screen-sub">What I'm carrying right now, what needs you, and what I've already cleared.</p>

      <div className="desk-grid">
        <div>
          <div className="hq-label">Working on right now</div>
          <div style={{ marginBottom: 36 }}>
            {working.length ? (
              working.map((l) => (
                <div className="desk-doing" key={l.id} onClick={() => openLead(l.id)} style={{ cursor: "pointer" }}>
                  <span className="spin">⟳</span> {doingLine(l)}
                </div>
              ))
            ) : (
              <div className="hq-help-empty">Quiet desk — I'm scanning for the next signal.</div>
            )}
          </div>

          <div className="hq-label">Waiting on you</div>
          <div>
            {waiting.length ? (
              waiting.map((h) => {
                const lead = byId[h.lead_id];
                const badge = h.status === "pending_approval" ? "APPROVAL NEEDED" : "WARM REPLY";
                return (
                  <div className="help-card" key={h.lead_id} onClick={() => openLead(h.lead_id)}>
                    <span className="help-flag" />
                    <div className="help-body">
                      <div className="help-top">
                        <span className={`help-badge ${h.status === "pending_approval" ? "approval" : "warm"}`}>{badge}</span>
                        <span className="help-name">{h.contact_name || h.company_name}<span style={{ color: "var(--muted)", fontWeight: 400 }}> · {h.company_name}</span></span>
                      </div>
                      <div className="help-reason">
                        {h.status === "pending_approval" ? "Approve the outreach I drafted" : "Review and reply"}
                      </div>
                    </div>
                    {lead?.last_touched_at && <span className="help-time">waiting {timeAgo(lead.last_touched_at)}</span>}
                  </div>
                );
              })
            ) : (
              <div className="hq-help-empty">Nothing — <span className="accent">you're clear</span>.</div>
            )}
          </div>
        </div>

        <div>
          <div className="hq-label">Completed today</div>
          <div className="desk-wins col">
            {wins.map((w) => (
              <div className="win" key={w.t}>
                <div className="win-top"><span className="win-check">✓</span><span className="win-label" style={{ margin: 0 }}>{w.t}</span></div>
                <div className={`win-num ${w.green ? "green" : ""}`}>{w.n}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

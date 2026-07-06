import { useState } from "react";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

const RAEL_IMG = import.meta.env.VITE_RAEL_AVATAR_IMG || "/rael.png";

function partOfDay() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

// Rough hours-on-shift from the earliest activity still in the feed.
function hoursWorked(feed) {
  if (!feed.length) return null;
  const times = feed.map((e) => new Date(e.created_at).getTime()).filter((t) => !isNaN(t));
  if (!times.length) return null;
  const hrs = Math.round((Date.now() - Math.min(...times)) / 3600000);
  return Math.max(1, Math.min(hrs, 14));
}

// Humanize why a lead needs the rep.
function reasonFor(h) {
  if (h.status === "pending_approval") return "I drafted the outreach — I'd like your sign-off before it goes.";
  if (h.status === "warm") return h.why ? `Replied warm. ${h.why}` : "Replied warm and wants to talk.";
  return h.why || "Worth a look while it's hot.";
}
function badgeFor(h) {
  if (h.status === "pending_approval") return { cls: "approval", label: "APPROVAL NEEDED" };
  if (h.status === "warm") return { cls: "warm", label: "WARM REPLY" };
  return { cls: "warm", label: "NEEDS YOU" };
}

// Map a lead's stage to a live-work progress.
const STAGE = { identified: 1, enriched: 2, qualified: 3, pending_approval: 4, contacted: 4, warm: 4 };
const STEPS = ["Found the buying signal", "Enriched the contact", "Scored it against your Fit Model", "Drafting the outreach"];
const STATUS_WORD = { 1: "Researching", 2: "Enriching", 3: "Scoring", 4: "Writing" };

export default function HQ() {
  const { metrics, hot, leads, feed, openLead, setView } = useStore(
    useShallow((s) => ({
      metrics: s.metrics, hot: s.hot, leads: s.leads, feed: s.feed,
      openLead: s.openLead, setView: s.setView,
    }))
  );
  const [silenced, setSilenced] = useState(false);

  const hrs = hoursWorked(feed);
  const help = hot.filter((h) => h.needs_you).slice(0, 3);

  const acc = [
    { n: metrics.contacted ?? 0, t: "prospects contacted" },
    { n: metrics.replies ?? 0, t: "conversations started" },
    { n: metrics.meetings ?? 0, t: "meetings booked" },
    { n: `$${(metrics.pipeline_value ?? 0).toLocaleString()}`, t: "pipeline created" },
  ];

  // Live work: the freshest lead still mid-pipeline.
  const inFlight = leads.find((l) => STAGE[l.status] && STAGE[l.status] < 4) || leads.find((l) => STAGE[l.status]);
  const rank = inFlight ? STAGE[inFlight.status] || 4 : 0;

  return (
    <div className="hq rise">
      <div className="hq-head">
        <div className="hq-portrait">
          <img src={RAEL_IMG} alt="Rael" draggable={false} />
        </div>
        <div style={{ flex: 1 }}>
          <div className="hq-eyebrow">Rael · {inFlight ? STATUS_WORD[rank] : "Monitoring"} now</div>
          <h1 className="hq-greeting">{partOfDay()}.</h1>
          <p className="hq-sub">
            {hrs ? <>I've been working for about <span className="accent">{hrs} {hrs === 1 ? "hour" : "hours"}</span>. Here's where things stand.</>
                 : <>I'm watching the market for you. Here's where things stand.</>}
          </p>
        </div>
      </div>

      <div className="hq-grid">
        <div className="hq-left">
          {/* What I got done */}
          <section className="hq-block">
            <div className="hq-label">What I got done</div>
            <div className="hq-acc">
              {acc.map((a) => (
                <div className="acc" key={a.t}>
                  <span className="check">✓</span>
                  <span className="num">{a.n}</span>
                  <span className="txt">{a.t}</span>
                </div>
              ))}
            </div>
          </section>

          {/* I need your help with */}
          <section className="hq-block">
            <div className="hq-label">I need your help with</div>
            {silenced ? (
              <div className="hq-help-empty">I'll keep working quietly and resurface these when they're hotter.</div>
            ) : help.length === 0 ? (
              <div className="hq-help-empty">Nothing right now — <span className="accent">you're all caught up</span>. I'll handle the rest.</div>
            ) : (
              <>
                {help.map((h) => (
                  <div className="help-card" key={h.lead_id} onClick={() => openLead(h.lead_id)}>
                    <span className="help-flag" />
                    <div className="help-body">
                      <div className="help-top">
                        <span className={`help-badge ${badgeFor(h).cls}`}>{badgeFor(h).label}</span>
                        <span className="help-name">{h.contact_name || h.company_name}{h.contact_name && <span style={{ color: "var(--muted)", fontWeight: 400 }}> · {h.company_name}</span>}</span>
                      </div>
                      <div className="help-reason">{reasonFor(h)}</div>
                    </div>
                    <span className="help-go">Show me →</span>
                  </div>
                ))}
                <div className="hq-cta">
                  <button className="cta primary" onClick={() => setView("outreach")}>Review the drafts</button>
                  <button className="cta" onClick={() => setView("relationships")}>Show hot leads</button>
                  <button className="cta ghost" onClick={() => setSilenced(true)}>Stay silent</button>
                </div>
              </>
            )}
          </section>
        </div>

        {/* Glass wall — live work (right rail) */}
        <div className="hq-right">
          <section className="hq-block">
            <div className="hq-label">Live — what I'm doing right now</div>
            <div className="glasswall">
              {inFlight ? (
                <>
                  <div className="gw-top">
                    <div className="gw-now">Currently working on <b>{inFlight.company_name}</b></div>
                    <div className="gw-status"><span className="ws-dot" style={{ background: "var(--signal)" }} /> {STATUS_WORD[rank]}</div>
                  </div>
                  <div className="gw-bar"><div className="gw-fill" style={{ width: `${(rank / 4) * 100}%` }} /></div>
                  <div className="gw-steps">
                    {STEPS.map((s, i) => {
                      const state = i + 1 < rank ? "done" : i + 1 === rank ? "doing" : "todo";
                      return (
                        <div className={`gw-step ${state}`} key={s}>
                          <span className="ic">{state === "done" ? "✓" : state === "doing" ? "⟳" : "○"}</span>
                          {s}
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div className="gw-now">All caught up — I'm scanning the market for the next signal. <span className="ws-dot" style={{ background: "var(--signal)", display: "inline-block", marginLeft: 4 }} /></div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

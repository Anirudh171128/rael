import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { clampScore, scoreColor, timeAgo } from "../util";

const COLUMNS = [
  { key: "identified", label: "Identified", color: "var(--faint)", statuses: ["identified", "enriched", "incomplete", "watching"] },
  { key: "contacted", label: "Contacted", color: "#6B93E0", statuses: ["qualified", "pending_approval", "contacted"] },
  { key: "replied", label: "Replied", color: "var(--signal)", statuses: ["warm", "unsubscribed"] },
  { key: "meeting", label: "Meeting", color: "var(--sage)", statuses: ["meeting", "follow_up"] },
  { key: "closed", label: "Closed", color: "#34D399", statuses: ["closed", "disqualified"] },
];

function actionWord(s) {
  if (["identified", "enriched", "incomplete", "watching"].includes(s)) return "spotted";
  if (s === "qualified") return "scored";
  if (["pending_approval", "contacted"].includes(s)) return "reached out";
  if (["warm", "unsubscribed"].includes(s)) return "heard back";
  if (["meeting", "follow_up"].includes(s)) return "booked a meeting";
  if (s === "closed") return "closed";
  return "updated";
}

export default function Pipeline() {
  const { leads, openLead } = useStore(useShallow((s) => ({ leads: s.leads, openLead: s.openLead })));

  return (
    <div className="pl-wrap">
      <div className="screen-eyebrow">Rael · Pipeline</div>
      <h1 className="screen-title" style={{ marginBottom: 20 }}>Everyone I'm moving forward.</h1>
      <div className="pl-board">
        {COLUMNS.map((col) => {
          const cards = leads.filter((l) => col.statuses.includes(l.status));
          return (
            <div className="pl-col" key={col.key}>
              <div className="pl-colhead">
                <span className="pl-coltag" style={{ background: col.color, boxShadow: `0 0 7px ${col.color}` }} />
                <span className="pl-colname">{col.label}</span>
                <span className="pl-colcount">{cards.length}</span>
              </div>
              <div className="pl-cards">
                {cards.map((l) => {
                  const score = clampScore(l.fit_score);
                  return (
                    <button className="pl-card" key={l.id} onClick={() => openLead(l.id)}>
                      <div className="pl-card-top">
                        <span className="pl-co">{l.company_name}</span>
                        <span className="pl-score" style={{ color: score == null ? "var(--faint)" : scoreColor(score) }}>
                          {score ?? "—"}
                        </span>
                      </div>
                      <div className="pl-contact">{l.contact_name || "—"}{l.title ? ` · ${l.title}` : ""}</div>
                      {l.trigger_event && <div className="pl-trigger">{l.trigger_event}</div>}
                      <div className="pl-when">Rael {actionWord(l.status)} {timeAgo(l.last_touched_at) || "recently"}</div>
                    </button>
                  );
                })}
                {cards.length === 0 && (
                  <div className="pl-empty">Rael is watching for leads at this stage.</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

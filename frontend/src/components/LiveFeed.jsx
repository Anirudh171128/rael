import { useEffect, useRef, useState } from "react";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

const RAEL_IMG = import.meta.env.VITE_RAEL_AVATAR_IMG || "/rael.png";

const FILTERS = [
  ["all", "All"],
  ["outreach", "Outreach"],
  ["signal", "Signals"],
  ["reply", "Replies"],
  ["brief", "Meetings"],
];

const matches = (f, e) => {
  if (f === "all") return true;
  const a = (e.action_type || "") + (e.agent_name || "");
  if (f === "signal") return /signal/i.test(a);
  if (f === "outreach") return /outreach|draft|approval/i.test(a);
  if (f === "reply") return /reply|faq|objection|escalate|warm|hot/i.test(a);
  if (f === "brief") return /brief|meeting/i.test(a);
  return true;
};

// Type → cold-wire color. Warmth (t-warm) appears ONLY on a human moment.
function typeOf(e) {
  const a = ((e.action_type || "") + " " + (e.agent_name || "")).toLowerCase();
  if (e.level === "urgent") return "danger";
  if (/brief|meeting/.test(a)) return "meeting";
  if (/warm|reply|faq|objection|escalate/.test(a) || e.level === "positive") return "warm";
  if (/signal|enrich|qualif/.test(a)) return "signal";
  if (/outreach|draft|approval/.test(a)) return "outreach";
  return "system";
}

// Which of the 8 sub-agents acted — a mono ops tag.
function tagOf(e) {
  const a = ((e.agent_name || "") + " " + (e.action_type || "")).toLowerCase();
  if (/signal/.test(a)) return "SIG";
  if (/enrich/.test(a)) return "ENR";
  if (/qualif/.test(a)) return "QAL";
  if (/outreach|draft|approval/.test(a)) return "OUT";
  if (/reply|faq|objection|escalate/.test(a)) return "RPY";
  if (/brief|meeting/.test(a)) return "MTG";
  if (/memory/.test(a)) return "MEM";
  if (/report/.test(a)) return "RPT";
  if (/orchestr/.test(a)) return "ORC";
  return "SYS";
}

function badgeOf(e, type) {
  if (e.level === "urgent") return ["badge-urgent", "URGENT"];
  if (type === "meeting") return ["badge-warm", "MEETING"];
  if (type === "warm") return ["badge-warm", "WARM"];
  return null;
}

function ts(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

export default function LiveFeed() {
  const [filter, setFilter] = useState("all");
  const { feed, openLead } = useStore(useShallow((s) => ({ feed: s.feed, openLead: s.openLead })));
  const listRef = useRef(null);

  const shown = feed.filter((e) => matches(filter, e));

  useEffect(() => {
    listRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [feed.length]);

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="feed-header">
        <span className="feed-title">
          <span className="live-dot" />
          Live Activity
        </span>
        {FILTERS.map(([k, label]) => (
          <button key={k} onClick={() => setFilter(k)} className={`filter-tab ${filter === k ? "active" : ""}`}>
            {label}
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="feed-empty">
          <img src={RAEL_IMG} alt="Rael" draggable={false} />
          <div className="lead">Rael is scanning the market.</div>
          <div className="sub">Activity appears here as he works.</div>
        </div>
      ) : (
        <div className="feed-list" ref={listRef}>
          {shown.map((e) => {
            const type = typeOf(e);
            const badge = badgeOf(e, type);
            return (
              <div
                key={e.id ?? e.created_at + e.description}
                className={`feed-entry t-${type}`}
                onClick={() => e.lead_id && openLead(e.lead_id)}
              >
                <span className={`entry-tag t-${type}`}>{tagOf(e)}</span>
                <div className="entry-body">
                  <span className="entry-time">{ts(e.created_at)}</span>
                  <div className="entry-desc">
                    {e.description}
                    {badge && <span className={`badge ${badge[0]}`}>{badge[1]}</span>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

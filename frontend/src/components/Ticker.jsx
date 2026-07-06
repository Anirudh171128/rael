import { useEffect, useRef } from "react";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

// Agent tag mapping — compact, monospace.
function tag(e) {
  const a = ((e.agent_name || "") + " " + (e.action_type || "")).toLowerCase();
  if (/discovery|scout/.test(a)) return "SCT";
  if (/signal/.test(a)) return "SIG";
  if (/enrich/.test(a)) return "ENR";
  if (/qualif/.test(a)) return "QAL";
  if (/outreach|draft/.test(a)) return "OUT";
  if (/reply|escalat/.test(a)) return "RPY";
  if (/brief|meeting/.test(a)) return "MTG";
  if (/memory/.test(a)) return "MEM";
  if (/report/.test(a)) return "RPT";
  return "SYS";
}

function levelColor(e) {
  if (e.level === "urgent") return "var(--danger)";
  if (e.level === "positive") return "var(--success)";
  if (e.level === "attention") return "var(--signal)";
  return "var(--muted)";
}

export default function Ticker() {
  const { feed, openLead } = useStore(useShallow((s) => ({ feed: s.feed, openLead: s.openLead })));
  const ref = useRef(null);

  // Smooth-scroll to leftmost on new entry.
  useEffect(() => {
    ref.current?.scrollTo({ left: 0, behavior: "smooth" });
  }, [feed.length]);

  const recent = feed.slice(0, 8);

  return (
    <div className="ticker-wrap">
      <span className="ticker-dot" />
      <div className="ticker-scroll" ref={ref}>
        {recent.map((e, i) => (
          <button
            key={e.id ?? `${e.created_at}-${i}`}
            className="ticker-item"
            onClick={() => e.lead_id && openLead(e.lead_id)}
            style={{ "--lc": levelColor(e) }}
          >
            <span className="ticker-tag">{tag(e)}</span>
            <span className="ticker-msg">{e.description?.length > 64 ? e.description.slice(0, 61) + "…" : e.description}</span>
          </button>
        ))}
        {recent.length === 0 && <span className="ticker-empty">Rael is scanning the market…</span>}
      </div>
    </div>
  );
}

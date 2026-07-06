import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

export default function HotNow() {
  const { hot, openLead } = useStore(useShallow((s) => ({ hot: s.hot, openLead: s.openLead })));

  return (
    <div className="hot-bar">
      <span className="hot-label">Hot Now</span>
      <span className="divider" />
      {hot.length === 0 && <span className="hot-empty">No hot leads yet — Rael is scanning.</span>}
      {hot.map((h) => (
        <button
          key={h.lead_id}
          className={`hot-chip ${h.needs_you ? "needs" : ""}`}
          onClick={() => openLead(h.lead_id)}
          title={h.why || ""}
        >
          {h.fit_score != null && <span className="score-badge">{h.fit_score}</span>}
          <span>
            <span className="chip-name">{h.contact_name || h.company_name}</span>
            {h.contact_name && <span className="chip-company"> · {h.company_name}</span>}
          </span>
          {h.why && <span className="chip-why">{h.why}</span>}
        </button>
      ))}
    </div>
  );
}

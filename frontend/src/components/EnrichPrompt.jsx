import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { clampScore, scoreColor } from "../util";

const RAEL_IMG = import.meta.env.VITE_RAEL_AVATAR_IMG || "/rael.png";

// Pops whenever Rael has found companies whose contacts aren't pulled yet.
// STRICT guardrail: Apollo credits are only spent through the buttons here
// (or the lead panel) — Rael never enriches on his own.
export default function EnrichPrompt() {
  const { leads, enrichDismissed, enriching, enrichLead, enrichAll, snoozeEnrich, openLead } = useStore(
    useShallow((s) => ({
      leads: s.leads,
      enrichDismissed: s.enrichDismissed,
      enriching: s.enriching,
      enrichLead: s.enrichLead,
      enrichAll: s.enrichAll,
      snoozeEnrich: s.snoozeEnrich,
      openLead: s.openLead,
    }))
  );

  // Freshly promoted leads with no contact yet = waiting for the go-ahead.
  const pending = leads.filter((l) => l.status === "identified" && !l.email && !l.contact_name);
  const visible = pending.filter((l) => !enrichDismissed[l.id]);
  const anyEnriching = Object.keys(enriching).length > 0;

  if (!visible.length && !anyEnriching) return null;

  const shown = visible.slice(0, 5);

  return (
    <div className="ep-pop rise">
      <div className="ep-head">
        <span className="ep-portrait"><img src={RAEL_IMG} alt="" draggable={false} /></span>
        <div className="ep-title-wrap">
          <div className="ep-title">
            {anyEnriching && !visible.length
              ? "Pulling contacts from Apollo…"
              : `I found ${visible.length} new compan${visible.length === 1 ? "y" : "ies"}.`}
          </div>
          <div className="ep-sub">
            {anyEnriching && !visible.length
              ? "Only the ones you approved — nothing else."
              : "Should I pull their decision-makers from Apollo? Credits are spent only if you say yes."}
          </div>
        </div>
      </div>

      {shown.length > 0 && (
        <div className="ep-list">
          {shown.map((l) => {
            const score = clampScore(l.fit_score);
            const busy = !!enriching[l.id];
            return (
              <div className="ep-row" key={l.id}>
                <button className="ep-co" onClick={() => openLead(l.id)} title="Open lead">
                  {l.company_name}
                </button>
                {score != null && <span className="ep-score" style={{ color: scoreColor(score) }}>{score}</span>}
                <button className="ep-btn" disabled={busy} onClick={() => enrichLead(l.id)}>
                  {busy ? "Finding…" : "Enrich"}
                </button>
              </div>
            );
          })}
          {visible.length > shown.length && (
            <div className="ep-more">+{visible.length - shown.length} more waiting</div>
          )}
        </div>
      )}

      {visible.length > 0 && (
        <div className="ep-actions">
          <button
            className="cta primary"
            disabled={anyEnriching}
            onClick={() => enrichAll(visible.map((l) => l.id))}
          >
            Enrich all ({visible.length})
          </button>
          <button className="cta ghost" onClick={() => snoozeEnrich(visible.map((l) => l.id))}>
            Not now
          </button>
        </div>
      )}
    </div>
  );
}

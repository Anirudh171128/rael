import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { clampScore, scoreColor } from "../util";

// Turn a lead into the reasons Rael believes in it.
function reasonsFor(l) {
  const out = [];
  if (l.trigger_event) out.push(l.trigger_event);
  if (l.reasoning) {
    l.reasoning.split(/\.\s+/).map((s) => s.replace(/\.$/, "").trim()).filter(Boolean).forEach((s) => out.push(s));
  }
  return out.slice(0, 4);
}

// A unique one-liner that captures WHY — read off the actual buying signal.
function sayFor(l, conf) {
  const t = (l.trigger_event || "").toLowerCase();
  const co = l.company_name;
  if (/intent|posted|searching|evaluat|research/.test(t)) return `${co} named the pain themselves.`;
  if (/fund|raised|series|round|capital/.test(t)) return `${co} just unlocked budget.`;
  if (/hir|sdr|sales role|recruit/.test(t)) return `${co} is scaling its sales team right now.`;
  if (/vp|chief|head of|leadership|joined|new exec/.test(t)) return `${co} put a new decision-maker in the seat.`;
  if (/expand|expansion|new market|launch|growth/.test(t)) return `${co} is expanding — the timing's on our side.`;
  if (conf >= 90) return `${co} is one of your strongest fits right now.`;
  if (conf >= 70) return `${co} looks worth pursuing.`;
  return `I'm watching ${co} — not fully convinced yet.`;
}

export default function Brain() {
  const { leads, openLead } = useStore(useShallow((s) => ({ leads: s.leads, openLead: s.openLead })));

  const beliefs = [...leads]
    .filter((l) => l.fit_score != null)
    .sort((a, b) => (b.fit_score ?? 0) - (a.fit_score ?? 0))
    .slice(0, 12);

  return (
    <div className="screen rise">
      <div className="screen-eyebrow">Rael · Brain</div>
      <h1 className="screen-title">What I believe, and why.</h1>
      <p className="screen-sub">Every company I'm pursuing, the confidence behind it, and the evidence I'm reading.</p>

      {beliefs.length === 0 && (
        <div className="hq-help-empty">I'm still forming opinions — nothing scored yet.</div>
      )}

      <div className="belief-grid">
      {beliefs.map((l) => {
        const conf = clampScore(l.fit_score) ?? 0;
        const reasons = reasonsFor(l);
        const col = scoreColor(conf);
        return (
          <div className="belief" key={l.id} onClick={() => openLead(l.id)}>
            <div className="belief-top">
              <span className="belief-co">{l.company_name}</span>
              <span className="belief-conf" style={{ color: col }}>{conf}% confident</span>
            </div>
            <div className="belief-say">{sayFor(l, conf)}</div>
            <div className="belief-meter"><i style={{ width: `${conf}%`, background: col }} /></div>
            {reasons.length > 0 && (
              <div className="belief-reasons">
                {reasons.map((r, i) => (
                  <span className="reason" key={i}><span className="tick">✓</span>{r}</span>
                ))}
              </div>
            )}
          </div>
        );
      })}
      </div>
    </div>
  );
}

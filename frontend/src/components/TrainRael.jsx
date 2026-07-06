import { useState } from "react";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { api } from "../api";

const RAEL_IMG = import.meta.env.VITE_RAEL_AVATAR_IMG || "/rael.png";

const INDUSTRIES = ["Travel & Tourism", "Hospitality", "Corporate Travel", "SaaS", "D2C", "Fintech", "Healthtech", "EdTech", "E-commerce", "B2B Services"];
const FUNDING_STAGES = ["Bootstrapped", "Seed", "Series A", "Series B", "Series C+"];
const REGIONS = ["India (All)", "Tier 1 Cities", "Tier 2 Cities", "North America", "Europe"];
const SIGNALS = [
  "Recently raised funding (last 6 months)",
  "Actively hiring for sales roles",
  "Leadership change (new CRO/VP Sales/Head of Growth)",
  "Product launch / expansion announcement",
  "Currently using a competitor's product",
  "Tech stack match (integrates with X)",
];

const fromFit = (fit) => {
  const m = {};
  (fit || []).forEach((r) => { m[r.parameter_name] = r.parameter_value; });
  
  const parseList = (str) => str ? str.split(",").map(s => s.trim()).filter(Boolean) : [];
  
  return {
    product_description: m.product_description || "",
    targets: m.targets || "",
    icp_industries: parseList(m.icp_industries),
    icp_funding_stages: parseList(m.icp_funding_stages),
    icp_geographies: parseList(m.icp_geographies) || ["India (All)"],
    icp_company_size_min: parseInt(m.icp_company_size_min) || 1,
    icp_company_size_max: parseInt(m.icp_company_size_max) || 10000,
    signals: parseList(m.signals),
    disqualifiers: parseList(m.disqualifiers).join(", "), // keep as string for input
    qualify_threshold: parseInt(m.qualify_threshold) || 65,
  };
};

export default function TrainRael() {
  const { fit, refresh, setView, authStatus, completeOnboarding, logout } = useStore(
    useShallow((s) => ({
      fit: s.fit,
      refresh: s.refresh,
      setView: s.setView,
      authStatus: s.authStatus,
      completeOnboarding: s.completeOnboarding,
      logout: s.logout
    }))
  );

  const [form, setForm] = useState(() => fromFit(fit));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const setField = (k, v) => setForm((prev) => ({ ...prev, [k]: v }));
  
  const toggleArray = (k, val) => {
    setForm((prev) => {
      const arr = prev[k] || [];
      if (arr.includes(val)) return { ...prev, [k]: arr.filter(x => x !== val) };
      return { ...prev, [k]: [...arr, val] };
    });
  };

  const handleSizeChange = (rangeStr) => {
    const [minStr, maxStr] = rangeStr.split("-");
    let min = parseInt(minStr) || 1;
    let max = maxStr ? (parseInt(maxStr) || 10000) : 10000;
    if (rangeStr.includes("+")) {
      min = parseInt(rangeStr);
      max = 10000;
    }
    setField("icp_company_size_min", min);
    setField("icp_company_size_max", max);
  };

  const getSizeStr = () => {
    if (form.icp_company_size_max === 10) return "1-10";
    if (form.icp_company_size_max === 50) return "11-50";
    if (form.icp_company_size_max === 200) return "51-200";
    if (form.icp_company_size_min === 200) return "200+";
    return "any";
  };

  const canStart = form.product_description.trim() && form.targets.trim();

  async function approve() {
    if (!canStart) return;
    setSaving(true);
    setError("");
    try {
      await api.onboard({
        product_description: form.product_description.trim(),
        targets: form.targets.trim(),
        icp_industries: form.icp_industries,
        icp_funding_stages: form.icp_funding_stages,
        icp_geographies: form.icp_geographies,
        icp_company_size_min: form.icp_company_size_min,
        icp_company_size_max: form.icp_company_size_max,
        signals: form.signals,
        disqualifiers: form.disqualifiers.split(",").map(s => s.trim()).filter(Boolean),
        qualify_threshold: form.qualify_threshold,
      });
      if (authStatus === "onboard_pending") {
        await completeOnboarding();
      } else {
        await refresh();
        setView("hq");
      }
    } catch (e) {
      // Without this, any failure silently reset the button and looked like it
      // "did nothing". Surface it — and if the session lapsed, send them to re-auth.
      if (String(e.message).startsWith("401")) {
        setError("Your session expired. Please sign in again.");
        setTimeout(() => logout(), 1500);
      } else {
        setError("Couldn't save your ICP. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="train rise">
      <div className="train-grid">
        <div className="train-main">
          <div className="train-head">
            <div className="train-portrait"><img src={RAEL_IMG} alt="Rael" draggable={false} /></div>
            <div>
              <div className="train-eyebrow">Training Rael · Target Configuration</div>
              <div className="train-step-of">Set up your engine. I will strictly follow these parameters.</div>
            </div>
          </div>

          <h2 className="text-xl font-serif text-ink mb-2">1. The Core</h2>
          <div className="train-field">
            <label className="train-label">What do we sell?</label>
            <textarea
              className="t-area"
              rows={2}
              placeholder='e.g. "We provide AI voice agents for outbound sales calls and support."'
              value={form.product_description}
              onChange={(e) => setField("product_description", e.target.value)}
            />
          </div>
          <div className="train-field">
            <label className="train-label">Who do you want me to target? (Free text)</label>
            <textarea
              className="t-area"
              rows={2}
              placeholder='e.g. "Series A–B SaaS startups, D2C brands scaling their sales teams."'
              value={form.targets}
              onChange={(e) => setField("targets", e.target.value)}
            />
          </div>

          <div className="h-px bg-white/5 my-8"></div>

          <h2 className="text-xl font-serif text-ink mb-4">2. Firmographics</h2>
          
          <div className="mb-6">
            <label className="train-label">Industry</label>
            <div className="flex flex-wrap gap-2">
              {INDUSTRIES.map(ind => (
                <button
                  key={ind}
                  onClick={() => toggleArray("icp_industries", ind)}
                  className={`train-chip ${form.icp_industries.includes(ind) ? "active" : ""}`}
                >
                  {ind}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-6">
            <label className="train-label">Company Size (Employees)</label>
            <div className="flex flex-wrap gap-2">
              {["1-10", "11-50", "51-200", "200+", "any"].map(size => (
                <button
                  key={size}
                  onClick={() => handleSizeChange(size === "any" ? "1-10000" : size)}
                  className={`train-chip ${getSizeStr() === size ? "active" : ""}`}
                >
                  {size === "any" ? "Any Size" : size}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-6">
            <label className="train-label">Funding Stage</label>
            <div className="flex flex-wrap gap-2">
              {FUNDING_STAGES.map(st => (
                <button
                  key={st}
                  onClick={() => toggleArray("icp_funding_stages", st)}
                  className={`train-chip ${form.icp_funding_stages.includes(st) ? "active" : ""}`}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-6">
            <label className="train-label">Geography</label>
            <div className="flex flex-wrap gap-2">
              {REGIONS.map(reg => (
                <button
                  key={reg}
                  onClick={() => toggleArray("icp_geographies", reg)}
                  className={`train-chip ${form.icp_geographies.includes(reg) ? "active" : ""}`}
                >
                  {reg}
                </button>
              ))}
            </div>
          </div>

          <div className="h-px bg-white/5 my-8"></div>

          <h2 className="text-xl font-serif text-ink mb-2">3. The "Why Now" Signals</h2>
          <p className="text-muted text-sm mb-4">Check the triggers that indicate a prospect is ready to buy.</p>
          <div className="flex flex-col gap-3 mb-6">
            {SIGNALS.map(sig => (
              <label key={sig} className="flex items-center gap-3 cursor-pointer group">
                <div className={`w-5 h-5 rounded border flex items-center justify-center transition-colors ${form.signals.includes(sig) ? 'bg-accent border-accent text-white' : 'border-white/20 group-hover:border-white/40'}`}>
                  {form.signals.includes(sig) && <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                </div>
                <input type="checkbox" className="hidden" checked={form.signals.includes(sig)} onChange={() => toggleArray("signals", sig)} />
                <span className="text-sm text-ink-2">{sig}</span>
              </label>
            ))}
          </div>

          <div className="h-px bg-white/5 my-8"></div>

          <h2 className="text-xl font-serif text-ink mb-2">4. Disqualifiers</h2>
          <p className="text-muted text-sm mb-3">Hard negatives. Never contact if...</p>
          <div className="train-field">
            <input
              type="text"
              className="t-input"
              placeholder='e.g. "already has 10+ SDRs, not hiring, enterprise only"'
              value={form.disqualifiers}
              onChange={(e) => setField("disqualifiers", e.target.value)}
            />
          </div>

          <div className="h-px bg-white/5 my-8"></div>

          <h2 className="text-xl font-serif text-ink mb-2">5. Qualification Bar</h2>
          <p className="text-muted text-sm mb-5">
            Set the score threshold (0-100) a company must reach to be promoted to a Lead. 
            Currently set to: <span className="font-mono text-accent font-bold">{form.qualify_threshold}</span>
          </p>
          <div className="mb-8">
            <input
              type="range"
              min="40"
              max="95"
              step="1"
              value={form.qualify_threshold}
              onChange={(e) => setField("qualify_threshold", parseInt(e.target.value))}
              className="w-full accent-accent bg-card"
            />
            <div className="flex justify-between text-xs text-muted mt-2 font-mono">
              <span>40 (Lenient)</span>
              <span>65 (Balanced)</span>
              <span>95 (Strict)</span>
            </div>
          </div>

          {error && (
            <div className="text-danger bg-danger/10 border border-danger/20 p-3 rounded-lg mt-6 text-sm">{error}</div>
          )}

          <div className="train-nav mt-10">
            <div className="spacer" />
            <button className="cta primary" onClick={approve} disabled={saving || !canStart}>
              {saving ? "Saving…" : "Approve — Set ICP"}
            </button>
          </div>
        </div>

        <aside className="train-preview">
          <div className="pk" style={{ marginTop: 0 }}>Qualification Summary</div>
          
          <Pv label="We sell" v={form.product_description.split("\n")[0]} />
          
          <div className="pk mt-4 mb-2">Firmographics</div>
          <div className="flex flex-wrap gap-1 mb-2">
            {form.icp_industries.map(i => <span key={i} className="pp">{i}</span>)}
            {form.icp_industries.length === 0 && <span className="pv empty">Any industry</span>}
          </div>
          
          <div className="pk mt-3 mb-2">Key Signals</div>
          <div className="flex flex-col gap-1 mb-2">
            {form.signals.map(s => <span key={s} className="text-xs text-ink-2 truncate">✓ {s}</span>)}
            {form.signals.length === 0 && <span className="pv empty">No specific signals</span>}
          </div>

          <div className="pk mt-4">Threshold</div>
          <div className="text-xl font-mono text-success mt-1">{form.qualify_threshold} <span className="text-xs text-muted">/ 100</span></div>
        </aside>
      </div>
    </div>
  );
}

const Pv = ({ label, v }) => (
  <>
    <div className="pk">{label}</div>
    <div className={`pv ${v && v.trim() ? "" : "empty"}`}>{v && v.trim() ? v : "—"}</div>
  </>
);

import { useState } from "react";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";
import { clampScore, scoreColor, timeAgo } from "../util";
import { api } from "../api";

const RAEL_IMG = import.meta.env.VITE_RAEL_AVATAR_IMG || "/rael.png";

const STATUS = {
  promoted: { label: "Lead created", cls: "ok" },
  qualified: { label: "Qualified", cls: "ok" },
  verified: { label: "Verified · watching", cls: "warm" },
  rejected: { label: "Parked", cls: "muted" },
  discovered: { label: "Found", cls: "muted" },
};

const SOURCE = { google: "Web", google_news: "News", careers: "Careers", manual: "Target Account" };

// The buying signal that surfaced a company — the "why now", shown on each card.
const SIGNAL_LABEL = {
  funding: "Recently funded",
  hiring: "Hiring",
  leadership: "New leadership",
  expansion: "Expanding",
  growth: "Growing",
  intent: "Buying intent",
  news: "In the news",
};

const FILTERS = [
  { key: "today", label: "Today" },
  { key: "promoted", label: "Promoted" },
  { key: "score60", label: "Score 60+" },
  { key: "all", label: "All" },
];

const PAGE_SIZE = 15;

function Tags({ items, avoid }) {
  const list = (items || []).filter(Boolean);
  if (!list.length) return <span className="sc-empty">—</span>;
  return (
    <div className="sc-tags">
      {list.map((x, i) => (
        <span className={`sc-tag ${avoid ? "avoid" : ""}`} key={i}>{x}</span>
      ))}
    </div>
  );
}

function isToday(dateStr) {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const now = new Date();
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}

export default function Scouting() {
  const { brain, discovered, busy, runDiscovery, rebuildBrain, openLead } = useStore(
    useShallow((s) => ({
      brain: s.brain,
      discovered: s.discovered,
      busy: s.busy,
      runDiscovery: s.runDiscovery,
      rebuildBrain: s.rebuildBrain,
      openLead: s.openLead,
    }))
  );

  const [mode, setMode] = useState("autonomous"); // "autonomous" | "manual"
  const [filter, setFilter] = useState("today");
  const [page, setPage] = useState(1);
  const [manualUrls, setManualUrls] = useState("");
  const [importing, setImporting] = useState(false);
  const [importSuccess, setImportSuccess] = useState("");

  const u = brain?.understanding || {};
  
  // Distinguish autonomous vs manual discovered companies
  const autoDiscovered = discovered.filter(d => d.discovery_source !== "manual");
  const manualDiscovered = discovered.filter(d => d.discovery_source === "manual");
  
  // Counters for autonomous
  const promoted = autoDiscovered.filter((d) => d.status === "promoted").length;
  const todayCount = autoDiscovered.filter((d) => isToday(d.discovered_at || d.created_at)).length;

  // Apply filter (for autonomous list)
  let filtered = autoDiscovered;
  if (filter === "today") {
    filtered = autoDiscovered.filter((d) => isToday(d.discovered_at || d.created_at));
  } else if (filter === "promoted") {
    filtered = autoDiscovered.filter((d) => d.status === "promoted");
  } else if (filter === "score60") {
    filtered = autoDiscovered.filter((d) => (d.fit_score ?? 0) >= 60);
  }

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const visible = filtered.slice(0, page * PAGE_SIZE);
  
  // For manual list
  const manualVisible = manualDiscovered.slice(0, page * PAGE_SIZE);

  const handleImport = async () => {
    const urls = manualUrls.split("\n").map(u => u.trim()).filter(Boolean);
    if (!urls.length) return;
    setImporting(true);
    setImportSuccess("");
    try {
      const res = await api.importUrls(urls);
      setImportSuccess(`Successfully imported ${res.data.created} accounts. Rael is now verifying them.`);
      setManualUrls("");
      useStore.getState().refresh();
    } catch (e) {
      console.error(e);
      setImportSuccess("Failed to import URLs.");
    } finally {
      setImporting(false);
    }
  };

  const renderCard = (d) => {
    const st = STATUS[d.status] || STATUS.discovered;
    const score = clampScore(d.fit_score);
    const ev = (d.evidence && d.evidence[0]) || {};
    return (
      <div
        className={`sc-card ${d.lead_id ? "clickable" : ""}`}
        key={d.id}
        onClick={() => d.lead_id && openLead(d.lead_id)}
      >
        <div className="sc-card-main">
          <div className="sc-card-top">
            <span className="sc-co">{d.company_name}</span>
            {d.domain && <span className="sc-dom">{d.domain}</span>}
            <span className={`sc-badge ${st.cls}`}>{st.label}</span>
            {!d.verified && <span className="sc-badge muted">unverified</span>}
          </div>
          <div className="sc-firmo">
            {ev.signal && <span className="sc-why">{SIGNAL_LABEL[ev.signal] || ev.signal}</span>}
            {d.industry && <span>{d.industry}</span>}
            {d.employee_count != null && <span>{d.employee_count} ppl</span>}
            {d.funding && d.funding !== "unknown" && <span>{d.funding}</span>}
            <span className="sc-src">via {SOURCE[d.discovery_source] || d.discovery_source}</span>
          </div>
          {ev.snippet && <div className="sc-ev">"{ev.snippet}"</div>}
          {d.reasoning && <div className="sc-reason">{d.reasoning}</div>}
        </div>
        {score != null && (
          <div className="sc-score">
            <div className="sc-score-num" style={{ color: scoreColor(score) }}>{score}</div>
            <div className="sc-score-lbl">fit</div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="screen rise">
      <div className="screen-eyebrow">Rael · Scouting</div>
      
      {/* Mode toggle */}
      <div className="flex gap-4 mb-8 mt-2">
        <button 
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${mode === "autonomous" ? "bg-accent text-white" : "bg-card text-muted hover:text-ink border border-line"}`}
          onClick={() => { setMode("autonomous"); setPage(1); }}
        >
          Mode A: Autonomous Scouting
        </button>
        <button 
          className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${mode === "manual" ? "bg-accent text-white" : "bg-card text-muted hover:text-ink border border-line"}`}
          onClick={() => { setMode("manual"); setPage(1); }}
        >
          Mode B: Target Accounts List (TAL)
        </button>
      </div>

      {mode === "autonomous" ? (
        <>
          <div className="sc-head">
            <div>
              <h1 className="screen-title">Out finding companies for you.</h1>
              <p className="screen-sub">
                I distil what we sell into a search strategy, run it through a browser,
                verify every hit, and only raise a lead once it clears the bar.
              </p>
            </div>
            <div className="sc-actions">
              <button className="cta" onClick={rebuildBrain} disabled={busy}>Rebuild brain</button>
              <button className="cta primary" onClick={runDiscovery} disabled={busy}>
                {busy ? "Scouting…" : "Scout now"}
              </button>
            </div>
          </div>

          {/* ── The Brain: Rael's understanding ── */}
          <div className="sc-brain">
            <div className="sc-brain-portrait"><img src={RAEL_IMG} alt="Rael" draggable={false} /></div>
            <div className="sc-brain-body">
              <div className="sc-brain-top">
                <span className="sc-brain-eyebrow">My understanding</span>
                {brain && (
                  <span className="sc-brain-meta">
                    built {brain.built_from === "mock" ? "from your profile" : `via ${brain.built_from}`} · {timeAgo(brain.created_at)}
                  </span>
                )}
              </div>
              {!brain ? (
                <p className="sc-brain-say">
                  I haven't built my understanding yet — finish Training, then hit <b>Rebuild brain</b>.
                </p>
              ) : (
                <>
                  <p className="sc-brain-say">{brain.summary}</p>
                  <div className="sc-grid">
                    <div className="sc-cell"><div className="sc-k">Industry</div><div className="sc-v">{u.industry || "—"}</div></div>
                    <div className="sc-cell"><div className="sc-k">Buyers I target</div><Tags items={u.buyers} /></div>
                    <div className="sc-cell"><div className="sc-k">Pain signals I hunt for</div><Tags items={u.pain_signals} /></div>
                    <div className="sc-cell"><div className="sc-k">I steer clear of</div><Tags items={u.negative_signals} avoid /></div>
                    <div className="sc-cell wide"><div className="sc-k">What I search for</div><Tags items={u.search_themes} /></div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* ── Running counter bar ── */}
          <div className="sc-counter-bar">
            <div className="sc-counter">{autoDiscovered.length} <span>scanned</span></div>
            <div className="sc-counter accent">{promoted} <span>promoted</span></div>
            <div className="sc-counter">{todayCount} <span>today</span></div>
            <div className="sc-counter">{autoDiscovered.length - promoted} <span>parked</span></div>
          </div>

          {/* ── Filter chips + list ── */}
          <div className="sc-section-head">
            <h2 className="sc-section-title">Companies I've scouted</h2>
            <div className="sc-filters">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  className={`sc-filter ${filter === f.key ? "active" : ""}`}
                  onClick={() => { setFilter(f.key); setPage(1); }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="hq-help-empty">
              {filter === "today"
                ? "Nothing scouted today yet. Hit Scout now and watch me work."
                : "No companies match this filter."}
            </div>
          ) : (
            <>
              <div className="sc-list">
                {visible.map(renderCard)}
              </div>
              {page * PAGE_SIZE < filtered.length && (
                <button className="sc-load-more" onClick={() => setPage((p) => p + 1)}>
                  Load more ({filtered.length - visible.length} remaining)
                </button>
              )}
            </>
          )}
        </>
      ) : (
        <>
          <div className="sc-head">
            <div>
              <h1 className="screen-title">Target Accounts List.</h1>
              <p className="screen-sub">
                Paste URLs of companies you want me to specifically go after.
                I will scrape them, check them against the Brain, score them, and draft outreach.
              </p>
            </div>
          </div>
          
          <div className="bg-card border border-line rounded-xl p-6 mb-8">
            <label className="block text-sm font-medium text-ink-2 mb-3">Paste URLs (one per line)</label>
            <textarea 
              className="w-full bg-surface border border-line-2 rounded-lg p-3 text-sm font-mono text-ink resize-y outline-none focus:border-accent"
              rows={5}
              placeholder="https://acme.com&#10;https://example.com"
              value={manualUrls}
              onChange={e => setManualUrls(e.target.value)}
            />
            
            {importSuccess && (
              <div className="mt-4 p-3 rounded bg-success-soft text-success text-sm">
                {importSuccess}
              </div>
            )}
            
            <div className="flex justify-end mt-4">
              <button 
                className="cta primary"
                onClick={handleImport}
                disabled={importing || !manualUrls.trim()}
              >
                {importing ? "Importing..." : "Add to pipeline"}
              </button>
            </div>
          </div>
          
          <div className="sc-section-head mt-8">
            <h2 className="sc-section-title">Manual Imports ({manualDiscovered.length})</h2>
          </div>
          
          {manualDiscovered.length === 0 ? (
            <div className="hq-help-empty">
              You haven't imported any target accounts yet.
            </div>
          ) : (
            <>
              <div className="sc-list">
                {manualVisible.map(renderCard)}
              </div>
              {page * PAGE_SIZE < manualDiscovered.length && (
                <button className="sc-load-more" onClick={() => setPage((p) => p + 1)}>
                  Load more ({manualDiscovered.length - manualVisible.length} remaining)
                </button>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

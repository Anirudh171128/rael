import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useStore } from "../store";
import { useShallow } from "zustand/react/shallow";

const OUTCOMES = [
  ["great_fit", "✅ Great fit", "bg-success/15 border-success/30 text-success"],
  ["wrong_fit", "❌ Wrong fit", "bg-rose-500/15 border-rose-500/30 text-rose-300"],
  ["follow_up", "🔄 Follow up", "bg-accent/15 border-accent/30 text-accent"],
  ["closed", "🤝 Closed", "bg-hot/15 border-hot/30 text-hot"],
];

export default function LeadPanel() {
  const { selected, closeLead, approve, recordOutcome, simulateReply, makeBrief, enrichLead, enriching } = useStore(useShallow((s) => ({
    selected: s.selected,
    closeLead: s.closeLead,
    approve: s.approve,
    recordOutcome: s.recordOutcome,
    simulateReply: s.simulateReply,
    makeBrief: s.makeBrief,
    enrichLead: s.enrichLead,
    enriching: s.enriching,
  })));
  const [reply, setReply] = useState("");

  const lead = selected?.lead;
  const draft = selected?.interactions?.find((i) => i.outcome === "pending_approval");
  const briefCard = [...(selected?.logs || [])].reverse().find((l) => l.action_type === "brief")?.extra?.card;

  return (
    <AnimatePresence>
      {selected && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeLead}
            className="fixed inset-0 bg-black/50 z-40"
          />
          <motion.aside
            initial={{ x: 460 }}
            animate={{ x: 0 }}
            exit={{ x: 460 }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            className="fixed right-0 top-0 h-full w-[460px] bg-surface border-l border-white/10 z-50 overflow-y-auto"
          >
            <div className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <h2 className="text-lg font-bold">{lead.company_name}</h2>
                  <div className="text-sm text-muted">
                    {lead.contact_name || "—"} · {lead.title || ""}
                  </div>
                </div>
                <button onClick={closeLead} className="text-muted hover:text-ink text-xl leading-none">×</button>
              </div>

              <div className="flex gap-2 mt-3 flex-wrap text-xs">
                <Tag>{lead.status.replace("_", " ")}</Tag>
                {lead.fit_score != null && <Tag>fit {lead.fit_score}</Tag>}
                {lead.company_size && <Tag>{lead.company_size} ppl</Tag>}
                {lead.industry && <Tag>{lead.industry}</Tag>}
              </div>

              {lead.reasoning && (
                <div className="mt-4 rounded-lg bg-card border border-white/5 p-3">
                  <div className="text-xs text-muted mb-1">Rael's reasoning</div>
                  <div className="text-sm">{lead.reasoning}</div>
                </div>
              )}

              <div className="mt-3 text-xs text-muted space-y-1">
                {lead.email && <div>✉ {lead.email}</div>}
                {lead.phone && <div>☎ {lead.phone}</div>}
                {lead.linkedin_url && <div>in {lead.linkedin_url}</div>}
                {lead.trigger_event && <div>⚡ {lead.trigger_event}</div>}
                <div>Apollo credits used: {lead.enrichment_cost ?? 0}</div>
              </div>

              {/* Apollo enrichment — human-approved, costs credits */}
              {!lead.email && !["closed", "disqualified", "unsubscribed"].includes(lead.status) && (
                <div className="mt-4 rounded-lg bg-accent/10 border border-accent/30 p-3">
                  <div className="text-xs text-accent font-semibold mb-1">No verified contact yet</div>
                  <div className="text-sm text-muted mb-2">
                    I don't invent contacts — say the word and I'll pull the decision-maker from Apollo (~1 credit).
                  </div>
                  <Btn
                    onClick={() => enrichLead(lead.id)}
                    cls="bg-accent/20 border-accent/40 text-accent"
                  >
                    {enriching[lead.id] ? "Finding the decision-maker…" : "🔎 Enrich via Apollo"}
                  </Btn>
                </div>
              )}

              {/* Approval surface */}
              {draft && (
                <div className="mt-4 rounded-lg bg-hot/10 border border-hot/30 p-3">
                  <div className="text-xs text-hot font-semibold mb-1">Draft awaiting approval ({draft.channel})</div>
                  {draft.subject && <div className="text-sm font-semibold mb-1">{draft.subject}</div>}
                  <div className="text-sm italic">"{draft.content}"</div>
                  <div className="text-xs text-muted mt-2">Want to reword it? Open the Outreach tab to edit before sending.</div>
                  <div className="flex gap-2 mt-3">
                    <Btn onClick={() => approve(lead.id, "send")} cls="bg-success/20 border-success/40 text-success">Send it</Btn>
                    <Btn onClick={() => approve(lead.id, "skip")} cls="bg-card border-white/10 text-muted">Skip</Btn>
                  </div>
                </div>
              )}

              {/* Brief */}
              <div className="mt-4">
                <button
                  onClick={() => makeBrief(lead.id)}
                  className="text-sm px-3 py-1.5 rounded-lg bg-card border border-white/10 hover:border-accent/40 transition"
                >
                  📋 Generate pre-call brief
                </button>
                {briefCard && (
                  <div className="mt-2 rounded-lg bg-card border border-white/5 p-3 text-sm whitespace-pre-wrap">
                    {briefCard.brief}
                  </div>
                )}
              </div>

              {/* Timeline */}
              <div className="mt-5">
                <div className="text-xs text-muted mb-2 uppercase tracking-wide">Timeline</div>
                <div className="space-y-2">
                  {selected.logs.map((l) => (
                    <div key={"log" + l.id} className="flex gap-2 text-sm">
                      <span className="w-1.5 h-1.5 rounded-full bg-accent mt-2 shrink-0" />
                      <span className="text-muted">{l.description}</span>
                    </div>
                  ))}
                  {selected.logs.length === 0 && <div className="text-xs text-muted/60">No activity yet.</div>}
                </div>
              </div>

              {/* Simulate inbound reply (stands in for SendGrid/LinkedIn webhook) */}
              <div className="mt-5">
                <div className="text-xs text-muted mb-1">Simulate an inbound reply</div>
                <div className="flex gap-2">
                  <input
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder="e.g. This sounds interesting, let's talk"
                    className="flex-1 bg-card border border-white/10 rounded-lg px-3 py-2 text-sm outline-none focus:border-accent/50"
                  />
                  <Btn
                    onClick={() => { if (reply.trim()) { simulateReply(lead.id, reply); setReply(""); } }}
                    cls="bg-accent/20 border-accent/40 text-accent"
                  >
                    Send
                  </Btn>
                </div>
              </div>

              {/* Outcome buttons */}
              <div className="mt-5">
                <div className="text-xs text-muted mb-2">After the call, tell Rael how it went</div>
                <div className="grid grid-cols-2 gap-2">
                  {OUTCOMES.map(([k, label, cls]) => (
                    <button
                      key={k}
                      onClick={() => recordOutcome(lead.id, k, k === "closed" ? 30000 : undefined)}
                      className={`px-3 py-2 rounded-lg border text-sm transition ${cls}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

const Tag = ({ children }) => (
  <span className="px-2 py-0.5 rounded-md bg-card border border-white/5 text-muted">{children}</span>
);
const Btn = ({ onClick, cls, children }) => (
  <button onClick={onClick} className={`px-3 py-1.5 rounded-lg border text-sm transition ${cls}`}>
    {children}
  </button>
);
